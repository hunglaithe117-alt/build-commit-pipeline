#!/bin/bash
# Setup script to initialize data directories with correct permissions
# Run this once before starting Docker containers on EC2 Ubuntu

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"

# Get current user's UID and GID (for EC2 Ubuntu, typically ubuntu user is 1000:1000)
CURRENT_UID=$(id -u)
CURRENT_GID=$(id -g)

# Allow override via environment variables
APP_UID="${APP_UID:-${CURRENT_UID}}"
APP_GID="${APP_GID:-${CURRENT_GID}}"

echo "Setting up data directories for UID:GID = ${APP_UID}:${APP_GID}"
echo "Current user: $(whoami) (${CURRENT_UID}:${CURRENT_GID})"

# Create necessary directories
mkdir -p "${DATA_DIR}/uploads"
mkdir -p "${DATA_DIR}/exports"
mkdir -p "${DATA_DIR}/sonar-work"


# Set ownership and permissions
# On EC2, you typically have sudo access
if [ "${CURRENT_UID}" != "${APP_UID}" ] || [ "${CURRENT_GID}" != "${APP_GID}" ]; then
    echo "Changing ownership to ${APP_UID}:${APP_GID} (requires sudo)..."
    sudo chown -R "${APP_UID}:${APP_GID}" "${DATA_DIR}"
fi

# Set permissions to allow container access
sudo chmod -R 775 "${DATA_DIR}"

# Create .env file if it doesn't exist
if [ ! -f "${SCRIPT_DIR}/.env" ]; then
    echo "Creating .env file with detected UID/GID..."
    cat > "${SCRIPT_DIR}/.env" <<EOF
# Docker user configuration for EC2 Ubuntu
APP_UID=${APP_UID}
APP_GID=${APP_GID}
EOF
    echo ".env file created"
fi

echo "✅ Data directories configured successfully"
echo "ℹ️  Make sure to run 'docker-compose build' after first setup"
