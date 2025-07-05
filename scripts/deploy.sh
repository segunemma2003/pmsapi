#!/bin/bash

set -e

echo "🚀 Starting deployment to production..."

# Pull latest code
git pull origin main

# Build and start services (using docker compose instead of docker-compose)
docker compose -f docker-compose.production.yml down
docker compose -f docker-compose.production.yml build --no-cache
docker compose -f docker-compose.production.yml up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 30

# Run migrations
docker compose -f docker-compose.production.yml exec web python manage.py migrate --noinput

# Collect static files
docker compose -f docker-compose.production.yml exec web python manage.py collectstatic --noinput

# Create superuser if doesn't exist
docker compose -f docker-compose.production.yml exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='admin@oifyk.com').exists():
    User.objects.create_superuser('admin@oifyk.com', 'admin@oifyk.com', 'secure-admin-password')
    print('Superuser created')
else:
    print('Superuser already exists')
"

# Setup production environment with admin credentials from environment variables
if [ ! -z "$ADMIN_EMAIL" ] && [ ! -z "$ADMIN_PASSWORD" ]; then
    docker compose -f docker-compose.production.yml exec web python manage.py shell -c "
    from django.contrib.auth import get_user_model
    User = get_user_model()
    if not User.objects.filter(email='$ADMIN_EMAIL').exists():
        User.objects.create_superuser('$ADMIN_EMAIL', '$ADMIN_EMAIL', '$ADMIN_PASSWORD')
        print('Admin user created from environment variables')
    else:
        print('Admin user already exists')
    "
fi

# Warm up cache
docker compose -f docker-compose.production.yml exec web python manage.py shell -c "
try:
    from utils.cache_utils import CacheManager
    CacheManager.warm_cache()
    print('Cache warmed up')
except Exception as e:
    print(f'Cache warm-up failed: {e}')
"

# Health check
echo "🔍 Running health checks..."
sleep 10

if curl -f http://localhost/api/health/; then
    echo "✅ Deployment successful!"
else
    echo "❌ Health check failed!"
    echo "🔍 Checking service status..."
    docker compose -f docker-compose.production.yml ps
    echo "📋 Recent logs:"
    docker compose -f docker-compose.production.yml logs --tail=50 web
    exit 1
fi

echo "🎉 Deployment completed successfully!"