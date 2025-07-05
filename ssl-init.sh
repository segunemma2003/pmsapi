#!/bin/sh

set -e

echo "🔧 Starting SSL initialization..."

# Domain and email for certificates
DOMAIN="api.oifyk.com"
EMAIL="${ADMIN_EMAIL:-admin@oifyk.com}"

# Paths
CERT_PATH="/etc/letsencrypt/live/$DOMAIN"
NGINX_CONF="/etc/nginx/nginx.conf"
NGINX_SSL_CONF="/etc/nginx/nginx-ssl.conf"

# Function to check if certificates exist and are valid
check_certificates() {
    if [ -f "$CERT_PATH/fullchain.pem" ] && [ -f "$CERT_PATH/privkey.pem" ]; then
        # Check if certificate is valid (not expired)
        if openssl x509 -checkend 86400 -noout -in "$CERT_PATH/fullchain.pem" >/dev/null 2>&1; then
            echo "✅ Valid SSL certificates found"
            return 0
        else
            echo "⚠️ SSL certificates found but expiring soon or expired"
            return 1
        fi
    else
        echo "❌ No SSL certificates found"
        return 1
    fi
}

# Function to start nginx with HTTP-only configuration
start_nginx_http() {
    echo "🌐 Starting nginx with HTTP-only configuration for certificate generation..."
    nginx -g "daemon off;" &
    NGINX_PID=$!
    echo "Nginx HTTP started with PID: $NGINX_PID"
    
    # Wait for nginx to be ready
    for i in $(seq 1 30); do
        if curl -f http://localhost/api/health/ >/dev/null 2>&1; then
            echo "✅ Nginx HTTP is ready"
            return 0
        fi
        echo "⏳ Waiting for nginx to be ready... ($i/30)"
        sleep 2
    done
    
    echo "❌ Nginx failed to start properly"
    return 1
}

# Function to obtain SSL certificates
obtain_certificates() {
    echo "🔐 Obtaining SSL certificates from Let's Encrypt..."
    
    # Ensure certbot directories exist
    mkdir -p /var/www/certbot
    mkdir -p /etc/letsencrypt
    
    # Wait for certbot service to be available
    echo "⏳ Waiting for certbot service..."
    sleep 10
    
    # Try to obtain certificate
    if docker run --rm \
        -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
        -v "$(pwd)/certbot/www:/var/www/certbot" \
        --network oifyk_network \
        certbot/certbot \
        certonly \
        --webroot \
        -w /var/www/certbot \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        --force-renewal \
        -d "$DOMAIN" \
        --non-interactive; then
        echo "✅ SSL certificates obtained successfully"
        return 0
    else
        echo "❌ Failed to obtain SSL certificates"
        return 1
    fi
}

# Function to reload nginx with SSL configuration
reload_nginx_ssl() {
    echo "🔒 Reloading nginx with SSL configuration..."
    
    if [ -f "$NGINX_SSL_CONF" ]; then
        cp "$NGINX_SSL_CONF" "$NGINX_CONF"
        
        # Test nginx configuration
        if nginx -t; then
            nginx -s reload
            echo "✅ Nginx reloaded with SSL configuration"
            return 0
        else
            echo "❌ Nginx SSL configuration test failed"
            return 1
        fi
    else
        echo "❌ SSL configuration file not found"
        return 1
    fi
}

# Function to setup certificate auto-renewal
setup_auto_renewal() {
    echo "⚙️ Setting up automatic certificate renewal..."
    
    # Create renewal script
    cat > /etc/periodic/daily/renew-certs << 'EOF'
#!/bin/sh
echo "🔄 Checking for certificate renewal..."

# Renew certificates
docker run --rm \
    -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
    -v "$(pwd)/certbot/www:/var/www/certbot" \
    --network oifyk_network \
    certbot/certbot \
    renew --quiet --webroot -w /var/www/certbot

# If renewal was successful, reload nginx
if [ $? -eq 0 ]; then
    echo "✅ Certificates renewed, reloading nginx..."
    docker exec oifyk_nginx nginx -s reload
fi
EOF

    chmod +x /etc/periodic/daily/renew-certs
    echo "✅ Auto-renewal setup complete"
}

# Main execution
main() {
    echo "🚀 Initializing SSL setup for $DOMAIN..."
    
    # Start with HTTP-only configuration
    start_nginx_http
    
    # Check if we already have valid certificates
    if check_certificates; then
        echo "✅ Valid certificates found, switching to SSL configuration..."
        # Kill the HTTP-only nginx
        kill $NGINX_PID 2>/dev/null || true
        sleep 2
        
        # Load SSL configuration and start
        reload_nginx_ssl
        exec nginx -g "daemon off;"
    else
        echo "📜 Need to obtain new certificates..."
        
        # Wait a bit for nginx to fully start
        sleep 5
        
        # Try to obtain certificates
        if obtain_certificates; then
            echo "✅ Certificates obtained, switching to SSL..."
            
            # Kill the HTTP-only nginx
            kill $NGINX_PID 2>/dev/null || true
            sleep 2
            
            # Setup auto-renewal
            setup_auto_renewal
            
            # Load SSL configuration and start
            reload_nginx_ssl
            exec nginx -g "daemon off;"
        else
            echo "❌ Failed to obtain certificates, continuing with HTTP-only"
            echo "🔧 Please check your DNS settings and try again"
            
            # Continue with HTTP-only
            wait $NGINX_PID
        fi
    fi
}

# Handle signals properly
trap 'echo "🛑 Received signal, shutting down..."; kill $NGINX_PID 2>/dev/null || true; exit 0' TERM INT

# Run main function
main