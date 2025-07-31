#!/bin/bash

set -e

echo "🤖 Installing AI/ML dependencies..."

# Determine Docker Compose command
if docker compose version &> /dev/null; then
    DC_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    DC_CMD="docker-compose"
else
    echo "❌ Docker Compose not found"
    exit 1
fi

echo "✅ Using Docker Compose: $DC_CMD"

# Install AI dependencies in the running containers
echo "📦 Installing AI packages in web container..."
$DC_CMD -f docker-compose.production.yml exec web pip install -r requirements.ai.txt

echo "📦 Installing AI packages in celery container..."
$DC_CMD -f docker-compose.production.yml exec celery pip install -r requirements.ai.txt

echo "📦 Installing AI packages in celery-beat container..."
$DC_CMD -f docker-compose.production.yml exec celery-beat pip install -r requirements.ai.txt

# Download spaCy model
echo "📚 Downloading spaCy language model..."
$DC_CMD -f docker-compose.production.yml exec web python -m spacy download en_core_web_sm

# Update environment variables
echo "⚙️ Updating environment variables..."
sed -i 's/ENABLE_AI_FEATURES=False/ENABLE_AI_FEATURES=True/' .env.production
sed -i 's/DISABLE_AI_FEATURES=True/DISABLE_AI_FEATURES=False/' .env.production

# Restart services to pick up new environment
echo "🔄 Restarting services..."
$DC_CMD -f docker-compose.production.yml restart web celery celery-beat

echo "🎉 AI dependencies installed successfully!"
echo "💡 AI features are now enabled." 