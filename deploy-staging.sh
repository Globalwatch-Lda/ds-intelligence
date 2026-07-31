#!/usr/bin/env bash
# Staging deploy — run ON THE SERVER from the staging checkout:
#   cd ~/ds-engine-staging && ./deploy-staging.sh
#
# Pulls the `staging` branch, rebuilds the frontend, restarts the staging
# systemd services. Staging shares the prod database (reads real data) but runs
# on its own ports (frontend 3006, backend 8006) behind an nginx block on
# 127.0.0.1:8080 — reach it via an SSH tunnel. Never touches prod.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

echo "→ sync to origin/staging (hard reset; discards local lockfile drift)"
git fetch origin staging
git reset --hard origin/staging

echo "→ frontend build"
( cd frontend && npm install --no-audit --no-fund && npm run build )

echo "→ restart staging services"
sudo systemctl restart ds-intelligence-staging
sudo systemctl restart ds-intelligence-frontend-staging

echo "✓ staging deployed: $(git log --oneline -1)"
