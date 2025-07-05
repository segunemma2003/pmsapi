#!/bin/bash

set -e

echo "🔧 Setting up VPS for OnlyIfYouKnow deployment..."

# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y \
    git \
    curl \
    wget \
    docker.io \
    docker-compose \
    nginx \
    certbot \
    python3-certbot-nginx \
    ufw \
    htop \
    fail2ban

# Start and enable Docker
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group
sudo usermod -aG docker $USER

# Create application directory
sudo mkdir -p /opt/oifyk
sudo chown -R $USER:$USER /opt/oifyk

# Create necessary directories
mkdir -p /opt/oifyk/{logs,db_backups,ssl}

# Set up firewall
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable

# Setup log rotation for application logs
sudo tee /etc/logrotate.d/oifyk > /dev/null <<EOF
/opt/oifyk/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 644 $USER $USER
}
EOF

# Clone repository (replace with your actual repo URL)
cd /opt/oifyk
if [ ! -d ".git" ]; then
    git clone https://github.com/yourusername/your-repo.git .
    git config pull.rebase false
else
    echo "Repository already exists, pulling latest changes..."
    git pull origin main
fi

# Make scripts executable
chmod +x scripts/*.sh

# Create environment file from template
if [ ! -f ".env.production" ]; then
    echo "⚠️  Please create .env.production file with your configuration"
    echo "📋 Template available in the repository"
fi

echo "✅ VPS setup completed!"
echo "📝 Next steps:"
echo "1. Configure .env.production file"
echo "2. Set up SSL certificates with: sudo certbot --nginx -d api.oifyk.com"
echo "3. Run deployment with: ./scripts/deploy.sh"