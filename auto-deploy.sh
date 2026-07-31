#!/usr/bin/env bash
# Auto-deploy: corre o deploy.sh SÓ quando origin/main muda. Idempotente, com
# lock para não sobrepor builds. Instalado no EC2 via cron (a cada 2 min):
#   */2 * * * * /home/ubuntu/ds-engine/auto-deploy.sh
# Torna "merge para main = live em ~2 min", sem passos manuais.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
exec 9>/tmp/ds-autodeploy.lock
flock -n 9 || exit 0
git fetch origin main --quiet
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
[ "$LOCAL" = "$REMOTE" ] && exit 0
echo "==== $(date -u +%FT%TZ) auto-deploy ${LOCAL:0:7} -> ${REMOTE:0:7} ====" >> ~/ds-autodeploy.log
bash deploy.sh >> ~/ds-autodeploy.log 2>&1
echo "==== done $(date -u +%FT%TZ) ====" >> ~/ds-autodeploy.log
