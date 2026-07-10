"""Leads — read-only view over the live CrediDesk mirror (ds.leads_real).

The page used to read ds.leads, a demo/mock table only ever populated by
seed_mock_data.py or the old "Nova lead" form — empty in production, which is
why the page showed no leads. Real leads live in ds.leads_real (ingested from
CrediDesk), so this now reads that mirror, scoped to the logged-in user's
profile like the dashboard / crm-live views.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..core.names import fix_name
from ..core.scope import apply_scope, user_scope
from ..db import supabase

router = APIRouter()

# Estados de lead fechados no CrediDesk — não são pipeline de leads:
#   Concluido = já convertida em processo (hoje é cliente, vive em Clientes-live)
#   Perdido/Anulado = morta. Só "Pendente" (em aberto) é uma lead por trabalhar.
CLOSED_STATES = {"Concluido", "Concluído", "Perdido", "Anulado"}


def _shape(r: dict) -> dict:
    """Map a leads_real row to the shape the frontend Lead table expects."""
    ultima = r.get("updated_on_crm") or r.get("created_on_crm")
    return {
        "id": str(r.get("crm_id")),
        "nome": r.get("name"),
        "telefone": r.get("telephone"),
        "email": r.get("email"),
        "nif": None,  # not mirrored on leads_real
        "produto": r.get("type_name"),
        "consultor_id": r.get("manager_name"),
        "consultor_nome": fix_name(r.get("manager_name")),
        "status": r.get("state_name"),  # Pendente / Concluido / Perdido
        "ultima_acao": ultima,
        "created_at": r.get("created_on_crm"),
    }


@router.get("/list")
def list_leads(request: Request, limit: int = 1000):
    sb = supabase()
    scope = user_scope(request)  # None = loja-wide; else this user's filter
    q = apply_scope(
        sb.table("leads_real").select(
            "crm_id, name, telephone, email, type_name, manager_name, "
            "state_name, archived, updated_on_crm, created_on_crm"
        ),
        scope,
    )
    rows = (
        q.eq("archived", False)
        .order("created_on_crm", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    # Só leads em aberto (Pendente) — as convertidas/perdidas não são pipeline.
    abertas = [r for r in rows if r.get("state_name") not in CLOSED_STATES]
    return {"leads": [_shape(r) for r in abertas]}
