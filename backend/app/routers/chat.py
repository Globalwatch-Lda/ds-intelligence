"""Chat assistente — Sonnet 4.6 over a compact CRM snapshot.

This is the text-only Phase-1 replacement for the "Bruna" voice assistant
that Sílvia parked. Operator asks questions in natural Portuguese and the
model answers with concrete rows from the CRM.

As of 28 May 2026 the snapshot mixes:
  LIVE data (CrediDesk mirror): processos_real (all 187), clientes_real (top
    300 by recency + any open-process owners + any 7-day birthday), leads_real
    (all 438).
  DEMO data: apolices (endpoint not in CrediDesk — DS Seguros uses a separate
    system).
"""
from __future__ import annotations
import json
from datetime import date, datetime, timedelta

import anthropic
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..config import settings
from ..core.scope import user_scope, apply_scope
from ..db import supabase

router = APIRouter()


SYSTEM_PROMPT = """You are Ana, the operational assistant inside DS Matrix at the
__LOJA__ loja. The loja team asks you
natural-language questions about their clients, processes, and policies. You answer
from the JSON snapshot of the CRM provided in the user message.

LANGUAGE: Portuguese (Portugal). Never Brazilian. Direct, professional, no fluff.

DATA SOURCES INSIDE THE SNAPSHOT:
- `agregados` are AUTHORITATIVE totals computed over the FULL mirrored dataset (NOT
  a sample). Use them for ANY counting / total / volume question — e.g.
  `total_clientes_loja`, `total_processos_gestor`, `total_leads_gestor`,
  `processos_por_estado`, `ganhos_<ano>`, `anulados_perdidos_<ano>`,
  `leads_por_estado`. When you quote one of these, state it as the definitive number.
- `processos` and `leads` are the COMPLETE live rows from the CrediDesk CRM for this
  gestor's account. `clientes` is a live detail list of up to 300 client rows (the
  most relevant ones) — for looking up individuals, NOT for counting the client base.
- `apolices` is DEMO data — DS Seguros uses a separate system (not CrediDesk).
  If a question targets apólices, answer from the demo data BUT add a single
  sentence at the end: "(Dados de apólices ainda em modo demo — integração com a CRM de seguros DS pendente.)"

SCOPE: clientes are loja-wide; processos and leads mirror the LOGGED-IN gestor's
own CrediDesk account. If asked for loja-wide processo/lead figures across every
gestor, answer with this gestor's numbers and note they reflect their own pipeline
(a loja-coordinator view is not yet available). Never invent figures for other
gestores.

RULES:
- For counting / "quantos" / total / volume questions, use `agregados` and give the
  number directly. NEVER add caveats about sample size, "apenas 300 carregados",
  "o snapshot inclui apenas N", or similar — the agregados cover the full data, so
  such caveats are wrong and confusing. The only legitimate caveat is the SCOPE one
  above (gestor vs loja), and only when actually relevant.
- When asked about a SPECIFIC client who is not in the `clientes` detail list, say you
  can give the overall total but would need to look that person up specifically — do
  NOT imply the totals are uncertain.
- Answer from the data; never invent names, phone numbers, NIFs, or values.
- Commit to a single, clean final answer. Do NOT narrate your reasoning ("Aguarda…",
  "Na verdade…", "Espera, deixa-me ver outra vez", "Peço desculpa — são afinal…",
  "Corrijo: são…").
- COUNTING DISCIPLINE when you enumerate rows: never put the count at the START. List
  the matching rows first, then the total at the end, and make the total equal the
  number of rows listed. For pure aggregate questions, just quote `agregados`.
- Date semantics (compute against `as_of` in the snapshot, always Lisbon time):
    • "hoje" = the as_of date
    • "amanhã" = as_of + 1 day
    • "esta semana" = from as_of through the upcoming Sunday (inclusive)
    • "próximos N dias" = as_of through as_of + N days (inclusive)
    • "este mês" = first to last day of the as_of month
  Do NOT include dates that have already passed unless the user explicitly asks about
  "vencidas" or "atrasadas".
- For policy renewals, do NOT include `pendente_renovacao` (already-expired) apólices
  when answering future-looking questions ("a vencer", "próximos N dias").
- Use short markdown lists or tables. Include the most relevant fields (nome, data,
  valor, telefone). Never fabricate phone numbers, NIFs, or values.
- For processos, state names map: Qualificação, Enviado a Bancos, Decisão Cliente,
  Avaliação, Aprovação, Ganho (loan closed), Anulado (cancelled).
- For leads, state names map: Pendente (em aberto), Concluido (já convertido em
  processo), Perdido. The `origin_name` field tells you HOW the lead arrived
  (Círculo de influências, Directo/Loja, Evento, etc.) — useful when answering
  "de onde vêm os leads?".
- If a question can be answered with the LIVE data alone (processos/clientes), prefer
  that over reaching into the demo apolices/leads.
- When the operator asks "envia uma mensagem", DO NOT pretend to send. Tell them to
  use the Gatilhos panel.
- Keep replies under 200 words unless explicitly asked for more detail.""".replace("__LOJA__", settings.LOJA_NAME)


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


