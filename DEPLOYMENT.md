## Installation Steps

### 1. Initial Setup

```bash
# SSH into your instance
ssh -i your-key.pem ubuntu@your-ec2-ip

# Update system packages
sudo apt-get update
sudo apt-get upgrade -y
```

### 2. Install Docker and Docker Compose

```bash
# Install Docker
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker compose-plugin

# Add ubuntu user to docker group
sudo usermod -aG docker ubuntu

# Enable Docker to start on boot
sudo systemctl enable docker

# Log out and back in for group changes to take effect
exit
# SSH back in
```

### 3. Install Docker Compose (standalone)

```bash
# Download Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker compose

# Make it executable
sudo chmod +x /usr/local/bin/docker compose

# Verify installation
docker --version
docker compose --version
```

### 4. Clone Your Repository

```bash
# Clone your project
cd ~
git clone https://github.com/yourusername/build-commit-pipeline.git
cd build-commit-pipeline
```

### 5. Configure Permissions

```bash
# Run the setup script (auto-detects ubuntu user UID/GID)
chmod +x setup-permissions.sh
./setup-permissions.sh

# Verify .env file was created
cat .env
# Should show:
# APP_UID=1000
# APP_GID=1000
```

### 6. Configure Pipeline Settings

```bash
# Create user token
curl -u "admin:admin" -X POST \
  "http://localhost:9001/api/user_tokens/generate" \
  -d "name=my-ci-token" \
  -d "type=USER_TOKEN"
  
#Create webhook
curl -u "ADMIN_TOKEN:" -X POST \
  "http://YOUR_SONAR_HOST/api/webhooks/create" \
  -d "name=Global CI Webhook" \
  -d "url=https://your-endpoint.example.com/sonar-webhook" \
  -d "secret=YOUR_SECRET_STRING"

# Update SonarQube configuration
nano config/pipeline.yml
```

### 7. Build and Start Services

```bash
# Build all Docker images (this will take several minutes)
docker compose build

# Start all services
docker compose up -d

# Check service status
docker compose ps

# View logs
docker compose logs -f api
```

### 8. Verify Installation

```bash
# Check if API is running
curl http://localhost:8000

# Check SonarQube
curl http://localhost:9001

# Check all containers
docker compose ps
```
