#!/bin/bash
set -e
echo "🚀 Hermes Deploy Starting..."

# Pull latest
cd /root/hermes
git pull origin main

# Build frontend
echo "📦 Building frontend..."
cd /root/hermes/frontend
npm run build

# Restart services
echo "🔄 Restarting services..."
systemctl restart hermes-dashboard
systemctl restart hermes-watcher
systemctl reload nginx

echo "✅ Deploy complete!"
echo "🌐 https://app.letagentscook.lol"
