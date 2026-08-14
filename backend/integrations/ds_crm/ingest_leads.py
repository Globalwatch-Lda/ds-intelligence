"""Fetch all leads from CrediDesk and upsert into ds.leads_real.

Idempotent — re-runs overwrite by crm_id. Logged in ds.crm_sync_runs.

Depois da lista, faz uma segunda passagem por lead a buscar o histórico
(/customerspotential/leads/historic/list) e guarda a ÚLTIMA acção — data, texto,
autor. A lista de leads só traz `updatedon`, que diz quando alguém mexeu mas nunca
o quê; é o histórico que responde "qual foi a última intervenção". Uma chamada por
lead (~460, 0.15s de intervalo → ~2 min), o que é aceitável num job nocturno.
Passar `--sem-historico` salta essa fase (útil se o CRM estiver lento).

Prereqs: migrações 006_leads_real.sql e 029_leads_ultima_acao.sql aplicadas.
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


def normalise(row: dict) -> dict:
    return {
        "crm_id": row["id"],
        "reference": row.get("reference"),
        "name": row.get("name"),
        "email": row.get("email"),
        "telephone": row.get("telephone"),
        "age": row.get("age"),
        "address": row.get("address"),
        "country": row.get("country"),
        "credit_type_id": row.get("creditTypeId"),
        "type_name": row.get("typeName"),
        "type_full_name": row.get("typeFullName"),
        "financing_amount": row.get("financingAmount"),
        "duration_months": row.get("durationMonths"),
        "duration_years": row.get("durationYears"),
        "manager_crm_id": row.get("managerId"),
        "manager_name": row.get("managerName"),
        "state_id": row.get("stateId"),
        "state_name": row.get("stateName"),
        "sub_state_id": row.get("subStateId"),
        "sub_state_name": row.get("subStateName"),
        "origin_id": row.get("originId"),
        "origin_name": row.get("originName"),
        "origin_desc": row.get("originDesc"),
        "proponents_number": row.get("proponentsNumber"),
        "archived": bool(row.get("archived")),
        "no_scheduled_tasks": row.get("noScheduledTasks"),
        "created_on_crm": row.get("createdon"),
        "updated_on_crm": row.get("updatedon") or row.get("updatedOn"),
        "raw": row,
    }


def resumo_ultima_acao(hist: list[dict]) -> dict:
    """Campos last_action_* a partir do histórico (já ordenado, recente primeiro).

    `interacoes_agente` conta só os registos escritos por uma pessoa (typeId 0).
    É isso que separa uma lead POR TRABALHAR de uma já contactada: "criou a lead"
    (typeId 1) e "Lead arquivada automáticamente" (-1) são do sistema e não contam.
    """
    interacoes = sum(1 for h in hist if h.get("typeId") == 0)
    if not hist:
        return {
            "last_action_at": None, "last_action_text": None, "last_action_type": None,
            "last_action_state": None, "last_action_agent": None, "last_action_count": 0,
            "interacoes_agente": 0,
        }
    h = hist[0]
    texto = (h.get("observation") or "").strip() or None
    return {
        "last_action_at": h.get("createdOn"),
        "last_action_text": texto,
        "last_action_type": h.get("typeId"),
        "last_action_state": h.get("stateName"),
        "last_action_agent": h.get("agentName"),
        "last_action_count": len(hist),
        "interacoes_agente": interacoes,
    }


def sincronizar_historico(sb, clients: dict[str, "CredidekClient"], seen_by: dict[int, set[str]],
                          nomes: dict[int, str | None], pausa: float = 0.15) -> int:
    """Uma chamada de histórico por lead, com o client de uma conta que a vê.

    Um erro numa lead não aborta a passagem — o resto das leads continua a ser
    actualizado e a lead falhada mantém a última acção anterior (ou fica a nulo,
    e o frontend cai para a data de `updated_on_crm`).
    """
    agora = datetime.now(timezone.utc).isoformat()
    ok = 0
    for i, (cid, contas) in enumerate(seen_by.items(), start=1):
        client = clients[sorted(contas)[0]]
        try:
            hist = client.get_lead_historic(cid)
        except Exception as e:
            print(f"[hist] lead {cid} ({nomes.get(cid)}): {type(e).__name__}: {str(e)[:120]}")
            continue
        patch = resumo_ultima_acao(hist)
        patch["historic_synced_at"] = agora
        sb.table("leads_real").update(patch).eq("crm_id", cid).execute()
        ok += 1
        if i % 50 == 0:
            print(f"[hist] {i}/{len(seen_by)} leads processadas")
        time.sleep(pausa)
    return ok


def main():
    com_historico = "--sem-historico" not in sys.argv
    sb = supabase()
    run = sb.table("crm_sync_runs").insert({
        "source": "credidesk_leads",
        "rows_fetched": 0,
        "rows_upserted": 0,
    }).execute()
    run_id = run.data[0]["id"]

    accounts = list_crm_accounts()
    print(f"[ingest] {len(accounts)} conta(s) CRM: {[a.username for a in accounts]}")
    total_fetched = 0
    total_upserted = 0
    BATCH_SIZE = 100

    # Two-pass merge — a lead can be visible to more than one account; collect the
    # set of accounts per crm_id, then upsert once with source_accounts = that set.
    merged: dict[int, dict] = {}
    seen_by: dict[int, set[str]] = {}
    clients: dict[str, CredidekClient] = {}

    try:
        for acct in accounts:
            print(f"[ingest] --- conta {acct.username} ({acct.crm_email}) ---")
            client = CredidekClient(email=acct.crm_email, password=acct.crm_password)
            clients[acct.username] = client
            # state_id=1 = "Pendente" — só leads por trabalhar. Concluído (2) e
            # Perdido (3) deixam de ser puxados; as que já estavam na BD desses
            # dois estados foram removidas nesta mudança (pedido do utilizador).
            for row in client.iter_leads(page_size=50, state_id=1):
                total_fetched += 1
                norm = normalise(row)
                cid = norm["crm_id"]
                merged[cid] = norm
                seen_by.setdefault(cid, set()).add(acct.username)

        batch: list[dict] = []
        for cid, norm in merged.items():
            norm["source_accounts"] = sorted(seen_by[cid])
            batch.append(norm)
            if len(batch) >= BATCH_SIZE:
                sb.table("leads_real").upsert(batch, on_conflict="crm_id").execute()
                total_upserted += len(batch)
                print(f"[ingest] upserted batch — total {total_upserted}")
                batch.clear()
        if batch:
            sb.table("leads_real").upsert(batch, on_conflict="crm_id").execute()
            total_upserted += len(batch)
            print(f"[ingest] upserted final batch — total {total_upserted}")

        hist_ok = 0
        if com_historico:
            print(f"\n[hist] última acção de {len(seen_by)} leads (histórico do CRM)...")
            nomes = {cid: (n.get("name") if isinstance(n, dict) else None) for cid, n in merged.items()}
            hist_ok = sincronizar_historico(sb, clients, seen_by, nomes)
            print(f"[hist] {hist_ok}/{len(seen_by)} leads com última acção actualizada")

        sb.table("crm_sync_runs").update({
            "rows_fetched": total_fetched,
            "rows_upserted": total_upserted,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()
        print(f"\n[done] fetched {total_fetched} leads, {len(merged)} distintos, upserted {total_upserted}"
              + (f", histórico em {hist_ok}" if com_historico else ", sem histórico"))
    except Exception as e:
        sb.table("crm_sync_runs").update({
            "rows_fetched": total_fetched,
            "rows_upserted": total_upserted,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "error": f"{type(e).__name__}: {e}"[:1000],
        }).eq("id", run_id).execute()
        raise


if __name__ == "__main__":
    main()
