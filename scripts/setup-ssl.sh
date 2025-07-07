#!/bin/bash

set -e

# Ensure this script has execute permissions
chmod +x "$0" 2>/dev/null || true

echo "🔐 Setting up SSL certificates..."

# Determine Docker Compose command
if docker compose version &> /dev/null; then
    DC_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    DC_CMD="docker-compose"
else
    echo "❌ Docker Compose not found"
    exit 1
fi

DC_CMD="$DC_CMD --env-file .env.production -f docker-compose.production.yml"

# Create directories if they don't exist
echo "📁 Creating certificate directories..."
mkdir -p certbot/conf certbot/www

# Check if certificates already exist
if [ -d "certbot/conf/live/api.oifyk.com" ]; then
    echo "⚠️ Certificates already exist for api.oifyk.com"
    read -p "Do you want to renew them? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "🔄 Switching to SSL configuration..."
        # Just switch to SSL config if certs exist
        if [ -f "nginx-ssl.conf" ]; then
            cp nginx-ssl.conf nginx-initial.conf
            $DC_CMD restart nginx
            echo "✅ SSL configuration activated"
        fi
        exit 0
    fi
fi

# Stop nginx temporarily for standalone certificate generation
echo "🛑 Stopping nginx for certificate generation..."
$DC_CMD stop nginx

# Generate certificates using standalone mode
echo "📜 Generating SSL certificates..."
$DC_CMD run --rm -p 80:80 certbot \
    certonly \
    --standalone \
    --email admin@oifyk.com \
    --agree-tos \
    --no-eff-email \
    --force-renewal \
    -d api.oifyk.com \
    --non-interactive

if [ $? -eq 0 ]; then
    echo "✅ SSL certificates generated successfully"
    
    # Update nginx to use SSL configuration
    echo "🔧 Switching to SSL configuration..."
    if [ -f "nginx-ssl.conf" ]; then
        cp nginx-ssl.conf nginx-initial.conf
        echo "✅ SSL configuration file updated"
    else
        echo "❌ nginx-ssl.conf not found!"
        exit 1
    fi
    
    # Restart nginx with SSL
    echo "🔄 Restarting nginx with SSL..."
    $DC_CMD up -d nginx
    
    # Wait for nginx to start
    sleep 10
    
    # Test HTTP redirect
    echo "🧪 Testing HTTP to HTTPS redirect..."
    if curl -s -o /dev/null -w "%{http_code}" http://localhost/api/health/ | grep -q "301\|302"; then
        echo "✅ HTTP to HTTPS redirect is working"
    else
        echo "⚠️ HTTP redirect test inconclusive"
    fi
    
    # Test HTTPS
    echo "🧪 Testing HTTPS connectivity..."
    if curl -f -k https://localhost/api/health/ > /dev/null 2>&1; then
        echo "✅ HTTPS is working"
    else
        echo "⚠️ HTTPS test failed - checking logs..."
        $DC_CMD logs nginx | tail -20
    fi
    
    # Set up auto-renewal
    echo "⏰ Setting up certificate auto-renewal..."
    echo "0 12 * * * /usr/bin/docker compose --env-file .env.production -f docker-compose.production.yml run --rm certbot renew --quiet && /usr/bin/docker compose --env-file .env.production -f docker-compose.production.yml restart nginx" | crontab -
    
    echo "🎉 SSL setup completed!"
    echo "📅 Auto-renewal scheduled for daily at 12:00 PM"
    
else
    echo "❌ SSL certificate generation failed"
    echo "🔄 Restarting nginx with HTTP config..."
    $DC_CMD up -d nginx
    exit 1
fi

echo ""
echo "🔒 Your API is now available with SSL at:"
echo "  HTTPS: https://api.oifyk.com"
echo "  Admin: https://api.oifyk.com/admin/"
echo "  Health: https://api.oifyk.com/api/health/"