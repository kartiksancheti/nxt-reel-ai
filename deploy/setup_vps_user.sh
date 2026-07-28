#!/usr/bin/env bash
# ==============================================================================
# NXT Reel AI - VPS bootstrap script
#
# Creates a dedicated, isolated Linux user for this project so it never
# touches your other project's files, processes, or docker resources.
#
# Run as root (or with sudo) on your Ubuntu VPS:
#   sudo bash setup_vps_user.sh
# ==============================================================================
set -euo pipefail

PROJECT_USER="nxtreel"
PROJECT_DIR="/home/${PROJECT_USER}/nxt-reel-ai"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run this script as root (sudo bash setup_vps_user.sh)"
  exit 1
fi

echo "==> Creating system user '${PROJECT_USER}'"
if id "${PROJECT_USER}" &>/dev/null; then
  echo "    User already exists, skipping creation."
else
  useradd -m -s /bin/bash "${PROJECT_USER}"
  echo "    Created user ${PROJECT_USER}."
fi

echo "==> Adding ${PROJECT_USER} to the docker group (so it can run docker compose)"
if ! getent group docker >/dev/null; then
  groupadd docker
fi
usermod -aG docker "${PROJECT_USER}"

echo "==> Creating project directory structure"
mkdir -p "${PROJECT_DIR}"
mkdir -p "/home/${PROJECT_USER}/storage/uploads"
mkdir -p "/home/${PROJECT_USER}/storage/renders"
mkdir -p "/home/${PROJECT_USER}/storage/assets"
chown -R "${PROJECT_USER}:${PROJECT_USER}" "/home/${PROJECT_USER}"

echo "==> Setting up SSH access for ${PROJECT_USER} (optional but recommended)"
mkdir -p "/home/${PROJECT_USER}/.ssh"
if [ -f /root/.ssh/authorized_keys ]; then
  echo "    Copying your current authorized_keys so you can log in as ${PROJECT_USER} too."
  cp /root/.ssh/authorized_keys "/home/${PROJECT_USER}/.ssh/authorized_keys"
fi
chmod 700 "/home/${PROJECT_USER}/.ssh"
chmod 600 "/home/${PROJECT_USER}/.ssh/authorized_keys" 2>/dev/null || true
chown -R "${PROJECT_USER}:${PROJECT_USER}" "/home/${PROJECT_USER}/.ssh"

echo ""
echo "=================================================================="
echo " Done. Next steps:"
echo "   1. Switch to the new user:      su - ${PROJECT_USER}"
echo "   2. Copy/clone the project into: ${PROJECT_DIR}"
echo "   3. Copy .env.example to .env and fill in your secrets"
echo "   4. From ${PROJECT_DIR}, run:    docker compose up -d --build"
echo "=================================================================="
