#!/usr/bin/env bash
# Git-based deploy for DS Intelligence — run ON THE SERVER:  ~/ds-engine/deploy.sh
#
# Pulls main, installs deps, rebuilds the Next.js frontend, restarts both
# systemd services. Secrets live in backend/.env (gitignored) and are never
# touched by git, so a deploy never disturbs them.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

echo "→ sync to origin/main (hard reset; discards local lockfile drift)"
git fetch origin main
git reset --hard origin/main

echo "→ backend deps"
backend/venv/bin/pip install -q -r backend/requirements.txt

echo "→ frontend build"
# Injeta o short SHA no build para o rótulo de versão (NEXT_PUBLIC_BUILD_SHA).
SHA="$(git rev-parse --short=7 HEAD)"
( cd frontend && npm install --no-audit --no-fund && NEXT_PUBLIC_BUILD_SHA="$SHA" npm run build )

echo "→ restart services"
sudo systemctl restart ds-intelligence
sudo systemctl restart ds-intelligence-frontend

echo "✓ deployed: $(git log --oneline -1)"
