#!/bin/bash
# setup-server.sh — Initial server setup on Raspberry Pi
# Run once after deploy to configure systemd service

set -e

APP_DIR="/home/claude/o-running-info/running-tracker"

echo "[setup] Installing dependencies..."
sudo apt-get update
sudo apt-get install -y rsync sshpass python3-pip python3-venv

echo "[setup] Creating virtualenv..."
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "[setup] Creating data directory..."
mkdir -p "$APP_DIR/data"

echo "[setup] Installing systemd service..."
sudo cp running-tracker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable running-tracker
sudo systemctl restart running-tracker

echo "[setup] Checking status..."
sudo systemctl status running-tracker --no-pager

echo "[setup] Done! App should be available at http://<raspberry-ip>:8000"
