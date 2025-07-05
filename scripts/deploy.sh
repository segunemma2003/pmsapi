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

# Create SSL initialization script
echo "🔧 Setting up SSL initialization..."
chmod +x ssl-init.sh

# Stop existing services
echo "🛑 Stopping existing services..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml down || true

# Remove old containers and images
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

# Start application services
echo "🚀 Starting application services..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml up -d web celery celery-beat

# Wait for application to be ready
echo "⏳ Waiting for application to be ready..."
timeout=60
counter=0
while ! curl -f http://localhost:8000/api/health/ > /dev/null 2>&1; do
    if [ $counter -eq $timeout ]; then
        echo "❌ Application failed to start within $timeout seconds"
        $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml logs web
        exit 1
    fi
    echo "⏳ Waiting for application... ($counter/$timeout)"
    sleep 2
    counter=$((counter + 1))
done
echo "✅ Application is ready"

# Run migrations
echo "📊 Running database migrations..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml exec -T web python manage.py migrate --noinput

# Collect static files
echo "📁 Collecting static files..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml exec -T web python manage.py collectstatic --noinput

# Setup production data
echo "⚙️ Setting up production environment..."
if [ ! -z "$ADMIN_EMAIL" ] && [ ! -z "$ADMIN_PASSWORD" ]; then
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
else
    echo "⚠️ ADMIN_EMAIL and ADMIN_PASSWORD not set, skipping admin user creation"
fi

# Start nginx with SSL initialization
echo "🌐 Starting nginx with SSL initialization..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml up -d nginx

# Wait for nginx to be ready
echo "⏳ Waiting for nginx to initialize SSL..."
timeout=120  # Extended timeout for SSL setup
counter=0
while ! curl -f http://localhost/api/health/ > /dev/null 2>&1 && [ $counter -lt $timeout ]; do
    echo "⏳ Waiting for nginx SSL initialization... ($counter/$timeout)"
    sleep 2
    counter=$((counter + 2))
done

if [ $counter -ge $timeout ]; then
    echo "⚠️ Nginx SSL initialization taking longer than expected"
    echo "📋 Checking nginx logs..."
    $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml logs nginx
else
    echo "✅ Nginx is ready"
fi

# Start automatic certificate renewal
echo "🔄 Starting automatic certificate renewal service..."
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml up -d certbot-renew

# Final health check
echo "🔍 Running final health checks..."

# Check HTTP health (should always work)
echo "🌐 Testing HTTP endpoint..."
if curl -f -m 10 http://localhost/api/health/ > /dev/null 2>&1; then
    echo "✅ HTTP health check passed"
    http_working=true
else
    echo "❌ HTTP health check failed"
    http_working=false
    HEALTH_FAILED=true
fi

# Check HTTPS health (may take time)
echo "🔒 Testing HTTPS endpoint..."
if curl -f -k -m 10 https://localhost/api/health/ > /dev/null 2>&1; then
    echo "✅ HTTPS health check passed"
    https_working=true
elif [ "$http_working" = true ]; then
    echo "ℹ️ HTTPS not yet available, but HTTP is working"
    echo "🔧 SSL certificates may still be initializing"
    https_working=false
else
    echo "❌ Both HTTP and HTTPS health checks failed"
    https_working=false
    HEALTH_FAILED=true
fi

# Test external connectivity (if DNS is set up)
echo "🌍 Testing external connectivity..."
if curl -f -m 15 http://api.oifyk.com/api/health/ > /dev/null 2>&1; then
    echo "✅ External HTTP connectivity working"
elif [ "$http_working" = true ]; then
    echo "ℹ️ Local HTTP working but external connectivity may need DNS setup"
else
    echo "⚠️ External HTTP connectivity not available"
fi

if curl -f -m 15 https://api.oifyk.com/api/health/ > /dev/null 2>&1; then
    echo "✅ External HTTPS connectivity working"
elif [ "$https_working" = true ]; then
    echo "ℹ️ Local HTTPS working but external HTTPS may need DNS setup"
else
    echo "ℹ️ External HTTPS not yet available (normal during initial setup)"
fi

# Show service status
echo "📊 Service status:"
$DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml ps

if [ "$HEALTH_FAILED" = true ]; then
    echo "❌ Health checks failed!"
    echo "🔍 Checking service logs..."
    echo "📋 Web service logs:"
    $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml logs --tail=50 web
    echo "📋 Nginx service logs:"
    $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml logs --tail=50 nginx
    exit 1
fi

# Show SSL certificate status
echo "🔐 SSL Certificate status:"
if [ -f "./certbot/conf/live/api.oifyk.com/fullchain.pem" ]; then
    echo "✅ SSL certificates are present"
    openssl x509 -in ./certbot/conf/live/api.oifyk.com/fullchain.pem -text -noout | grep -E "(Subject:|Not After :)"
else
    echo "⚠️ SSL certificates not yet obtained"
    echo "🔧 Check nginx logs for SSL initialization progress"
fi

# Setup log rotation
echo "📝 Setting up log rotation..."
sudo tee /etc/logrotate.d/oifyk > /dev/null <<EOF
/opt/oifyk/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    copytruncate
    su root root
}
EOF

echo "🎉 Deployment completed successfully!"
echo ""
echo "📋 Quick Commands:"
echo "  View logs: $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml logs -f"
echo "  Restart services: $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml restart"
echo "  Check status: $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml ps"
echo "  Update SSL: $DOCKER_COMPOSE_CMD --env-file .env.production -f docker-compose.production.yml restart nginx"
echo ""
echo "🌐 Your API should be available at:"
echo "  HTTP: http://api.oifyk.com"
echo "  HTTPS: https://api.oifyk.com (if SSL certificates were obtained)"