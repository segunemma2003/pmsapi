#!/bin/bash

set -e

echo "🚀 Starting production deployment..."

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker first."
    exit 1
fi

# Determine Docker Compose command
if docker compose version &> /dev/null; then
    DC_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    DC_CMD="docker-compose"
else
    echo "❌ Docker Compose not found"
    exit 1
fi

# Check if environment file exists
if [ ! -f ".env.production" ]; then
    echo "❌ .env.production file not found!"
    exit 1
fi

echo "✅ Using Docker Compose: $DC_CMD"

# Stop existing services
echo "🛑 Stopping existing services..."
$DC_CMD --env-file .env.production -f docker-compose.production.yml down || true

# Build and start services
echo "🔨 Building and starting services..."
$DC_CMD --env-file .env.production -f docker-compose.production.yml build --no-cache
$DC_CMD --env-file .env.production -f docker-compose.production.yml up -d

# Wait for database
echo "⏳ Waiting for database..."
timeout=60
counter=0
while ! $DC_CMD --env-file .env.production -f docker-compose.production.yml exec -T db pg_isready -U oifyk_user -d oifyk_production > /dev/null 2>&1; do
    if [ $counter -eq $timeout ]; then
        echo "❌ Database failed to start"
        $DC_CMD --env-file .env.production -f docker-compose.production.yml logs db
        exit 1
    fi
    sleep 2
    counter=$((counter + 1))
done

echo "✅ Database is ready"

# Run migrations and setup
echo "📊 Running migrations..."
$DC_CMD --env-file .env.production -f docker-compose.production.yml exec -T web python manage.py migrate --noinput

echo "📁 Collecting static files..."
$DC_CMD --env-file .env.production -f docker-compose.production.yml exec -T web python manage.py collectstatic --noinput

# Wait for web service
echo "⏳ Waiting for web service..."
timeout=60
counter=0
while ! curl -f http://localhost:8000/api/health/ > /dev/null 2>&1; do
    if [ $counter -eq $timeout ]; then
        echo "❌ Web service failed to start"
        $DC_CMD --env-file .env.production -f docker-compose.production.yml logs web
        exit 1
    fi
    sleep 2
    counter=$((counter + 1))
done

echo "✅ Web service is ready"

# Test final connectivity
if curl -f http://localhost/api/health/ > /dev/null 2>&1; then
    echo "✅ HTTP connectivity working"
else
    echo "⚠️ HTTP connectivity not working - checking nginx..."
    $DC_CMD --env-file .env.production -f docker-compose.production.yml logs nginx
fi

echo "🎉 Deployment completed successfully!"

# Show service status
echo "📊 Service status:"
$DC_CMD --env-file .env.production -f docker-compose.production.yml ps

echo ""
echo "🌐 Your API is available at:"
echo "  HTTP: http://api.oifyk.com"
echo "  Admin: http://api.oifyk.com/admin/"
echo "  Health: http://api.oifyk.com/api/health/"