def _trim_processo(p: dict) -> dict:
    return {
        "id": p["crm_id"],
        "ref": p.get("reference"),
        "cliente_id": p.get("customer_crm_id"),
        "cliente_nome": p.get("customer_name"),
        "cliente_nif": p.get("customer_tax_number"),
        "cliente_tel": p.get("customer_telephone"),
        "consultor": p.get("manager_name"),
        "estado": p.get("state_name"),
        "tipo": p.get("type_name"),
        "valor": p.get("financing_amount"),
        "docs_obrigatorios": p.get("docs_mandatory"),
        "docs_carregados": p.get("docs_uploaded"),
        "docs_validados": p.get("docs_validated"),
        "criado_em": p.get("created_on_crm"),
        "atualizado_em": p.get("updated_on_crm"),
    }


def _trim_cliente(c: dict) -> dict:
    return {
        "id": c["crm_id"],
        "nome": c.get("name"),
        "nif": c.get("tax_number"),
        "telefone": c.get("telephone"),
        "email": c.get("email"),
        "data_nascimento": c.get("date_of_birth"),
        "criado_em": c.get("created_on_crm"),
    }


def _upcoming_birthday(dob: str | None, today: date, until: date) -> bool:
    if not dob:
        return False
    try:
        d = date.fromisoformat(dob)
    except ValueError:
        return False
    try:
        by = d.replace(year=today.year)
    except ValueError:
        return False
    if by < today:
        by = by.replace(year=today.year + 1)
    return today <= by <= until


