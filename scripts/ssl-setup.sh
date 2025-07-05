#!/bin/bash

set -e

echo "🔐 Setting up SSL certificates for api.oifyk.com..."

# Check if we're in the right directory
if [ ! -f "docker-compose.production.yml" ]; then
    echo "❌ Please run this script from the project root directory"
    exit 1
fi

# Docker compose command
DC_CMD="docker compose --env-file .env.production -f docker-compose.production.yml"

# Ensure web service is running
echo "🔍 Checking if web service is running..."
if ! curl -f http://localhost:8000/api/health/ > /dev/null 2>&1; then
    echo "❌ Web service is not responding. Please run deployment first."
    exit 1
fi

# Ensure nginx is running with HTTP configuration
echo "🔍 Checking nginx status..."
if ! curl -f http://localhost/api/health/ > /dev/null 2>&1; then
    echo "❌ Nginx is not responding on HTTP. Please check deployment."
    exit 1
fi

echo "✅ Services are ready for SSL setup"

# Create necessary directories
mkdir -p certbot/conf certbot/www

# Stop nginx temporarily for certificate generation
echo "🛑 Temporarily stopping nginx for certificate generation..."
$DC_CMD stop nginx

# Generate SSL certificates using standalone method
echo "📜 Generating SSL certificates..."
$DC_CMD run --rm -p 80:80 certbot \
    certonly \
    --standalone \
    --email "${ADMIN_EMAIL:-admin@oifyk.com}" \
    --agree-tos \
    --no-eff-email \
    --force-renewal \
    -d api.oifyk.com \
    --non-interactive

if [ $? -eq 0 ]; then
    echo "✅ SSL certificates generated successfully"
else
    echo "❌ SSL certificate generation failed"
    echo "🔄 Restarting nginx with HTTP-only configuration..."
    $DC_CMD up -d nginx
    exit 1
fi

# Update nginx configuration to use SSL
echo "🔧 Updating nginx configuration for SSL..."
# Copy SSL configuration over the initial configuration
if [ -f "nginx-ssl.conf" ]; then
    docker cp nginx-ssl.conf $(docker ps -q -f name=oifyk_nginx):/etc/nginx/nginx.conf
    echo "✅ SSL configuration copied"
else
    echo "⚠️ nginx-ssl.conf not found, nginx will continue with HTTP"
fi

# Restart nginx with SSL configuration
echo "🔄 Restarting nginx with SSL configuration..."
$DC_CMD up -d nginx

# Wait for nginx to restart
sleep 10

# Test SSL connectivity
echo "🧪 Testing SSL connectivity..."
if curl -f -k https://localhost/api/health/ > /dev/null 2>&1; then
    echo "✅ HTTPS is working locally"
else
    echo "⚠️ HTTPS not working locally, checking configuration..."
    $DC_CMD logs --tail=20 nginx
fi

# Test external SSL if DNS is configured
echo "🌐 Testing external SSL connectivity..."
if curl -f https://api.oifyk.com/api/health/ > /dev/null 2>&1; then
    echo "✅ External HTTPS is working"
else
    echo "ℹ️ External HTTPS not yet available (may need DNS propagation)"
fi

# Set up auto-renewal
echo "⚙️ Setting up automatic certificate renewal..."
$DC_CMD up -d certbot-renew

# Show certificate info
echo "📋 Certificate information:"
if [ -f "certbot/conf/live/api.oifyk.com/fullchain.pem" ]; then
    openssl x509 -in certbot/conf/live/api.oifyk.com/fullchain.pem -text -noout | grep -E "(Subject:|Not After)"
else
    echo "⚠️ Certificate file not found in expected location"
fi

echo "🎉 SSL setup completed!"
echo ""
echo "📋 SSL Status:"
echo "  Local HTTP:  $(curl -s -o /dev/null -w '%{http_code}' http://localhost/api/health/ || echo 'Failed')"
echo "  Local HTTPS: $(curl -s -o /dev/null -w '%{http_code}' -k https://localhost/api/health/ || echo 'Failed')"
echo "  External:    $(curl -s -o /dev/null -w '%{http_code}' https://api.oifyk.com/api/health/ || echo 'Failed')"