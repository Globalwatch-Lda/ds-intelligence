"""Dashboard KPIs — the surface a gestor sees first on opening DS Intelligence.

As of 28 May 2026 the dashboard reads from the LIVE CrediDesk mirror tables
(ds.clientes_real, ds.processos_real) for cards whose source fields exist in
the CRM list responses. Cards that still need fields we haven't captured
(apólices, leads, taxa fixa ends, exact escritura dates) report value 0 and
data_source="pending_integration" so the UI can render a clear badge.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Request

from ..config import settings
from ..core.scope import user_scope, apply_scope, scope_label
from ..db import supabase

router = APIRouter()

GANHO_STATE_NAMES = ("Ganho",)
OPEN_STATE_IDS_EXCLUDE = (12, 13)  # 12=Ganho, 13=Anulado — everything else is "open"
ESCRITURA_TOLERANCE_DAYS = 7  # widened from ±3d because updated_on is an approximation


def _today() -> date:
    return date.today()


def _add_days(n: int) -> date:
    return _today() + timedelta(days=n)


def _parse_iso_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def _select_all(sb, table: str, columns: str, page_size: int = 1000, *, scope: dict | None = None) -> list[dict]:
    """Paginate around Supabase's default 1000-row select cap. When `scope` is
    given, apply the per-profile filter (processos/leads)."""
    rows: list[dict] = []
    offset = 0
    while True:
        q = apply_scope(sb.table(table).select(columns), scope)
        chunk = q.range(offset, offset + page_size - 1).execute().data or []
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        offset += page_size
    return rows


def _upcoming_birthday(dob: str | None, today: date, until: date) -> bool:
    d = _parse_iso_date(dob)
    if not d:
        return False
    try:
        by = d.replace(year=today.year)
    except ValueError:
        return False
    if by < today:
        by = by.replace(year=today.year + 1)
    return today <= by <= until


@router.get("/kpis")
def dashboard_kpis(request: Request):
    sb = supabase()
    scope = user_scope(request)  # None for diretor_loja/admin; else this user's filter

    # clientes_real is loja-wide (not scoped); processos/leads are scoped per profile.
    clientes = _select_all(
        sb, "clientes_real", "crm_id, name, date_of_birth, telephone, email, raw"
    )
    processos = _select_all(
        sb, "processos_real",
        "crm_id, customer_crm_id, customer_name, state_id, state_name, "
        "type_name, docs_mandatory, docs_uploaded, docs_validated, "
        "updated_on_crm, created_on_crm, archived, "
        "taxa_tipo, taxa_fixa_anos_min, concluded_on_crm",
        scope=scope,
    )
    leads = _select_all(
        sb, "leads_real",
        "crm_id, name, telephone, type_name, state_name, origin_name, "
        "updated_on_crm, created_on_crm",
        scope=scope,
    )

    today = _today()
    in_7d = _add_days(7)

    # ---- aniversários próximos 7 dias (LIVE) ----
    aniversarios = [
        c for c in clientes if _upcoming_birthday(c.get("date_of_birth"), today, in_7d)
    ]

    # ---- docs em atraso (LIVE) ----
    # processo open (not Ganho/Anulado), missing docs, not touched in 7+ days
    d_minus_7 = _add_days(-7)
    docs_atraso = []
    for p in processos:
        if p.get("archived"):
            continue
        if p.get("state_id") in OPEN_STATE_IDS_EXCLUDE:
            continue
        mandatory = p.get("docs_mandatory") or 0
        uploaded = p.get("docs_uploaded") or 0
        if uploaded >= mandatory or mandatory == 0:
            continue
        upd = _parse_iso_date(p.get("updated_on_crm"))
        if upd and upd > d_minus_7:
            continue
        docs_atraso.append(p)

    # ---- escritura anniversaries via Ganho-processos updated_on proxy ----
    # join customer -> their Ganho processo, use updated_on as escritura proxy
    ganho_by_customer: dict[int, dict] = {}
    for p in processos:
        if p.get("state_name") not in GANHO_STATE_NAMES:
            continue
        cid = p.get("customer_crm_id")
        if not cid:
            continue
        # keep the most recently updated Ganho per customer
        prior = ganho_by_customer.get(cid)
        if not prior or (p.get("updated_on_crm") or "") > (prior.get("updated_on_crm") or ""):
            ganho_by_customer[cid] = p

    def _anniversary_hits(months: int) -> list[dict]:
        target_days = round(months * 30.4375)
        hits = []
        for cliente in clientes:
            cid = cliente.get("crm_id")
            ganho = ganho_by_customer.get(cid)
            if not ganho:
                continue
            esc_date = _parse_iso_date(ganho.get("updated_on_crm"))
            if not esc_date:
                continue
            anniv = esc_date + timedelta(days=target_days)
            if abs((anniv - today).days) <= ESCRITURA_TOLERANCE_DAYS:
                hits.append({"cliente": cliente, "processo": ganho})
        return hits

    escritura_3m = _anniversary_hits(3)
    escritura_6m = _anniversary_hits(6)
    escritura_12m = _anniversary_hits(12)

    # ---- taxa fixa/mista a terminar em 90 dias (LIVE, best-effort) ----
    # taxa_tipo/taxa_fixa_anos_min vêm de texto livre (ver taxa_fixa.py) — usa-se
    # o limite MENOR do intervalo de anos (ex. "2 a 5 anos" -> 2), para avisar
    # cedo em vez de tarde. concluded_on_crm é a data real de conclusão
    # (closingValues.concludedOn), não uma aproximação.
    d_plus_90 = _add_days(90)
    taxa_fixa_90d = []
    for p in processos:
        if p.get("state_name") not in GANHO_STATE_NAMES:
            continue
        anos = p.get("taxa_fixa_anos_min")
        concl = _parse_iso_date(p.get("concluded_on_crm"))
        if not anos or not concl:
            continue
        try:
            fim = concl.replace(year=concl.year + anos)
        except ValueError:
            fim = concl.replace(year=concl.year + anos, day=28)  # 29 fev em ano não bissexto
        if today <= fim <= d_plus_90:
            taxa_fixa_90d.append(p)

    # ---- leads Pendente dormentes (LIVE) ----
    # state Pendente + not updated in 30+ days = reactivation pool (per Bruno's
    # iteration 4 "Reativações" reframe)
    d_minus_30 = _add_days(-30)
    leads_dormentes = []
    for ld in leads:
        if ld.get("state_name") != "Pendente":
            continue
        upd = _parse_iso_date(ld.get("updated_on_crm"))
        if upd and upd > d_minus_30:
            continue
        leads_dormentes.append(ld)

    # ---- live totals ----
    clientes_total = len(clientes)
    processos_total = len(processos)
    processos_em_curso = sum(
        1 for p in processos
        if not p.get("archived") and p.get("state_id") not in OPEN_STATE_IDS_EXCLUDE
    )
    processos_ganhos = sum(1 for p in processos if p.get("state_name") in GANHO_STATE_NAMES)

    return {
        "loja": settings.LOJA_NAME,
        "as_of": today.isoformat(),
        "cards": [
            {
                "key": "aniversarios_7d",
                "label": "Aniversários próximos 7 dias",
                "value": len(aniversarios),
                "intent": "comemorativo",
                "data_source": "live",
            },
            {
                "key": "escritura_3m",
                "label": "Escrituras +3 meses esta semana",
                "value": len(escritura_3m),
                "intent": "acompanhamento",
                "data_source": "live_approx",
                "note": "Aproximação via último estado Ganho (data de escritura exata requer endpoint detalhe)",
            },
            {
                "key": "escritura_6m",
                "label": "Escrituras +6 meses esta semana",
                "value": len(escritura_6m),
                "intent": "acompanhamento",
                "data_source": "live_approx",
                "note": "Aproximação via último estado Ganho",
            },
            {
                "key": "escritura_12m",
                "label": "Aniversário de escritura este ano",
                "value": len(escritura_12m),
                "intent": "celebracao",
                "data_source": "live_approx",
                "note": "Aproximação via último estado Ganho",
            },
            {
                "key": "apolices_60d",
                "label": "Apólices a vencer (60 dias)",
                "value": 0,
                "intent": "comercial",
                "data_source": "pending_integration",
                "note": "Endpoint apólices ainda por capturar — secção seguros do CrediDesk",
            },
            {
                "key": "taxa_fixa_90d",
                "label": "Taxa fixa/mista a terminar (90 dias)",
                "value": len(taxa_fixa_90d),
                "intent": "comercial",
                "data_source": "live_approx",
                "note": (
                    "Extraído de texto livre do CRM (preferência do cliente, não campo "
                    "estruturado) — usa o limite menor do intervalo de anos indicado; "
                    "só conta processos onde essa preferência foi mesmo mencionada."
                ),
            },
            {
                "key": "docs_atraso",
                "label": "Processos com docs em falta há >7 dias",
                "value": len(docs_atraso),
                "intent": "alerta",
                "data_source": "live",
            },
            {
                "key": "leads_dormentes",
                "label": "Reativações (leads pendentes >30d)",
                "value": len(leads_dormentes),
                "intent": "alerta",
                "data_source": "live",
            },
        ],
        "totais": {
            "clientes_total": clientes_total,
            "processos_total": processos_total,
            "processos_em_curso": processos_em_curso,
            "processos_ganhos": processos_ganhos,
        },
        "crm_live": _crm_live_snapshot(sb, scope, scope_label(request)),
    }


def _crm_live_snapshot(sb, scope: dict | None = None, label: str = "Loja toda") -> dict:
    """Snapshot of live CRM ingest — counts + last sync timestamps. processos/leads
    counts respect the per-profile scope; clientes stays loja-wide."""
    try:
        clientes_count = sb.table("clientes_real").select("crm_id", count="exact").limit(1).execute().count or 0
        pq = apply_scope(sb.table("processos_real").select("crm_id", count="exact"), scope)
        lq = apply_scope(sb.table("leads_real").select("crm_id", count="exact"), scope)
        processos_count = pq.limit(1).execute().count or 0
        leads_count = lq.limit(1).execute().count or 0

        def _last_run(source: str) -> dict | None:
            res = (
                sb.table("crm_sync_runs")
                .select("rows_upserted, started_at, finished_at, error")
                .eq("source", source)
                .order("started_at", desc=True)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None

        last_clientes = _last_run("credidesk_customers") or {}
        last_processos = _last_run("credidesk_processos") or {}
        last_leads = _last_run("credidesk_leads") or {}

        return {
            "total_clientes": clientes_count,
            "total_processos": processos_count,
            "total_leads": leads_count,
            "last_sync_clientes_at": last_clientes.get("finished_at"),
            "last_sync_clientes_rows": last_clientes.get("rows_upserted"),
            "last_sync_processos_at": last_processos.get("finished_at"),
            "last_sync_processos_rows": last_processos.get("rows_upserted"),
            "last_sync_leads_at": last_leads.get("finished_at"),
            "last_sync_leads_rows": last_leads.get("rows_upserted"),
            "source": f"CrediDesk · {label}",
            "scope_label": label,
        }
    except Exception as e:
        return {"total_clientes": 0, "error": f"{type(e).__name__}: {e}"}


@router.get("/crm-live/sample")
def crm_live_sample(limit: int = 5):
    """Top-N mirrored CRM clients — for the dashboard preview row."""
    sb = supabase()
    res = (
        sb.table("clientes_real")
        .select("crm_id, name, email, telephone, tax_number, created_on_crm")
        .order("created_on_crm", desc=True)
        .limit(limit)
        .execute()
    )
    return {"items": res.data or []}