def _crm_snapshot(scope: dict | None = None) -> dict:
    sb = supabase()
    today = date.today()
    in_7d = today + timedelta(days=7)

    # LIVE — processos for the logged-in user's profile (loja-wide for diretor_loja)
    processos = _select_all(
        sb, "processos_real",
        "crm_id, reference, customer_crm_id, customer_name, customer_tax_number, "
        "customer_telephone, manager_name, state_name, type_name, financing_amount, "
        "commission_amount, docs_mandatory, docs_uploaded, docs_validated, "
        "created_on_crm, updated_on_crm",
        scope=scope,
    )
    processos_trim = [_trim_processo(p) for p in processos]

    # LIVE — clientes with priority: any with an open processo, plus birthday-in-7d,
    # then fill with most-recent up to 300 total. Keeps token cost predictable.
    clientes_all = _select_all(
        sb, "clientes_real",
        "crm_id, name, tax_number, telephone, email, date_of_birth, created_on_crm"
    )
    open_customer_ids = {p["customer_crm_id"] for p in processos if p.get("customer_crm_id") and p.get("state_name") not in ("Ganho", "Anulado")}
    must_include = set(open_customer_ids)
    must_include.update(
        c["crm_id"] for c in clientes_all if _upcoming_birthday(c.get("date_of_birth"), today, in_7d)
    )
    priority = [c for c in clientes_all if c["crm_id"] in must_include]
    leftover = [c for c in clientes_all if c["crm_id"] not in must_include]
    leftover.sort(key=lambda c: c.get("created_on_crm") or "", reverse=True)
    snapshot_clientes = priority + leftover[: max(0, 300 - len(priority))]
    clientes_trim = [_trim_cliente(c) for c in snapshot_clientes]

    # LIVE — consultores from the processos manager_name distinct
    consultores = sorted({p.get("manager_name") for p in processos if p.get("manager_name")})

    # LIVE — leads for the logged-in user's profile (loja-wide for diretor_loja)
    leads_all = _select_all(
        sb, "leads_real",
        "crm_id, name, telephone, type_full_name, state_name, origin_name, "
        "financing_amount, manager_name, created_on_crm, updated_on_crm",
        scope=scope,
    )
    leads_trim = [
        {
            "id": l["crm_id"],
            "nome": l.get("name"),
            "telefone": l.get("telephone"),
            "produto": l.get("type_full_name"),
            "estado": l.get("state_name"),
            "origem": l.get("origin_name"),
            "valor": l.get("financing_amount"),
            "consultor": l.get("manager_name"),
            "criado_em": l.get("created_on_crm"),
            "atualizado_em": l.get("updated_on_crm"),
        }
        for l in leads_all
    ]

    # DEMO — apolices from mock seed (DS Seguros uses a separate CRM)
    apolices = sb.table("apolices").select(
        "id, cliente_id, ramo, seguradora, premio_anual, data_vencimento, status"
    ).execute().data

    # ---- authoritative aggregates, computed over the FULL mirrored data so the
    # assistant answers counting/volume questions exactly, with no sample caveats ----
    def _num(x) -> float:
        try:
            return float(x or 0)
        except (TypeError, ValueError):
            return 0.0

    proc_por_estado: dict[str, dict] = {}
    for p in processos:
        sn = p.get("state_name") or "—"
        b = proc_por_estado.setdefault(sn, {"count": 0, "volume_eur": 0.0})
        b["count"] += 1
        b["volume_eur"] = round(b["volume_eur"] + _num(p.get("financing_amount")), 2)

    ano = today.year
    ganhos_ano = {"count": 0, "volume_eur": 0.0, "comissao_eur": 0.0}
    anulados_ano = {"count": 0, "volume_eur": 0.0}
    for p in processos:
        if (p.get("updated_on_crm") or "")[:4] != str(ano):
            continue
        if p.get("state_name") == "Ganho":
            ganhos_ano["count"] += 1
            ganhos_ano["volume_eur"] = round(ganhos_ano["volume_eur"] + _num(p.get("financing_amount")), 2)
            ganhos_ano["comissao_eur"] = round(ganhos_ano["comissao_eur"] + _num(p.get("commission_amount")), 2)
        elif p.get("state_name") in ("Anulado", "Perdido"):
            anulados_ano["count"] += 1
            anulados_ano["volume_eur"] = round(anulados_ano["volume_eur"] + _num(p.get("financing_amount")), 2)

    leads_por_estado: dict[str, int] = {}
    for ld in leads_all:
        sn = ld.get("state_name") or "—"
        leads_por_estado[sn] = leads_por_estado.get(sn, 0) + 1

    agregados = {
        "ambito": "clientes = loja inteira; processos e leads = conta do gestor autenticado",
        "total_clientes_loja": len(clientes_all),
        "total_processos_gestor": len(processos),
        "total_leads_gestor": len(leads_all),
        "processos_por_estado": proc_por_estado,
        f"ganhos_{ano}": ganhos_ano,
        f"anulados_perdidos_{ano}": anulados_ano,
        "leads_por_estado": leads_por_estado,
    }

    return {
        "as_of": today.isoformat(),
        "loja": settings.LOJA_NAME,
        "agregados": agregados,
        "consultores": consultores,
        "clientes": clientes_trim,
        "clientes_total_no_crm": len(clientes_all),
        "clientes_no_snapshot": len(clientes_trim),
        "processos": processos_trim,
        "processos_total": len(processos_trim),
        "leads": leads_trim,
        "leads_total": len(leads_trim),
        "apolices": apolices,
        "apolices_demo": True,
    }


class ChatBody(BaseModel):
    message: str
    history: list[dict] = []   # [{role: "user"|"assistant", content: str}, ...]


@router.post("/ask")
def ask(body: ChatBody, request: Request):
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured")

    snapshot = _crm_snapshot(user_scope(request))
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, default=str)

    messages = []
    for h in body.history[-10:-1]:
        if h.get("role") in ("user", "assistant"):
            messages.append({"role": h["role"], "content": h["content"]})

    user_content = (
        f"<crm_snapshot>\n{snapshot_json}\n</crm_snapshot>\n\n"
        f"Pergunta: {body.message}"
    )
    messages.append({"role": "user", "content": user_content})

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=settings.CHAT_MODEL,
        max_tokens=1200,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    return {"reply": text, "as_of": snapshot["as_of"]}
