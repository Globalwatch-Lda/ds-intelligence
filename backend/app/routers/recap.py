"""Weekly recap for coordenadores — Amin iteration-4 ask (22 May 2026).

Generates a pulse-style summary aimed at the loja coordinator (not individual
gestores): open processos at week-end, processos closed this week split by
Ganho / Anulado, docs ladder distribution, Reativações pool.

V1 is operator-triggered (no cron yet) and read-only — the recap renders as
HTML in the UI; the gestor copies into email or WhatsApp manually. Auto-send
deferred until DS approves the format.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Request

from ..config import settings
from ..core.scope import user_scope, apply_scope
from ..core.valores import valor_financiamento
from ..db import supabase

router = APIRouter()


GANHO_STATES = ("Ganho",)
LOST_STATES = ("Anulado", "Perdido")
OPEN_EXCLUDE_STATES = ("Ganho", "Anulado", "Perdido")


def _select_all(sb, table: str, columns: str, page_size: int = 1000, *, scope: dict | None = None) -> list[dict]:
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


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _week_window(as_of: date) -> tuple[date, date]:
    """Return (monday, friday) of the week containing as_of.
    Friday-end-of-week framing per Amin's preference."""
    monday = as_of - timedelta(days=as_of.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


@router.get("/weekly")
def weekly_recap(
    request: Request,
    week_of: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Structured recap. Defaults to the last completed calendar week. A custom
    [date_from, date_to] interval overrides the week framing (e.g. a full month)."""
    today = date.today()
    if date_from and date_to:
        monday = date.fromisoformat(date_from)
        friday = date.fromisoformat(date_to)
        if monday > friday:
            monday, friday = friday, monday
    else:
        if week_of:
            anchor = date.fromisoformat(week_of)
        else:
            # default = last completed week if today is before its own Friday
            current_friday = today - timedelta(days=today.weekday()) + timedelta(days=4)
            anchor = today - timedelta(days=7) if today <= current_friday else today
        monday, friday = _week_window(anchor)
    week_start_dt = datetime.combine(monday, datetime.min.time(), tzinfo=timezone.utc)
    week_end_dt = datetime.combine(friday + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

    sb = supabase()
    scope = user_scope(request)  # None for diretor_loja/admin (loja-wide); else this user
    processos = _select_all(
        sb, "processos_real",
        "crm_id, reference, customer_name, customer_telephone, manager_name, "
        "state_id, state_name, type_name, financing_amount, financing_amount_finished, commission_amount, "
        "docs_mandatory, docs_uploaded, docs_validated, created_on_crm, updated_on_crm, archived",
        scope=scope,
    )
    leads = _select_all(
        sb, "leads_real",
        "crm_id, name, type_full_name, state_name, origin_name, updated_on_crm",
        scope=scope,
    )

    # ----- this week's transitions -----
    closed_won = []
    closed_lost = []
    created_this_week = []
    for p in processos:
        upd = _parse_dt(p.get("updated_on_crm"))
        crt = _parse_dt(p.get("created_on_crm"))
        if crt and week_start_dt <= crt < week_end_dt:
            created_this_week.append(p)
        if not upd or not (week_start_dt <= upd < week_end_dt):
            continue
        if p.get("state_name") in GANHO_STATES:
            closed_won.append(p)
        elif p.get("state_name") in LOST_STATES:
            closed_lost.append(p)

    # ----- open processos right now -----
    open_now = [p for p in processos if p.get("state_name") not in OPEN_EXCLUDE_STATES and not p.get("archived")]
    open_by_state: dict[str, int] = {}
    open_volume_by_state: dict[str, float] = {}
    open_by_state_detail: dict[str, list] = {}
    for p in open_now:
        sn = p.get("state_name") or "—"
        open_by_state[sn] = open_by_state.get(sn, 0) + 1
        open_volume_by_state[sn] = open_volume_by_state.get(sn, 0) + valor_financiamento(p)
        open_by_state_detail.setdefault(sn, []).append({
            "reference": p.get("reference"),
            "cliente": p.get("customer_name"),
            "tipo": p.get("type_name"),
            "valor_eur": valor_financiamento(p),
            "consultor": p.get("manager_name"),
        })

    # ----- docs ladder distribution -----
    d_minus_7 = today - timedelta(days=7)
    ladder_buckets = {"nudge_7_9": 0, "second_10_14": 0, "pivot_15_19": 0, "final_20_29": 0, "standby_30plus": 0}
    ladder_rows = []
    for p in open_now:
        mandatory = p.get("docs_mandatory") or 0
        uploaded = p.get("docs_uploaded") or 0
        if mandatory == 0 or uploaded >= mandatory:
            continue
        upd = _parse_dt(p.get("updated_on_crm"))
        if not upd:
            continue
        dias = (today - upd.date()).days
        if dias < 7:
            continue
        if dias <= 9:    bucket = "nudge_7_9"
        elif dias <= 14: bucket = "second_10_14"
        elif dias <= 19: bucket = "pivot_15_19"
        elif dias <= 29: bucket = "final_20_29"
        else:            bucket = "standby_30plus"
        ladder_buckets[bucket] += 1
        ladder_rows.append({
            "reference": p.get("reference"),
            "cliente": p.get("customer_name"),
            "tipo": p.get("type_name"),
            "dias_atraso": dias,
            "bucket": bucket,
        })

    # ----- reativações count -----
    d_minus_30 = today - timedelta(days=30)
    reativacoes = sum(
        1 for ld in leads
        if ld.get("state_name") == "Pendente"
        and (_parse_dt(ld.get("updated_on_crm")) or datetime.max.replace(tzinfo=timezone.utc)).date() <= d_minus_30
    )

    # ----- totals & money flows -----
    money_won = sum(valor_financiamento(p) for p in closed_won)
    commission_won = sum(float(p.get("commission_amount") or 0) for p in closed_won)
    money_lost = sum(valor_financiamento(p) for p in closed_lost)

    return {
        "loja": settings.LOJA_NAME,
        "week_start": monday.isoformat(),
        "week_end": friday.isoformat(),
        "as_of": today.isoformat(),
        "totals": {
            "open_now": len(open_now),
            "open_volume_eur": round(sum(open_volume_by_state.values()), 2),
            "closed_won": len(closed_won),
            "closed_lost": len(closed_lost),
            "created_this_week": len(created_this_week),
            "money_won_eur": round(money_won, 2),
            "commission_won_eur": round(commission_won, 2),
            "money_lost_eur": round(money_lost, 2),
            "ladder_total_atraso": sum(ladder_buckets.values()),
            "reativacoes_pool": reativacoes,
        },
        "open_by_state": [
            {
                "state": s,
                "count": c,
                "volume_eur": round(open_volume_by_state.get(s, 0), 2),
                "processos": open_by_state_detail.get(s, []),
            }
            for s, c in sorted(open_by_state.items(), key=lambda x: -x[1])
        ],
        "closed_won_detail": [
            {
                "reference": p.get("reference"),
                "cliente": p.get("customer_name"),
                "tipo": p.get("type_name"),
                "valor_eur": valor_financiamento(p),
                "comissao_eur": p.get("commission_amount"),
                "consultor": p.get("manager_name"),
                "fechado_em": p.get("updated_on_crm"),
            }
            for p in sorted(closed_won, key=lambda x: x.get("updated_on_crm") or "", reverse=True)
        ],
        "closed_lost_detail": [
            {
                "reference": p.get("reference"),
                "cliente": p.get("customer_name"),
                "tipo": p.get("type_name"),
                "valor_eur": valor_financiamento(p),
                "consultor": p.get("manager_name"),
                "fechado_em": p.get("updated_on_crm"),
            }
            for p in sorted(closed_lost, key=lambda x: x.get("updated_on_crm") or "", reverse=True)
        ],
        "ladder": {
            "buckets": ladder_buckets,
            "rows": sorted(ladder_rows, key=lambda r: -r["dias_atraso"]),
        },
    }
