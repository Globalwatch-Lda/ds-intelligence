#!/usr/bin/env bash
# Instala o comando `nova-loja` nesta box (uma vez por box).
#
#   sudo bash scripts/instalar-comando.sh
#
# Também deixa a lembrança na mensagem de entrada por SSH: quem entrar na box
# vê como se instala uma loja, sem ter de procurar no runbook.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

install -m 0755 nova-loja /usr/local/bin/nova-loja
echo "✓ comando instalado: nova-loja"

MOTD=/etc/update-motd.d/99-ds-matrix
cat > "$MOTD" <<'EOF'
#!/bin/sh
cat <<'TXT'

  DS Matrix — esta box serve as lojas em /home/ubuntu/ds-engine*
    nova-loja             instalar uma loja nova (pergunta o que precisa)
    nova-loja --dry-run   ver o plano sem tocar em nada

TXT
EOF
chmod +x "$MOTD"
echo "✓ lembrete acrescentado à entrada por SSH"
