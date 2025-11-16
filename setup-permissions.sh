#!/bin/bash
# Setup script to initialize data directories with correct permissions
# Run this once before starting Docker containers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"

# Get UID and GID from environment or use defaults
APP_UID="${APP_UID:-1000}"
APP_GID="${APP_GID:-1000}"

echo "Setting up data directories for UID:GID = ${APP_UID}:${APP_GID}"

# Create necessary directories
mkdir -p "${DATA_DIR}/uploads"
mkdir -p "${DATA_DIR}/exports"
mkdir -p "${DATA_DIR}/sonar-work"
mkdir -p "${DATA_DIR}/promtail"

# Set ownership and permissions
sudo chown -R "${APP_UID}:${APP_GID}" "${DATA_DIR}"
sudo chmod -R 775 "${DATA_DIR}"

echo "Data directories configured successfully"
