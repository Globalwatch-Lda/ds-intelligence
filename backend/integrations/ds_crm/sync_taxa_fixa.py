"""Enriquece ds.processos_real com o período de taxa fixa/mista extraído do
resumo em texto livre (`contextPartners.html`) — best-effort, ver taxa_fixa.py
para o porquê de não haver campo estruturado na API do CrediDesk.

Uma chamada de detalhe por processo (mesmo padrão do histórico de leads em
ingest_leads.py). Só corre para processos NÃO arquivados — os arquivados/
anulados não interessam a este trigger comercial, e poupa chamadas.

Prereq: migração 034_taxa_fixa_extraida.sql aplicada.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.db import supabase  # noqa: E402
from integrations.ds_crm.accounts import list_crm_accounts  # noqa: E402
from integrations.ds_crm.client import CredidekClient  # noqa: E402
from integrations.ds_crm.taxa_fixa import extract_taxa_fixa  # noqa: E402


def main(pausa: float = 0.15):
    sb = supabase()
    accounts = list_crm_accounts()
    if not accounts:
        print("[taxa_fixa] sem contas CRM configuradas — nada a fazer")
        return
    clients = {
        a.username: CredidekClient(email=a.crm_email, password=a.crm_password)
        for a in accounts
    }
    default_client = next(iter(clients.values()))

    rows = (
        sb.table("processos_real")
        .select("crm_id, source_accounts")
        .eq("archived", False)
        .execute()
        .data
        or []
    )
    print(f"[taxa_fixa] {len(rows)} processos não arquivados a verificar")

    agora = datetime.now(timezone.utc).isoformat()
    ok = 0
    com_taxa = 0
    for i, row in enumerate(rows, start=1):
        pid = row["crm_id"]
        # `get_processo` só vê o que a conta autenticada alcança (mesma regra dos
        # /list) — usa uma conta que já se sabe ver este processo, gravada em
        # source_accounts pelo ingest_processos.py. Sem isso, cai na 1ª conta —
        # não pode ser sempre a mesma para todos, senão perde metade (visto ao
        # vivo: 74/272 do Ramada só visíveis à conta "bs", não "jg").
        src = row.get("source_accounts") or []
        client = clients.get(src[0]) if src else None
        client = client or default_client
        try:
            detail = client.get_processo(pid)
        except Exception as e:
            print(f"[taxa_fixa] processo {pid}: {type(e).__name__}: {str(e)[:120]}")
            continue
        cp = detail.get("creditprocess")
        cp = cp[0] if isinstance(cp, list) and cp else None
        if not cp:
            print(f"[taxa_fixa] processo {pid}: sem creditprocess na resposta (conta {src})")
            continue

        parsed = extract_taxa_fixa(
            (cp.get("contextPartners") or {}).get("html")
            if isinstance(cp.get("contextPartners"), dict)
            else None
        )
        closing = cp.get("closingValues") or {}

        patch = {
            "taxa_tipo": parsed["tipo"] if parsed else None,
            "taxa_fixa_anos_min": parsed["anos_min"] if parsed else None,
            "taxa_fixa_anos_max": parsed["anos_max"] if parsed else None,
            "concluded_on_crm": closing.get("concludedOn"),
            "taxa_fixa_synced_at": agora,
        }
        sb.table("processos_real").update(patch).eq("crm_id", pid).execute()
        ok += 1
        if parsed:
            com_taxa += 1
        if i % 100 == 0:
            print(f"[taxa_fixa] {i}/{len(rows)} processados")
        time.sleep(pausa)

    print(f"[taxa_fixa] concluído: {ok}/{len(rows)} atualizados, {com_taxa} com preferência de taxa fixa/mista extraída")


if __name__ == "__main__":
    main()
