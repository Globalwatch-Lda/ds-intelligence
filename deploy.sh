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

# Que serviços reiniciar. O MESMO deploy.sh serve os três checkouts da box, por
# isso os nomes têm de sair do checkout — não podem estar fixos.
# Estiveram fixos em ds-intelligence* até 31 jul 2026: um deploy do Loulé
# reiniciava a PRODUÇÃO da Ramada e deixava o próprio Loulé a correr código
# antigo (o ds-loule-frontend esteve 2 dias sem reiniciar, sem ninguém notar).
case "$(basename "$PWD")" in
  ds-engine)         API=ds-intelligence;         WEB=ds-intelligence-frontend ;;
  ds-engine-loule)   API=ds-loule;                WEB=ds-loule-frontend ;;
  ds-engine-staging) API=ds-intelligence-staging; WEB=ds-intelligence-frontend-staging ;;
  *) echo "✗ checkout desconhecido ($PWD) — não sei que serviços reiniciar"; exit 1 ;;
esac

echo "→ restart services ($API, $WEB)"
sudo systemctl restart "$API"
sudo systemctl restart "$WEB"

echo "✓ deployed: $(git log --oneline -1)"
