# EC2 Ubuntu Deployment Guide

## Installation Steps

### 1. Initial EC2 Setup

```bash
# SSH into your EC2 instance
ssh -i your-key.pem ubuntu@your-ec2-ip

# Update system packages
sudo apt-get update
sudo apt-get upgrade -y
```

### 2. Install Docker and Docker Compose

```bash
# Add Docker's official GPG key:
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add ubuntu user to docker group
sudo usermod -aG docker ubuntu

# Enable Docker to start on boot
sudo systemctl enable docker

# Log out and back in for group changes to take effect
exit
# SSH back in
```

### 3. Configure Permissions

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

### 4. Configure Pipeline Settings

```bash
docker-compose start sonarqube

# Generate token api
curl -u "USER_NAME:PASS" -X POST \
  "http://YOUR_SONAR_HOST/api/user_tokens/generate" \
  -d "name=my-ci-token" \
  -d "type=USER_TOKEN"
  
# Create webhook
curl -u "USER_NAME:PASS" -X POST \
  "http://YOUR_SONAR_HOST/api/webhooks/create" \
  -d "name=Global CI Webhook" \
  -d "url=https://your-endpoint.example.com/sonar-webhook" \
  -d "secret=YOUR_SECRET_STRING"

# Update SonarQube configuration
nano config/pipeline.yml

# Set your SonarQube token
# Update the host URL if needed (use internal Docker hostname or EC2 IP)
```

### 7. Build and Start Services

```bash
# Build all Docker images
docker-compose build

# Start all services
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f api
```

### 8. Verify Installation

```bash
# Check if API is running
curl http://localhost:8000

# Check SonarQube
curl http://localhost:9001

# Check all containers
docker-compose ps
```

### 9. Access from External IP

Update your EC2 Security Group to allow inbound traffic:

- Port 8000 (API)
- Port 3000 (Frontend)
- Port 9001 (SonarQube)

Access services:

- API: `http://your-ec2-ip:8000`
- Frontend: `http://your-ec2-ip:3000`
- SonarQube: `http://your-ec2-ip:9001`

## Monitoring and Maintenance

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f worker_scan

# Last 100 lines
docker-compose logs --tail=100 api
```

### Restart Services

```bash
# Restart specific service
docker-compose restart worker_scan

# Restart all
docker-compose restart

# Stop and start (clears container state)
docker-compose down
docker-compose up -d
```

### Check Disk Usage

```bash
# Check Docker disk usage
docker system df

# Check data directory size
du -sh ~/build-commit-pipeline/data/

# Clean up old Docker images
docker system prune -a
```

## Performance Tuning for EC2

### 1. Adjust Worker Concurrency

Edit `docker-compose.yml`:

```yaml
worker_scan:
  command: celery -A app.celery_app.celery_app worker --loglevel=info -Q pipeline.scan -n scan.%h -c 2  # Reduce from 4 to 2 for smaller instances
```

### 2. Limit SonarScanner Memory

```yaml
worker_scan:
  environment:
    SONAR_SCANNER_OPTS: "-Xmx1g -Xms256m"  # Reduce for smaller EC2 instances
```

### 3. Set Docker Memory Limits

```yaml
worker_scan:
  deploy:
    resources:
      limits:
        memory: 2G
      reservations:
        memory: 1G
```
