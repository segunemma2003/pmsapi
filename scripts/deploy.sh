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

# Check if docker compose is available (newer versions use 'docker compose' instead of 'docker-compose')
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

# Pull latest code
git pull origin main

# Build and start services
$DOCKER_COMPOSE_CMD -f docker-compose.production.yml down || true
$DOCKER_COMPOSE_CMD -f docker-compose.production.yml build --no-cache
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml up -d
$DOCKER_COMPOSE_CMD -f docker-compose.production.yml up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 30

# Run migrations
$DOCKER_COMPOSE_CMD -f docker-compose.production.yml exec -T web python manage.py migrate --noinput

# Collect static files
$DOCKER_COMPOSE_CMD -f docker-compose.production.yml exec -T web python manage.py collectstatic --noinput

# Setup production environment with admin credentials from environment variables
if [ ! -z "$ADMIN_EMAIL" ] && [ ! -z "$ADMIN_PASSWORD" ]; then
    $DOCKER_COMPOSE_CMD -f docker-compose.production.yml exec -T web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='$ADMIN_EMAIL').exists():
    User.objects.create_superuser('$ADMIN_EMAIL', '$ADMIN_EMAIL', '$ADMIN_PASSWORD')
    print('Admin user created from environment variables')
else:
    print('Admin user already exists')
"
fi

# Health check
echo "🔍 Running health checks..."
sleep 10

# Check if the application is responding
if curl -f http://localhost/api/health/ || curl -f http://localhost:80/api/health/; then
    echo "✅ Deployment successful!"
else
    echo "❌ Health check failed!"
    echo "🔍 Checking service status..."
    $DOCKER_COMPOSE_CMD -f docker-compose.production.yml ps
    echo "📋 Recent logs:"
    $DOCKER_COMPOSE_CMD -f docker-compose.production.yml logs --tail=50 web
    exit 1
fi

echo "🎉 Deployment completed successfully!"
