#!/bin/bash

set -e

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_BACKUP_FILE="$BACKUP_DIR/db_backup_$DATE.sql.gz"
MEDIA_BACKUP_FILE="$BACKUP_DIR/media_backup_$DATE.tar.gz"

echo "🗄️ Starting backup process..."

# Create backup directory
mkdir -p $BACKUP_DIR

# Database backup
echo "📊 Backing up database..."
docker-compose -f docker-compose.production.yml exec -T db pg_dump -U $DB_USER -d $DB_NAME | gzip > $DB_BACKUP_FILE

# Media files backup (if not using S3)
if [ "$USE_S3" != "True" ]; then
    echo "📁 Backing up media files..."
    tar -czf $MEDIA_BACKUP_FILE -C /app/media .
fi

# Clean up old backups (keep last 7 days)
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete

echo "✅ Backup completed successfully!"
echo "Database backup: $DB_BACKUP_FILE"
if [ "$USE_S3" != "True" ]; then
    echo "Media backup: $MEDIA_BACKUP_FILE"
fi
