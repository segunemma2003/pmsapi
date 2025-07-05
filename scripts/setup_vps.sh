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
    nginx \
    certbot \
    python3-certbot-nginx \
    ufw \
    htop \
    fail2ban \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release

# Install Docker (official method)
echo "🐳 Installing Docker..."
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Install Docker Compose (standalone)
echo "📦 Installing Docker Compose..."
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Start and enable Docker
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group
sudo usermod -aG docker $USER

# Test Docker installation
echo "🧪 Testing Docker installation..."
sudo docker run hello-world

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
    git clone https://github.com/segunemma2003/pmsapi.git .
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
echo "3. Logout and login again to apply Docker group membership"
echo "4. Run deployment with: ./scripts/deploy.sh"