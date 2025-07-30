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

# ⚠️ IMPORTANT: Stop containers but PRESERVE VOLUMES (database data)
echo "🛑 Stopping containers (preserving database data)..."
$DC_CMD -f docker-compose.production.yml down --remove-orphans || true
$DC_CMD -f docker-compose.pipeline.yml down --remove-orphans || true

# Remove any orphaned containers with our project names (but keep volumes)
echo "🗑️ Removing orphaned containers..."
docker container rm -f oifyk_nginx oifyk_web oifyk_db oifyk_redis oifyk_celery oifyk_celery_beat oifyk_certbot 2>/dev/null || true

# Remove any orphaned networks (but keep volumes)
echo "🌐 Cleaning up networks..."
docker network rm oifyk_oifyk_network 2>/dev/null || true

# ⚠️ IMPORTANT: Prune unused Docker resources BUT PRESERVE VOLUMES
echo "🧽 Pruning unused Docker resources (preserving volumes)..."
docker system prune -f

# Optional: Create database backup before deployment
echo "💾 Creating database backup (if database exists)..."
if docker volume ls | grep -q "oifyk_postgres_data"; then
    BACKUP_FILE="db_backups/backup_$(date +%Y%m%d_%H%M%S).sql"
    mkdir -p db_backups
    
    # Try to backup existing database
    $DC_CMD -f docker-compose.production.yml run --rm db pg_dump -h db -U $DB_USER -d $DB_NAME > "$BACKUP_FILE" 2>/dev/null || {
        echo "⚠️ Could not create backup (database might not be running)"
        rm -f "$BACKUP_FILE"
    }
    
    if [ -f "$BACKUP_FILE" ]; then
        echo "✅ Database backup created: $BACKUP_FILE"
        
        # Keep only last 5 backups
        ls -t db_backups/*.sql 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null || true
    fi
fi

# Build and start services
echo "🔨 Building and starting services..."
$DC_CMD -f docker-compose.production.yml build --no-cache --pull
$DC_CMD -f docker-compose.production.yml up -d

# Wait for database
echo "⏳ Waiting for database..."
timeout=60
counter=0
while ! $DC_CMD -f docker-compose.production.yml exec -T db pg_isready -U $(grep DB_USER .env.production | cut -d'=' -f2) -d $(grep DB_NAME .env.production | cut -d'=' -f2) > /dev/null 2>&1; do
    if [ $counter -eq $timeout ]; then
        echo "❌ Database failed to start"
        $DC_CMD -f docker-compose.production.yml logs db
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
$DC_CMD -f docker-compose.production.yml exec -T web python manage.py migrate --noinput

# Initialize database if needed
echo "🔧 Initializing database..."
$DC_CMD -f docker-compose.production.yml exec -T web python manage.py check --deploy || true

echo "📁 Collecting static files..."
$DC_CMD -f docker-compose.production.yml exec -T web python manage.py collectstatic --noinput

# Wait for web service
echo "⏳ Waiting for web service..."
timeout=60
counter=0
while ! curl -f http://localhost:8000/api/health/ > /dev/null 2>&1; do
    if [ $counter -eq $timeout ]; then
        echo "❌ Web service failed to start"
        $DC_CMD -f docker-compose.production.yml logs web
        exit 1
    fi
    sleep 2
    counter=$((counter + 1))
done

echo "✅ Web service is ready"

# Test final connectivity
echo "🔍 Testing service health..."
sleep 5

# Test web service health (internal)
if curl -f http://localhost:8000/api/health/ > /dev/null 2>&1; then
    echo "✅ Web service health check passed"
else
    echo "⚠️ Web service health check failed - checking logs..."
    $DC_CMD -f docker-compose.production.yml logs web
fi

# Test external domain health check - try HTTPS first, then HTTP
if curl -f https://api.oifyk.com/api/health/simple/ > /dev/null 2>&1; then
    echo "✅ External domain health check passed (HTTPS)"
elif curl -f http://api.oifyk.com/api/health/simple/ > /dev/null 2>&1; then
    echo "✅ External domain health check passed (HTTP)"
else
    echo "⚠️ External domain health check failed - checking logs..."
    $DC_CMD -f docker-compose.production.yml logs nginx
fi

# Test database connectivity
if $DC_CMD -f docker-compose.production.yml exec -T db pg_isready -U $(grep DB_USER .env.production | cut -d'=' -f2) -d $(grep DB_NAME .env.production | cut -d'=' -f2) > /dev/null 2>&1; then
    echo "✅ Database health check passed"
else
    echo "⚠️ Database health check failed"
fi

# Test Redis connectivity
if $DC_CMD -f docker-compose.production.yml exec -T redis redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis health check passed"
else
    echo "⚠️ Redis health check failed"
fi

echo "🎉 Deployment completed successfully!"

# Show service status
echo "📊 Service status:"
$DC_CMD -f docker-compose.production.yml ps

# Check container health
echo "🔍 Container health check:"
containers=("oifyk_web" "oifyk_db" "oifyk_redis" "oifyk_nginx" "oifyk_celery" "oifyk_celery_beat")
for container in "${containers[@]}"; do
    if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q "$container"; then
        status=$(docker ps --format "table {{.Names}}\t{{.Status}}" | grep "$container" | awk '{print $2}')
        echo "✅ $container: $status"
    else
        echo "❌ $container: Not running"
    fi
done

# Show volume status
echo "📦 Volume status:"
docker volume ls | grep -E "(postgres_data|redis_data)"

echo ""
echo "🌐 Your API is available at:"
echo "  HTTPS: https://api.oifyk.com"
echo "  Admin: https://api.oifyk.com/admin/"
echo "  Health: https://api.oifyk.com/api/health/"
echo "  Simple Health: https://api.oifyk.com/api/health/simple/"

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
echo ""
echo "💡 Database persistence info:"
echo "  - Database data is stored in Docker volume 'oifyk_postgres_data'"
echo "  - Backups are stored in ./db_backups/"
echo "  - To manually backup: docker compose -f docker-compose.production.yml exec db pg_dump -U $DB_USER $DB_NAME > backup.sql"
echo "  - To restore: docker compose -f docker-compose.production.yml exec -T db psql -U $DB_USER $DB_NAME < backup.sql"
