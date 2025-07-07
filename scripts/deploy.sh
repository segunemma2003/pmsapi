#!/bin/bash

set -e

echo "🚀 Starting production deployment..."

if [ -f ".env.production" ]; then
    echo "🔄 Loading .env.production into shell"
    set -o allexport
    source .env.production
    set +o allexport
else
    echo "❌ .env.production file not found!"
    exit 1
fi

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

# Fix script permissions early
echo "🔧 Ensuring script permissions..."
chmod +x scripts/*.sh 2>/dev/null || true
chmod +x scripts/setup-ssl.sh 2>/dev/null || true

# Force cleanup of existing containers and networks
echo "🧹 Cleaning up existing containers..."
$DC_CMD -f docker-compose.production.yml down --volumes --remove-orphans || true

# Remove any orphaned containers with our project names
echo "🗑️ Removing orphaned containers..."
docker container rm -f oifyk_nginx oifyk_web oifyk_db oifyk_redis oifyk_celery oifyk_celery_beat oifyk_certbot 2>/dev/null || true

# Remove any orphaned networks
echo "🌐 Cleaning up networks..."
docker network rm oifyk_oifyk_network 2>/dev/null || true
docker rm -f oifyk_redis oifyk_web oifyk_db oifyk_celery oifyk_celery_beat oifyk_nginx oifyk_certbot 2>/dev/null || true

# Prune unused Docker resources
echo "🧽 Pruning unused Docker resources..."
docker system prune -f --volumes

# Build and start services
echo "🔨 Building and starting services..."
$DC_CMD  -f docker-compose.production.yml build --no-cache
$DC_CMD  -f docker-compose.production.yml up -d

# Wait for database
echo "⏳ Waiting for database..."
timeout=60
counter=0
while ! $DC_CMD  -f docker-compose.production.yml exec -T db pg_isready -U $(grep DB_USER .env.production | cut -d'=' -f2) -d $(grep DB_NAME .env.production | cut -d'=' -f2) > /dev/null 2>&1; do
    if [ $counter -eq $timeout ]; then
        echo "❌ Database failed to start"
        $DC_CMD  -f docker-compose.production.yml logs db
        exit 1
    fi
    sleep 2
    counter=$((counter + 1))
done

echo "✅ Database is ready"

# Wait a bit more for all services to stabilize
echo "⏳ Allowing services to stabilize..."
sleep 10

# Run migrations and setup
echo "📊 Running migrations..."
$DC_CMD  -f docker-compose.production.yml exec -T web python manage.py migrate --noinput

echo "📁 Collecting static files..."
$DC_CMD  -f docker-compose.production.yml exec -T web python manage.py collectstatic --noinput

# Wait for web service
echo "⏳ Waiting for web service..."
timeout=60
counter=0
while ! curl -f http://localhost:8000/api/health/ > /dev/null 2>&1; do
    if [ $counter -eq $timeout ]; then
        echo "❌ Web service failed to start"
        $DC_CMD  -f docker-compose.production.yml logs web
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
    $DC_CMD  -f docker-compose.production.yml logs nginx
fi

echo "🎉 Deployment completed successfully!"

# Show service status
echo "📊 Service status:"
$DC_CMD  -f docker-compose.production.yml ps

echo ""
echo "🌐 Your API is available at:"
echo "  HTTP: http://api.oifyk.com"
echo "  Admin: http://api.oifyk.com/admin/"
echo "  Health: http://api.oifyk.com/api/health/"

# Ask about SSL setup
echo ""
read -p "🔐 Would you like to set up SSL certificates now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "📜 Setting up SSL..."
    # Ensure SSL script has execute permissions
    chmod +x scripts/setup-ssl.sh
    # Verify permissions were set
    if [ -x "scripts/setup-ssl.sh" ]; then
        echo "✅ SSL script permissions verified"
        ./scripts/setup-ssl.sh
    else
        echo "❌ Failed to set execute permissions on SSL script"
        echo "💡 Run manually: chmod +x scripts/setup-ssl.sh && ./scripts/setup-ssl.sh"
    fi
fi

echo "✅ All done!"
