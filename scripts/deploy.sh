#!/bin/bash

set -e

echo "🚀 Starting deployment to production..."

# Check if Docker is installed and running
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "✅ Docker installed"
fi

# Ensure Docker service is running
if ! sudo systemctl is-active --quiet docker; then
    echo "🔄 Starting Docker service..."
    sudo systemctl start docker
    sudo systemctl enable docker
fi

# Check if docker compose is available
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
else
    echo "❌ Docker Compose not found. Installing..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    DOCKER_COMPOSE_CMD="docker-compose"
fi

echo "✅ Using Docker Compose command: $DOCKER_COMPOSE_CMD"

# Check if environment file exists
if [ ! -f ".env.production" ]; then
    echo "❌ .env.production file not found!"
    echo "📋 Please create .env.production file with your configuration"
    exit 1
fi

# Pull latest code
echo "📥 Pulling latest code..."
git fetch origin
git reset --hard origin/main

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p certbot/conf certbot/www logs db_backups ssl

# Stop existing services
echo "🛑 Stopping existing services..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml down || true

# Remove old containers and clean up
echo "🧹 Cleaning up old containers..."
docker system prune -f

# Build services
echo "🔨 Building services..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml build --no-cache

# Start database and redis first
echo "💾 Starting database and cache services..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml up -d db redis

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
timeout=60
counter=0
while ! $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml exec -T db pg_isready -U ${DB_USER:-oifyk_user} -d ${DB_NAME:-oifyk_production} > /dev/null 2>&1; do
    if [ $counter -eq $timeout ]; then
        echo "❌ Database failed to start within $timeout seconds"
        $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml logs db
        exit 1
    fi
    echo "⏳ Waiting for database... ($counter/$timeout)"
    sleep 2
    counter=$((counter + 1))
done
echo "✅ Database is ready"

# Start web service first (without nginx)
echo "🚀 Starting web application..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml up -d web

# Run migrations and setup
echo "📊 Running database migrations..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml exec -T web python manage.py migrate --noinput

echo "📁 Collecting static files..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml exec -T web python manage.py collectstatic --noinput

# Setup admin user if provided
if [ ! -z "$ADMIN_EMAIL" ] && [ ! -z "$ADMIN_PASSWORD" ]; then
    echo "👤 Setting up admin user..."
    $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml exec -T web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='$ADMIN_EMAIL').exists():
    user = User.objects.create_superuser('$ADMIN_EMAIL', '$ADMIN_EMAIL', '$ADMIN_PASSWORD')
    user.user_type = 'admin'
    user.status = 'active'
    user.full_name = 'System Administrator'
    user.save()
    print('✅ Admin user created')
else:
    print('ℹ️ Admin user already exists')
"
fi

# Wait for web service to be ready
echo "⏳ Waiting for web application to be ready..."
timeout=120
counter=0
while ! curl -f http://localhost:8000/api/health/ > /dev/null 2>&1; do
    if [ $counter -eq $timeout ]; then
        echo "❌ Web application failed to start within $timeout seconds"
        echo "📋 Web service logs:"
        $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml logs --tail=50 web
        exit 1
    fi
    echo "⏳ Waiting for web application... ($counter/$timeout)"
    sleep 2
    counter=$((counter + 1))
done
echo "✅ Web application is ready"

# Start nginx with simplified configuration (HTTP only first)
echo "🌐 Starting nginx with HTTP-only configuration..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml up -d nginx

# Wait for nginx to start
echo "⏳ Waiting for nginx to start..."
sleep 10

# Test HTTP connectivity
echo "🔍 Testing HTTP connectivity..."
if curl -f http://localhost/api/health/ > /dev/null 2>&1; then
    echo "✅ HTTP connectivity working"
else
    echo "❌ HTTP connectivity failed"
    echo "📋 Nginx logs:"
    $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml logs --tail=50 nginx
    exit 1
fi

# Start remaining services
echo "🚀 Starting remaining services..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml up -d celery

# Start celery-beat with retry logic
echo "📅 Starting celery beat scheduler..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml up -d celery-beat || {
    echo "⚠️ Celery beat failed to start, retrying..."
    sleep 5
    $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml up -d celery-beat
}

# Final health checks
echo "🔍 Running final health checks..."

# Check all services
echo "📊 Service status:"
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml ps

# Test connectivity
echo "🌐 Testing connectivity..."
if curl -f http://localhost/api/health/ > /dev/null 2>&1; then
    echo "✅ HTTP health check passed"
else
    echo "❌ HTTP health check failed"
    exit 1
fi

# Test internal connectivity
if curl -f http://localhost:8000/api/health/ > /dev/null 2>&1; then
    echo "✅ Direct web service connectivity working"
else
    echo "⚠️ Direct web service connectivity issue"
fi

echo "🎉 Deployment completed successfully!"
echo ""
echo "📋 Quick Commands:"
echo "  View logs: $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml logs -f"
echo "  Restart services: $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml restart"
echo "  Check status: $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml ps"
echo ""
echo "🌐 Your API should be available at:"
echo "  HTTP: http://api.oifyk.com"
echo "  ⚠️ HTTPS: Run SSL setup separately with: ./scripts/ssl-setup.sh"