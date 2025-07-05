#!/bin/bash

# SSL Management Helper Script
# Usage: ./scripts/ssl-manager.sh [command]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DOMAIN="api.oifyk.com"

# Docker compose command with env file
DC_CMD="docker compose --env-file .env.production -f docker-compose.production.yml"

# Check if we're in the project directory
cd "$PROJECT_DIR"

show_help() {
    echo "🔐 SSL Management Helper"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  status     - Show SSL certificate status"
    echo "  renew      - Force certificate renewal"
    echo "  logs       - Show nginx and certbot logs"
    echo "  restart    - Restart nginx service"
    echo "  test       - Test SSL configuration"
    echo "  setup      - Initial SSL setup"
    echo "  help       - Show this help message"
    echo ""
}

check_ssl_status() {
    echo "🔍 Checking SSL certificate status for $DOMAIN..."
    
    if [ -f "./certbot/conf/live/$DOMAIN/fullchain.pem" ]; then
        echo "✅ SSL certificate exists"
        
        # Check expiration
        expiry_date=$(openssl x509 -enddate -noout -in "./certbot/conf/live/$DOMAIN/fullchain.pem" | cut -d= -f 2)
        echo "📅 Certificate expires: $expiry_date"
        
        # Check if certificate is valid for next 30 days
        if openssl x509 -checkend 2592000 -noout -in "./certbot/conf/live/$DOMAIN/fullchain.pem" >/dev/null 2>&1; then
            echo "✅ Certificate is valid for the next 30 days"
        else
            echo "⚠️ Certificate expires within 30 days - renewal recommended"
        fi
        
        # Show certificate details
        echo "📋 Certificate details:"
        openssl x509 -in "./certbot/conf/live/$DOMAIN/fullchain.pem" -text -noout | grep -E "(Subject:|Issuer:|Not Before|Not After)"
        
    else
        echo "❌ SSL certificate not found"
        echo "🔧 Run: $0 setup"
    fi
}

renew_certificate() {
    echo "🔄 Forcing SSL certificate renewal..."
    
    # Stop nginx temporarily
    echo "🛑 Stopping nginx for renewal..."
    $DC_CMD stop nginx
    
    # Run certbot renewal
    echo "📜 Running certbot renewal..."
    $DC_CMD run --rm certbot \
        certonly \
        --standalone \
        --email "${ADMIN_EMAIL:-admin@oifyk.com}" \
        --agree-tos \
        --no-eff-email \
        --force-renewal \
        -d "$DOMAIN"
    
    if [ $? -eq 0 ]; then
        echo "✅ Certificate renewed successfully"
        
        # Restart nginx
        echo "🔄 Restarting nginx..."
        $DC_CMD up -d nginx
        
        echo "✅ SSL renewal completed"
    else
        echo "❌ Certificate renewal failed"
        
        # Restart nginx anyway
        echo "🔄 Restarting nginx..."
        $DC_CMD up -d nginx
        
        exit 1
    fi
}

show_logs() {
    echo "📋 Showing SSL-related logs..."
    
    echo "🌐 Nginx logs (last 50 lines):"
    $DC_CMD logs --tail=50 nginx
    
    echo ""
    echo "🔐 Recent certbot operations:"
    if [ -f "./certbot/conf/letsencrypt.log" ]; then
        tail -n 20 "./certbot/conf/letsencrypt.log"
    else
        echo "No certbot logs found"
    fi
}

restart_nginx() {
    echo "🔄 Restarting nginx service..."
    $DC_CMD restart nginx
    
    # Wait for nginx to be ready
    echo "⏳ Waiting for nginx to restart..."
    sleep 5
    
    if curl -f http://localhost/api/health/ >/dev/null 2>&1; then
        echo "✅ Nginx restarted successfully"
    else
        echo "❌ Nginx restart failed"
        echo "📋 Checking logs..."
        $DC_CMD logs --tail=20 nginx
        exit 1
    fi
}

test_ssl() {
    echo "🧪 Testing SSL configuration..."
    
    # Test HTTP redirect
    echo "🔍 Testing HTTP to HTTPS redirect..."
    http_response=$(curl -s -o /dev/null -w "%{http_code}" http://$DOMAIN/api/health/ || echo "000")
    
    if [ "$http_response" = "301" ] || [ "$http_response" = "302" ]; then
        echo "✅ HTTP to HTTPS redirect working"
    else
        echo "⚠️ HTTP redirect not working (got $http_response)"
    fi
    
    # Test HTTPS
    echo "🔍 Testing HTTPS connection..."
    if curl -f https://$DOMAIN/api/health/ >/dev/null 2>&1; then
        echo "✅ HTTPS connection working"
        
        # Test SSL certificate
        echo "🔍 Testing SSL certificate..."
        ssl_info=$(echo | openssl s_client -servername $DOMAIN -connect $DOMAIN:443 2>/dev/null | openssl x509 -noout -dates)
        echo "📋 SSL certificate info:"
        echo "$ssl_info"
        
    else
        echo "❌ HTTPS connection failed"
    fi
    
    # Test local connections
    echo "🔍 Testing local connections..."
    if curl -f http://localhost/api/health/ >/dev/null 2>&1; then
        echo "✅ Local HTTP working"
    else
        echo "❌ Local HTTP failed"
    fi
    
    if curl -f -k https://localhost/api/health/ >/dev/null 2>&1; then
        echo "✅ Local HTTPS working"
    else
        echo "❌ Local HTTPS failed"
    fi
}

setup_ssl() {
    echo "🔧 Setting up SSL certificates..."
    
    # Ensure directories exist
    mkdir -p certbot/conf certbot/www
    
    # Stop nginx if running
    echo "🛑 Stopping nginx..."
    $DC_CMD stop nginx || true
    
    # Start web service for certbot validation
    echo "🚀 Starting web service..."
    $DC_CMD up -d web
    
    # Wait for web service
    echo "⏳ Waiting for web service..."
    timeout=60
    counter=0
    while ! curl -f http://localhost:8000/api/health/ >/dev/null 2>&1 && [ $counter -lt $timeout ]; do
        echo "⏳ Waiting for web service... ($counter/$timeout)"
        sleep 2
        counter=$((counter + 2))
    done
    
    if [ $counter -ge $timeout ]; then
        echo "❌ Web service failed to start"
        exit 1
    fi
    
    echo "✅ Web service ready"
    
    # Start nginx for certificate validation
    echo "🌐 Starting nginx for certificate validation..."
    $DC_CMD up -d nginx
    
    # Wait for nginx
    echo "⏳ Waiting for nginx..."
    sleep 10
    
    # Obtain certificate
    echo "📜 Obtaining SSL certificate..."
    renew_certificate
    
    echo "✅ SSL setup completed"
}

# Main script logic
case "${1:-help}" in
    "status")
        check_ssl_status
        ;;
    "renew")
        renew_certificate
        ;;
    "logs")
        show_logs
        ;;
    "restart")
        restart_nginx
        ;;
    "test")
        test_ssl
        ;;
    "setup")
        setup_ssl
        ;;
    "help"|*)
        show_help
        ;;
esac