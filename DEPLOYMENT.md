# EC2 Ubuntu Deployment Guide

## Prerequisites

- EC2 Ubuntu instance (20.04 or 22.04 LTS recommended)
- Minimum 4GB RAM, 2 vCPU (t3.medium or larger)
- 20GB+ storage for Docker images and git repositories
- Security group allowing ports: 22 (SSH), 8000 (API), 3000 (Frontend), 9001 (SonarQube)

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
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

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
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# Make it executable
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker --version
docker-compose --version
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
# Update SonarQube configuration
nano config/pipeline.yml

# Set your SonarQube token
# Update the host URL if needed (use internal Docker hostname or EC2 IP)
```

### 7. Build and Start Services

```bash
# Build all Docker images (this will take several minutes)
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

## Permission Issues and Solutions

### Issue: Git operations fail with "dubious ownership"

✅ **FIXED**: The Dockerfile now includes `git config --system safe.directory '*'`

### Issue: Cannot create directories in /app/data

✅ **FIXED**: Dockerfile creates directories with 777 permissions

### Issue: Permission denied when git cloning

✅ **FIXED**: 
- `HOME=/tmp` environment variable added to all services
- Git is installed in the Docker image
- Proper user/group configuration in docker-compose.yml

### Issue: Lock file conflicts between workers

✅ **HANDLED**: The fcntl.flock mechanism works on EC2 Ubuntu ext4 filesystem

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

### Monitor Git Worktrees

```bash
# Check worktree directory
ls -la ~/build-commit-pipeline/data/sonar-work/

# Count worktrees
find ~/build-commit-pipeline/data/sonar-work/ -name worktrees -type d -exec ls -la {} \;

# Check disk usage by worktrees
du -sh ~/build-commit-pipeline/data/sonar-work/*/worktrees/
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

## Backup Strategy

### Backup MongoDB Data

```bash
# Create backup
docker-compose exec mongo mongodump --username travis --password travis --authenticationDatabase admin --out /data/backup

# Copy from container to EC2
docker cp build_commit_mongo:/data/backup ./mongo-backup-$(date +%Y%m%d)

# Compress
tar -czf mongo-backup-$(date +%Y%m%d).tar.gz mongo-backup-$(date +%Y%m%d)
```

### Backup Git Repositories

```bash
# Backup the entire data directory
tar -czf data-backup-$(date +%Y%m%d).tar.gz ~/build-commit-pipeline/data/sonar-work/

# Upload to S3 (optional)
aws s3 cp data-backup-$(date +%Y%m%d).tar.gz s3://your-bucket/backups/
```

## Troubleshooting

### Container fails with "Permission denied"

```bash
# Check data directory permissions
ls -la ~/build-commit-pipeline/data/

# Re-run setup script
cd ~/build-commit-pipeline
./setup-permissions.sh

# Rebuild containers
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Git clone fails in container

```bash
# Verify git is installed in container
docker-compose exec api git --version

# Check git configuration
docker-compose exec api git config --list --show-origin

# Test git clone manually
docker-compose exec api git clone https://github.com/apache/commons-lang.git /tmp/test-repo
```

### Out of disk space

```bash
# Clean Docker system
docker system prune -a --volumes

# Remove old worktrees (be careful!)
find ~/build-commit-pipeline/data/sonar-work/*/worktrees/ -type d -mtime +7 -exec rm -rf {} +

# Clean old celery beat schedule
rm ~/build-commit-pipeline/data/celerybeat-schedule
```

### High CPU usage

```bash
# Check which containers are using CPU
docker stats

# Reduce worker concurrency
# Edit docker-compose.yml and reduce -c parameter

# Restart workers
docker-compose restart worker_scan
```

## Security Recommendations

1. **Use environment variables for secrets**:
   - Don't commit tokens to git
   - Use AWS Secrets Manager or EC2 instance metadata

2. **Limit network exposure**:
   - Only allow specific IPs in Security Groups
   - Use VPC and private subnets
   - Put services behind Application Load Balancer with HTTPS

3. **Regular updates**:
   ```bash
   # Update base images
   docker-compose pull
   docker-compose up -d
   
   # Update system packages
   sudo apt-get update && sudo apt-get upgrade -y
   ```

4. **Monitor logs for security issues**:
   ```bash
   # Check for failed authentication attempts
   docker-compose logs | grep -i "auth\|fail\|error"
   ```

## Auto-Start on EC2 Reboot

```bash
# Create systemd service
sudo nano /etc/systemd/system/build-commit-pipeline.service
```

Add:
```ini
[Unit]
Description=Build Commit Pipeline
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ubuntu/build-commit-pipeline
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
User=ubuntu

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl enable build-commit-pipeline
sudo systemctl start build-commit-pipeline
sudo systemctl status build-commit-pipeline
```
