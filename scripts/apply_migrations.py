"""Apply the ds-schema migrations to the new Supabase project via the Supavisor
session pooler. Idempotent (every DDL is `if not exists` / `add column if not
exists`). Connection params are read from argv to keep the password out of the
file. Run order matters: 007 alters clientes_real (created in 003)."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import psycopg

ORDER = [
    "001_schema.sql",
    "002_contactos_consultor.sql",
    "003_crm_real_mirror.sql",
    "004_processos_real.sql",
    "006_leads_real.sql",
    "007_consent.sql",
    "008_grants_and_expose.sql",
    "009_platform_users.sql",
    "010_source_account.sql",
    "011_source_accounts_array.sql",
    "012_acesso_loja_toda.sql",
    "013_perfis_loja.sql",
    "014_clientes_manager.sql",
    "015_triggers_fired_crm_ids.sql",
]

MIG_DIR = Path(__file__).resolve().parents[1] / "migrations"


def split_statements(sql: str):
    """Strip line comments first (a `--` comment may contain a ';'), then split on
    ';'. Our migrations have no dollar-quoted blocks or string-literal semicolons,
    so this is safe. Skip blank chunks."""
    no_comments = "\n".join(ln.split("--", 1)[0] for ln in sql.splitlines())
    for chunk in no_comments.split(";"):
        if chunk.strip():
            yield chunk.strip() + ";"


def _parse_db_url(url: str):
    """Parse postgresql://user:password@host:port/dbname into keyword parts.
    Tolerates passwords containing @ / $ / ! (greedy password, last '@' splits
    off the host) so we can connect via kwargs and never URL-encode."""
    m = re.match(r"^\w+://([^:]+):(.*)@([^:@/]+):(\d+)/(.+)$", url.strip())
    if not m:
        sys.exit("DB_URL inválido — esperado postgresql://user:pass@host:port/dbname")
    user, password, host, port, dbname = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    return host, port, user, password, dbname


def main():
    # Connection comes from argv (host port user password) OR, to keep the
    # password out of the command line, from the DB_URL env var (e.g.
    # `DB_URL="$(cat cred/ddl.txt)" python scripts/apply_migrations.py`).
    if len(sys.argv) >= 5:
        host, port, user, password = sys.argv[1:5]
        dbname = "postgres"
    elif os.environ.get("DB_URL"):
        host, port, user, password, dbname = _parse_db_url(os.environ["DB_URL"])
    else:
        sys.exit("Uso: apply_migrations.py <host> <port> <user> <password>  (ou env DB_URL)")
    conn = psycopg.connect(
        host=host, port=int(port), dbname=dbname,
        user=user, password=password, connect_timeout=15, autocommit=True,
    )
    cur = conn.cursor()
    for fname in ORDER:
        path = MIG_DIR / fname
        sql = path.read_text(encoding="utf-8")
        print(f"\n=== {fname} ===")
        for stmt in split_statements(sql):
            label = " ".join(stmt.split())[:70]
            try:
                cur.execute(stmt)
                print(f"  ok  {label}")
            except Exception as e:
                tolerate = fname == "008_grants_and_expose.sql" and (
                    "authenticator" in stmt or "pgrst" in stmt
                )
                if tolerate:
                    print(f"  WARN (tolerated) {label} -> {type(e).__name__}: {str(e)[:80]}")
                else:
                    print(f"  FAIL {label} -> {type(e).__name__}: {str(e)[:160]}")
                    conn.close()
                    sys.exit(1)

    print("\n=== verificacao: tabelas no schema ds ===")
    cur.execute(
        "select table_name from information_schema.tables "
        "where table_schema='ds' order by table_name"
    )
    for (t,) in cur.fetchall():
        print("  ds." + t)
    conn.close()
    print("\n[done] migracoes aplicadas")


if __name__ == "__main__":
    main()
