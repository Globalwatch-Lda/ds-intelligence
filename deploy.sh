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

# O JWT do CrediDesk é mintado por Chromium headless (integrations/ds_crm/auth.py),
# e o browser NÃO vem no pip — vive em ~/.cache/ms-playwright. A migração para a
# Hetzner deixou-o para trás e as três ingestões noturnas falharam durante dois dias
# sem ninguém dar por isso. É barato garanti-lo aqui: quando já existe, sai num
# instante. Não bloqueia o deploy se falhar — a app serve na mesma, só a ingestão é
# que precisa dele. (As bibliotecas de sistema instalam-se uma vez, à parte:
#  venv/bin/python -m playwright install-deps chromium, com root.)
echo "→ browser do Playwright (mint do JWT do CRM)"
backend/venv/bin/python -m playwright install chromium >/dev/null 2>&1 || \
  echo "  ⚠ não foi possível garantir o Chromium — a sincronização do CRM pode falhar"

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
