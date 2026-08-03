"""Dados iniciais de uma loja nova: catálogo, identidade e o primeiro utilizador.

Corre DENTRO do checkout da loja (usa o `.env` dela, logo o `DB_SCHEMA` e a
`APP_CRYPTO_KEY` certos). Invocado pelo `nova_loja.py`, mas pode ser corrido à
mão para acrescentar o utilizador inicial a uma instalação existente.

    cd ~/ds-engine-<loja>/backend
    venv/bin/python ../../ds-engine/scripts/seed_loja.py \\
        --numero 812 --nome "DS Crédito Faro" \\
        --crm-email loja@dsicredito.pt --crm-password ...

Idempotente: se a loja ou o utilizador já existirem, actualiza o que faz sentido
e não toca em passwords já definidas — para poder ser re-corrido sem medo.
"""
from __future__ import annotations

import argparse
import secrets
import string
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if (Path.cwd() / "app").exists():          # a correr de dentro do backend da loja
    BACKEND = Path.cwd()
sys.path.insert(0, str(BACKEND))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

from app.core.crypto import encrypt_secret, hash_password  # noqa: E402
from app.db import supabase  # noqa: E402


def password_legivel(n: int = 12) -> str:
    """Password inicial que se consegue ditar ao telefone (sem l/I/0/O)."""
    alfabeto = "".join(c for c in string.ascii_letters + string.digits if c not in "lI0O1")
    return "".join(secrets.choice(alfabeto) for _ in range(n)) + "!"


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed da loja + utilizador inicial.")
    ap.add_argument("--numero", required=True, help="agencyId do CrediDesk")
    ap.add_argument("--nome", required=True, help="nome da loja")
    ap.add_argument("--crm-email", required=True)
    ap.add_argument("--crm-password", required=True)
    ap.add_argument("--username", default="admin", help="utilizador inicial (default: admin)")
    ap.add_argument("--nome-utilizador", default=None, help="nome a mostrar do utilizador")
    args = ap.parse_args()

    sb = supabase()

    # 1) catálogo de lojas — partilhado por todas as instalações
    if not sb.table("lojas").select("numero").eq("numero", args.numero).limit(1).execute().data:
        sb.table("lojas").insert({"numero": args.numero, "nome": args.nome}).execute()
        print(f"  lojas: criada {args.numero} · {args.nome}")
    else:
        print(f"  lojas: {args.numero} já constava do catálogo")

    # 2) identidade desta instalação (linha única)
    existente = sb.table("loja_config").select("id, numero").eq("id", 1).limit(1).execute().data
    if existente:
        sb.table("loja_config").update({"numero": args.numero, "nome": args.nome}).eq("id", 1).execute()
    else:
        sb.table("loja_config").insert({"id": 1, "numero": args.numero, "nome": args.nome}).execute()
    print(f"  loja_config: esta instalação é a loja {args.numero}")

    # 3) utilizador inicial com as credenciais do CRM
    #    Diretor de loja: vê a loja toda e pode criar os restantes utilizadores.
    ja = sb.table("platform_users").select("id, password_hash").eq("username", args.username).limit(1).execute().data
    cred = {
        "crm_username": args.crm_email,
        "crm_password_enc": encrypt_secret(args.crm_password),
        "role": "diretor_loja",
        "is_active": True,
        "nome": args.nome_utilizador or f"Administrador {args.nome}",
    }
    if ja:
        # Nunca reescrever uma password já definida — este script pode ser
        # re-corrido para actualizar as credenciais do CRM sem trancar ninguém fora.
        sb.table("platform_users").update(cred).eq("username", args.username).execute()
        print(f"  platform_users: {args.username} actualizado (password mantida)")
        senha = None
    else:
        senha = password_legivel()
        h, salt = hash_password(senha)
        sb.table("platform_users").insert(
            {**cred, "username": args.username, "password_hash": h, "password_salt": salt,
             "can_newsletter": True, "is_superadmin": False}
        ).execute()
        print(f"  platform_users: criado {args.username}")

    print("\n--- credenciais de entrada ---")
    print(f"  utilizador: {args.username}")
    print(f"  password  : {senha if senha else '(mantida — já existia)'}")
    print("  Peça para a trocar no primeiro acesso.\n")


if __name__ == "__main__":
    main()
