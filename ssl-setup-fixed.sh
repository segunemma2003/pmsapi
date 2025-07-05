#!/bin/bash

set -e

echo "🔐 Fixed SSL Setup for api.oifyk.com"

# Check if we're in the right directory
if [ ! -f "docker-compose.production.yml" ]; then
    echo "❌ Please run this script from the project root directory"
    exit 1
fi

DC_CMD="docker compose --env-file .env.production -f docker-compose.production.yml"

echo "🔍 Step 1: Ensure services are running..."

# Make sure web service is running
if ! curl -f http://localhost:8000/api/health/ > /dev/null 2>&1; then
    echo "❌ Web service not responding. Starting web service..."
    $DC_CMD up -d web
    
    echo "⏳ Waiting for web service..."
    timeout=60
    counter=0
    while ! curl -f http://localhost:8000/api/health/ > /dev/null 2>&1 && [ $counter -lt $timeout ]; do
        echo "Waiting for web service... ($counter/$timeout)"
        sleep 2
        counter=$((counter + 2))
    done
    
    if [ $counter -ge $timeout ]; then
        echo "❌ Web service failed to start"
        exit 1
    fi
fi

echo "✅ Web service is ready"

echo "🔧 Step 2: Switch to HTTP-only nginx configuration..."

# Stop nginx
echo "🛑 Stopping nginx..."
$DC_CMD stop nginx

# Copy HTTP-only configuration
echo "📋 Applying HTTP-only nginx configuration..."
cp nginx-http-only.conf nginx-initial.conf

# Make sure certbot directories exist with proper permissions
echo "📁 Setting up certbot directories..."
mkdir -p certbot/conf certbot/www
sudo chown -R $USER:$USER certbot/
mkdir -p certbot/www/.well-known/acme-challenge
chmod -R 755 certbot/

# Start nginx with HTTP-only config
echo "🌐 Starting nginx with HTTP-only configuration..."
$DC_CMD up -d nginx

# Wait for nginx to start
echo "⏳ Waiting for nginx to start..."
sleep 10

# Test that nginx is working
echo "🧪 Step 3: Testing HTTP connectivity..."
if curl -f http://localhost/api/health/ > /dev/null 2>&1; then
    echo "✅ Local HTTP working"
else
    echo "❌ Local HTTP failed - checking nginx logs..."
    $DC_CMD logs --tail=20 nginx
    exit 1
fi

# Test challenge directory access
echo "🧪 Testing challenge directory..."
echo "test-challenge-file" > certbot/www/.well-known/acme-challenge/test
if curl -f http://localhost/.well-known/acme-challenge/test > /dev/null 2>&1; then
    echo "✅ Challenge directory accessible"
    rm certbot/www/.well-known/acme-challenge/test
else
    echo "❌ Challenge directory not accessible"
    echo "Testing from outside..."
    curl -v http://api.oifyk.com/.well-known/acme-challenge/test || true
    echo "Checking nginx logs..."
    $DC_CMD logs --tail=10 nginx
    exit 1
fi

echo "🔐 Step 4: Obtaining SSL certificates..."

# Try to obtain certificates using webroot method
echo "📜 Running certbot with webroot method..."
$DC_CMD run --rm certbot \
    certonly \
    --webroot \
    -w /var/www/certbot \
    --email "${ADMIN_EMAIL:-admin@oifyk.com}" \
    --agree-tos \
    --no-eff-email \
    --force-renewal \
    -d api.oifyk.com \
    --non-interactive \
    --verbose

if [ $? -eq 0 ]; then
    echo "✅ SSL certificates obtained successfully!"
else
    echo "❌ Webroot method failed. Trying standalone method..."
    
    # Stop nginx for standalone method
    $DC_CMD stop nginx
    
    # Try standalone method
    $DC_CMD run --rm -p 80:80 certbot \
        certonly \
        --standalone \
        --email "${ADMIN_EMAIL:-admin@oifyk.com}" \
        --agree-tos \
        --no-eff-email \
        --force-renewal \
        -d api.oifyk.com \
        --non-interactive \
        --verbose
    
    if [ $? -eq 0 ]; then
        echo "✅ SSL certificates obtained with standalone method!"
    else
        echo "❌ Both webroot and standalone methods failed"
        echo "🔄 Restarting nginx with HTTP configuration..."
        $DC_CMD up -d nginx
        exit 1
    fi
fi

echo "🔧 Step 5: Switching to SSL configuration..."

# Stop nginx
$DC_CMD stop nginx

# Check if certificates exist
if [ -f "certbot/conf/live/api.oifyk.com/fullchain.pem" ]; then
    echo "✅ SSL certificates found"
    
    # Show certificate info
    echo "📋 Certificate information:"
    openssl x509 -in certbot/conf/live/api.oifyk.com/fullchain.pem -text -noout | grep -E "(Subject:|Not After)" || true
    
    # Copy SSL configuration to main nginx config
    echo "🔄 Applying SSL nginx configuration..."
    cp nginx-ssl.conf nginx-initial.conf
    
else
    echo "❌ SSL certificates not found in expected location"
    ls -la certbot/conf/live/ || echo "No live certificates directory"
    exit 1
fi

# Start nginx with SSL configuration
echo "🚀 Starting nginx with SSL configuration..."
$DC_CMD up -d nginx

# Wait for nginx to start
echo "⏳ Waiting for nginx with SSL..."
sleep 15

echo "🧪 Step 6: Testing SSL connectivity..."

# Test local HTTP (should redirect to HTTPS)
echo "Testing HTTP to HTTPS redirect..."
http_response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/api/health/ || echo "000")
if [ "$http_response" = "301" ] || [ "$http_response" = "302" ]; then
    echo "✅ HTTP to HTTPS redirect working (got $http_response)"
else
    echo "⚠️ HTTP redirect not working as expected (got $http_response)"
fi

# Test local HTTPS
echo "Testing local HTTPS..."
if curl -f -k https://localhost/api/health/ > /dev/null 2>&1; then
    echo "✅ Local HTTPS working"
else
    echo "❌ Local HTTPS failed"
    echo "Checking nginx logs..."
    $DC_CMD logs --tail=20 nginx
fi

# Test external HTTPS
echo "Testing external HTTPS..."
if curl -f https://api.oifyk.com/api/health/ > /dev/null 2>&1; then
    echo "✅ External HTTPS working"
else
    echo "ℹ️ External HTTPS not yet available (may need DNS propagation)"
    echo "You can test manually: curl -v https://api.oifyk.com/api/health/"
fi

echo "⚙️ Step 7: Setting up certificate auto-renewal..."

# Start the certificate renewal service
$DC_CMD up -d certbot-renew

echo "🎉 SSL setup completed successfully!"

echo ""
echo "📋 Final Status:"
echo "  HTTP Response:  $(curl -s -o /dev/null -w '%{http_code}' http://api.oifyk.com/api/health/ 2>/dev/null || echo 'Failed')"
echo "  HTTPS Response: $(curl -s -o /dev/null -w '%{http_code}' https://api.oifyk.com/api/health/ 2>/dev/null || echo 'Failed')"
echo ""
echo "🔧 Useful commands:"
echo "  Check certificates: openssl x509 -in certbot/conf/live/api.oifyk.com/fullchain.pem -text -noout | grep -E '(Subject:|Not After)'"
echo "  Renew certificates: $DC_CMD run --rm certbot renew"
echo "  View nginx logs: $DC_CMD logs nginx"
echo "  Restart nginx: $DC_CMD restart nginx"