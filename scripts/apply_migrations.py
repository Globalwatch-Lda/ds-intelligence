"""Aplica as migrações a UM schema — o da loja que se quiser montar.

Cada instalação DS (Ramada=`ds`, Loulé=`dsl`, as próximas=o que for) vive num
schema próprio do mesmo projeto Supabase, com exactamente as mesmas tabelas. Este
script é o que garante que "exactamente as mesmas" é verdade.

    DB_URL="$(cat cred/ddl.txt)" python scripts/apply_migrations.py --schema dsf
    DB_URL="..." python scripts/apply_migrations.py --schema dsf --dry-run

PORQUÊ FOI REESCRITO (Ago 2026): a versão anterior tinha a lista de ficheiros
escrita à mão e parada na 015 — as 18 migrações seguintes foram aplicadas à mão
no editor SQL, uma a uma, com o `search_path` editado à cabeça. Montar um schema
novo assim são 33 execuções manuais e uma migração esquecida só se descobre
quando uma página rebenta em produção. Aqui a lista é o conteúdo da pasta, por
ordem numérica, e o schema é um argumento.

COMO LIDA COM O SCHEMA: os ficheiros trazem `set search_path to ds, public;` — é
substituído pelo schema alvo antes de executar. As referências a `ds.` que restam
nos ficheiros são comentários; a excepção é a 008 (grants/PostgREST), que nomeia o
schema directamente e por isso é reescrita com o mesmo cuidado.

IDEMPOTENTE em dois níveis: cada DDL é `if not exists`, e cada ficheiro aplicado
fica registado em `<schema>.schema_migrations` — re-correr salta o que já passou,
por isso é seguro usar isto para actualizar uma loja existente com migrações novas.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import psycopg

# A consola do Windows abre em cp1252 e rebenta com acentos ou setas.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MIG_DIR = Path(__file__).resolve().parents[1] / "migrations"

# Instruções que podem falhar sem que isso comprometa o schema: dependem de papéis
# ou extensões que só existem em certos projetos Supabase.
TOLERADAS = ("authenticator", "pgrst", "notify")

# NUNCA executar automaticamente: `alter role authenticator set pgrst.db_schemas`
# SUBSTITUI a lista de schemas expostos pelo PostgREST. Correr a migração 008 num
# schema novo tirava de lá os das lojas em produção — e a API deixava de ver as
# tabelas TODAS: login a devolver 503 nas duas lojas, plataforma em baixo.
# Aconteceu a 3 Ago 2026 ao testar um schema de ensaio.
# Expor um schema novo passa a ser um passo explícito (--expor), que ACRESCENTA.
PERIGOSAS = ("pgrst.db_schemas",)


def migracoes() -> list[Path]:
    """Todos os .sql da pasta, por ordem numérica do prefixo (001, 002, …)."""
    def chave(p: Path) -> tuple[int, str]:
        m = re.match(r"(\d+)", p.name)
        return (int(m.group(1)) if m else 9999, p.name)

    return sorted(MIG_DIR.glob("*.sql"), key=chave)


def para_schema(sql: str, schema: str) -> str:
    """Reaponta o SQL de uma migração para `schema`."""
    sql = re.sub(r"set\s+search_path\s+to\s+[\w\s,]+;", f"set search_path to {schema}, public;",
                 sql, flags=re.IGNORECASE)
    # 008 nomeia o schema nas instruções (não usa search_path).
    sql = re.sub(r"\bin schema ds\b", f"in schema {schema}", sql)
    sql = re.sub(r"\bschema ds to\b", f"schema {schema} to", sql)
    sql = sql.replace("'public, graphql_public, ds'", f"'public, graphql_public, {schema}'")
    return sql


def instrucoes(sql: str):
    """Divide em instruções. Tira comentários de linha primeiro — um `--` pode
    conter ';' e partiria a instrução ao meio."""
    limpo = "\n".join(ln.split("--", 1)[0] for ln in sql.splitlines())
    for pedaco in limpo.split(";"):
        if pedaco.strip():
            yield pedaco.strip() + ";"


def main() -> None:
    ap = argparse.ArgumentParser(description="Aplica as migrações a um schema.")
    ap.add_argument("--schema", required=True, help="schema alvo (ds, dsl, dsf, …)")
    ap.add_argument("--dry-run", action="store_true", help="mostra o que faria, sem escrever")
    ap.add_argument("--expor", action="store_true",
                    help="acrescenta o schema aos expostos ao PostgREST (preserva os das outras lojas)")
    ap.add_argument("--db-url", default=os.environ.get("DB_URL"),
                    help="postgresql://user:pass@host:port/db (ou env DB_URL)")
    args = ap.parse_args()

    if not args.db_url:
        sys.exit("Falta a ligação: --db-url ou DB_URL (ver cred/ddl.txt).")
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,30}", args.schema):
        sys.exit("Nome de schema inválido — minúsculas, dígitos e '_', a começar por letra.")

    ficheiros = migracoes()
    print(f"[migrações] {len(ficheiros)} ficheiros, schema alvo: {args.schema}")
    if args.dry_run:
        for f in ficheiros:
            print(f"   - {f.name}")
        return

    m = re.match(r"^\w+://([^:]+):(.*)@([^:@/]+):(\d+)/(.+)$", args.db_url.strip())
    if not m:
        sys.exit("DB_URL inválido — esperado postgresql://user:pass@host:port/dbname")
    user, password, host, porta, dbname = m.groups()

    conn = psycopg.connect(host=host, port=int(porta), dbname=dbname, user=user,
                           password=password, connect_timeout=15, autocommit=True)
    cur = conn.cursor()
    cur.execute(f'create schema if not exists "{args.schema}";')
    cur.execute(
        f'create table if not exists "{args.schema}".schema_migrations ('
        " nome text primary key, aplicada_em timestamptz not null default now());"
    )
    cur.execute(f'select nome from "{args.schema}".schema_migrations;')
    ja = {r[0] for r in cur.fetchall()}

    aplicadas = saltadas = 0
    for f in ficheiros:
        if f.name in ja:
            saltadas += 1
            continue
        print(f"\n=== {f.name}")
        sql = para_schema(f.read_text(encoding="utf-8"), args.schema)
        for stmt in instrucoes(sql):
            etiqueta = " ".join(stmt.split())[:70]
            if any(perigo in stmt.lower() for perigo in PERIGOSAS):
                print(f"  SALTADO (destrutivo p/ as outras lojas) {etiqueta}")
                continue
            try:
                cur.execute(stmt)
                print(f"  ok   {etiqueta}")
            except Exception as e:
                if any(t in stmt.lower() for t in TOLERADAS):
                    print(f"  AVISO (tolerado) {etiqueta} -> {type(e).__name__}: {str(e)[:70]}")
                    continue
                print(f"  FALHA {etiqueta}\n        {type(e).__name__}: {str(e)[:200]}")
                conn.close()
                sys.exit(1)
        cur.execute(f'insert into "{args.schema}".schema_migrations (nome) values (%s)'
                    " on conflict do nothing;", (f.name,))
        aplicadas += 1

    if args.expor:
        # Ler a lista actual e ACRESCENTAR — nunca substituir. É a diferença entre
        # publicar uma loja nova e derrubar as que já lá estão.
        cur.execute("select setconfig from pg_db_role_setting s join pg_roles r on r.oid = s.setrole"
                    " where r.rolname = 'authenticator'")
        linha = cur.fetchone()
        atual = ""
        for item in (linha[0] if linha and linha[0] else []):
            if item.startswith("pgrst.db_schemas="):
                atual = item.split("=", 1)[1]
        schemas = [s.strip() for s in (atual or "public, graphql_public").split(",") if s.strip()]
        if args.schema not in schemas:
            schemas.append(args.schema)
        lista = ", ".join(schemas)
        cur.execute(f"alter role authenticator set pgrst.db_schemas = '{lista}'")
        cur.execute("notify pgrst, 'reload config'")
        print(f"\n[PostgREST] schemas expostos: {lista}")

    cur.execute(
        "select table_name from information_schema.tables where table_schema=%s order by table_name",
        (args.schema,),
    )
    tabelas = [t for (t,) in cur.fetchall()]
    conn.close()
    print(f"\n[feito] {aplicadas} migração(ões) aplicada(s), {saltadas} já estavam."
          f"\n[schema {args.schema}] {len(tabelas)} tabelas: {', '.join(tabelas)}")
    print("\nPasso seguinte (uma vez por projeto Supabase): juntar o schema aos "
          "'Exposed schemas' em Settings → API, senão a API não o vê.")


if __name__ == "__main__":
    main()
