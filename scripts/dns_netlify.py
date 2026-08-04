"""Registo DNS da loja nova, na zona synertia-gw.ai (Netlify).

O DNS era o único passo do instalador que ficava para o humano fazer noutro sítio
— e é o que bloqueia o certificado, portanto o que atrasa a loja a ficar de pé.
A zona é gerida pela Netlify (51 registos a 4 Ago 2026; `dscredito` e `dsloule`
são registos A para a box), e a API dá para a criar daqui.

    python3 scripts/dns_netlify.py --dominio dsalmancil.synertia-gw.ai --ip 2.28.6.0
    python3 scripts/dns_netlify.py --dominio ... --ip ... --dry-run

O token é lido, por esta ordem, de: --token, NETLIFY_TOKEN, /etc/ds-matrix/netlify.token.
Sem token, o instalador segue e diz que o registo ficou por criar — nunca falha
a instalação por causa disto.

Idempotente: se o registo já existir com o mesmo valor, não faz nada; se existir
com outro valor, avisa e NÃO o altera (apontar um domínio a outro sítio nunca
pode ser efeito lateral de instalar uma loja).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://api.netlify.com/api/v1"
ZONA_PADRAO = "synertia-gw.ai"
FICHEIRO_TOKEN = Path("/etc/ds-matrix/netlify.token")


def token_disponivel(explicito: str | None = None) -> str | None:
    if explicito:
        return explicito.strip()
    if os.environ.get("NETLIFY_TOKEN"):
        return os.environ["NETLIFY_TOKEN"].strip()
    if FICHEIRO_TOKEN.exists():
        return FICHEIRO_TOKEN.read_text(encoding="utf-8").strip()
    return None


def _pedir(caminho: str, token: str, metodo: str = "GET", corpo: dict | None = None):
    req = urllib.request.Request(
        f"{API}{caminho}",
        method=metodo,
        data=json.dumps(corpo).encode() if corpo else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        bruto = r.read().decode()
    return json.loads(bruto) if bruto else None


def zona_id(token: str, zona: str) -> str | None:
    for z in _pedir("/dns_zones", token) or []:
        if z.get("name") == zona:
            return z.get("id")
    return None


def garantir_registo(dominio: str, ip: str, *, token: str, zona: str = ZONA_PADRAO,
                     seco: bool = False) -> tuple[bool, str]:
    """(sucesso, mensagem). Não levanta — o instalador não pode cair por DNS."""
    try:
        zid = zona_id(token, zona)
        if not zid:
            return False, f"zona {zona} não encontrada nesta conta Netlify"
        registos = _pedir(f"/dns_zones/{zid}/dns_records", token) or []
        existente = next((r for r in registos if r.get("hostname") == dominio), None)
        if existente:
            if existente.get("value") == ip:
                return True, f"registo já existia e aponta para {ip}"
            return False, (f"já existe um registo {existente.get('type')} para {dominio} a apontar "
                           f"para {existente.get('value')} — não foi alterado; verifique à mão")
        if seco:
            return True, f"[plano] criar A {dominio} -> {ip}"
        _pedir(f"/dns_zones/{zid}/dns_records", token, "POST",
               {"type": "A", "hostname": dominio, "value": ip, "ttl": 3600})
        return True, f"registo A criado: {dominio} -> {ip}"
    except urllib.error.HTTPError as e:
        return False, f"API Netlify devolveu {e.code}: {e.read().decode()[:150]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"[:200]


def main() -> None:
    ap = argparse.ArgumentParser(description="Cria o registo A da loja na zona DNS.")
    ap.add_argument("--dominio", required=True)
    ap.add_argument("--ip", required=True)
    ap.add_argument("--zona", default=ZONA_PADRAO)
    ap.add_argument("--token")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = token_disponivel(args.token)
    if not token:
        sys.exit("Sem token Netlify (--token, NETLIFY_TOKEN ou /etc/ds-matrix/netlify.token).")
    ok, msg = garantir_registo(args.dominio, args.ip, token=token, zona=args.zona, seco=args.dry_run)
    print(("  ✓ " if ok else "  ✗ ") + msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
