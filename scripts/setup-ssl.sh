#!/bin/bash

set -e

echo "🔐 Setting up SSL certificates..."

DC_CMD="docker compose --env-file .env.production -f docker-compose.production.yml"

# Create directories
mkdir -p certbot/conf certbot/www

# Stop nginx temporarily
echo "🛑 Stopping nginx for certificate generation..."
$DC_CMD stop nginx

# Generate certificates
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
    echo "✅ SSL certificates generated"
    
    # Update nginx to use SSL configuration
    echo "🔧 Switching to SSL configuration..."
    cp nginx-ssl.conf nginx-initial.conf
    
    # Restart nginx with SSL
    $DC_CMD up -d nginx
    
    # Test SSL
    sleep 10
    if curl -f -k https://localhost/api/health/ > /dev/null 2>&1; then
        echo "✅ HTTPS is working"
    else
        echo "⚠️ HTTPS test failed"
    fi
    
    echo "🎉 SSL setup completed!"
else
    echo "❌ SSL certificate generation failed"
    # Restart nginx with HTTP config
    $DC_CMD up -d nginx
    exit 1
fi