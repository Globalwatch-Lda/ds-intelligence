"""Lifecycle triggers — surfaces the actionable lists behind each dashboard card,
plus a `fire` endpoint that composes and sends the WhatsApp message.

Templates live here (PT-PT, short, brand-consistent). The gestor sees the
preview in the UI and can either Send or Skip per row.

Data sources (28 May 2026):
  aniversario, escritura_3m/6m/12m, doc_atraso → LIVE (clientes_real, processos_real)
  apolice_60d, taxa_fixa_90d, lead_dormente   → MOCK (endpoints not yet captured)
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ..config import settings
from ..core.scope import user_scope, apply_scope
from ..core.wa_client import send_text, is_demo_recipient
from ..core.valores import valor_financiamento
from ..db import supabase

router = APIRouter()


TriggerType = Literal[
    "aniversario", "escritura_3m", "escritura_6m", "escritura_12m",
    "apolice_60d", "taxa_fixa_90d", "doc_atraso", "lead_dormente",
]

LIVE_TRIGGERS = {"aniversario", "escritura_3m", "escritura_6m", "escritura_12m", "doc_atraso", "lead_dormente"}
GANHO_STATE_NAMES = ("Ganho",)
OPEN_STATE_IDS_EXCLUDE = (12, 13)  # 12=Ganho, 13=Anulado
ESCRITURA_TOLERANCE_DAYS = 7

# ---------------------------------------------------------------
# Documentação staged escalation ladder (Amin's iteration-4 ask, 22 May 2026).
# v1 intervals — to refine with DS once we see real-world response rates.
# Each tuple is (min_days_inclusive, max_days_inclusive, stage_key, stage_label).
DOC_LADDER_STAGES: list[tuple[int, int, str, str]] = [
    (7,  9,  "nudge",     "Lembrete"),
    (10, 14, "second",    "Segundo lembrete"),
    (15, 19, "pivot",     "Pergunta de continuidade"),
    (20, 29, "final",     "Última tentativa"),
    (30, 9999, "standby", "Stand-by sugerido"),
]


def _doc_atraso_stage(dias_atraso: int | None) -> dict:
    """Compute which ladder stage a doc-atraso processo is in.

    Below 7 days = not yet on the ladder. The dashboard card already filters
    for >7 days so this should always hit one of the stages, but we defensive-
    default to nudge if anything unusual lands here.
    """
    d = dias_atraso if dias_atraso is not None else 0
    for lo, hi, key, label in DOC_LADDER_STAGES:
        if lo <= d <= hi:
            return {"key": key, "label": label, "days_low": lo, "days_high": hi}
    return {"key": "nudge", "label": "Lembrete", "days_low": 7, "days_high": 9}


def _doc_atraso_template(stage: str, nome: str, docs_str: str, loja: str) -> str:
    """Per-stage WhatsApp body. Day intervals reference Amin's 22 May spec."""
    if stage == "nudge":
        return (
            f"Olá {nome}, tudo bem?\n\n"
            f"Para avançarmos com o seu processo de crédito, ainda precisamos da seguinte documentação:\n\n"
            f"• {docs_str}\n\n"
            f"Pode enviar-nos por WhatsApp ou trazer à loja. Qualquer dúvida, conte connosco.\n\n"
            f"Equipa {loja}."
        )
    if stage == "second":
        return (
            f"Olá {nome}, fazemos seguimento do nosso último contacto.\n\n"
            f"Continuamos a aguardar a documentação para podermos submeter o seu processo:\n\n"
            f"• {docs_str}\n\n"
            f"Quanto mais cedo recebermos, mais rápido conseguimos avançar. Pode responder aqui ou ligar-nos.\n\n"
            f"Equipa {loja}."
        )
    if stage == "pivot":
        # day 10 pivot — Amin's verbatim: "does it still make sense?"
        return (
            f"Olá {nome}, queremos perceber consigo o ponto de situação.\n\n"
            f"O seu processo continua em aberto mas ainda nos faltam alguns documentos para avançar:\n\n"
            f"• {docs_str}\n\n"
            f"Ainda faz sentido continuarmos agora, ou prefere que o coloquemos em *stand-by* até estar pronto? "
            f"Qualquer das opções é fácil para nós — só precisamos de saber.\n\n"
            f"Equipa {loja}."
        )
    if stage == "final":
        return (
            f"Olá {nome}, fazemos uma última tentativa de contacto sobre o seu processo de crédito.\n\n"
            f"Continuamos sem receber:\n\n"
            f"• {docs_str}\n\n"
            f"Se ainda quiser avançar, basta responder a esta mensagem. Caso contrário, colocaremos o processo "
            f"em *stand-by* nos próximos dias — pode ser retomado a qualquer momento sem perder o histórico.\n\n"
            f"Equipa {loja}."
        )
    if stage == "standby":
        # 30d+: surfacing to gestor for manual review — message rendered for reference only
        return (
            f"⚠️ Sugestão para o gestor: processo de {nome} está há mais de 30 dias sem actividade. "
            f"Recomendamos colocar em stand-by no CRM e contactar o cliente para fechar o ciclo. "
            f"(Mensagem reservada — não dispara automaticamente.)"
        )
    return (
        f"Olá {nome}, ainda precisamos de:\n\n• {docs_str}\n\nEquipa {loja}."
    )
# ---------------------------------------------------------------


def _today() -> date:
    return date.today()


def _parse(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        except (ValueError, TypeError):
            return None


def _birthday_in_range(dob: date | None, lo: date, hi: date) -> date | None:
    """First yearly occurrence of dob's month/day within [lo, hi], or None."""
    if not dob:
        return None
    for yr in range(lo.year, hi.year + 1):
        try:
            occ = dob.replace(year=yr)
        except ValueError:  # 29 Feb on a non-leap year
            continue
        if lo <= occ <= hi:
            return occ
    return None


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


def _manager_by_customer(sb) -> dict[int, str]:
    """Map each customer_crm_id → the manager (consultor) of their most recent
    processo. Used to surface the responsible consultant on triggers whose base
    table (clientes_real) carries no manager column (aniversário, escrituras)."""
    procs = _select_all(sb, "processos_real", "customer_crm_id, manager_name, updated_on_crm")
    latest: dict[int, dict] = {}
    for p in procs:
        cid = p.get("customer_crm_id")
        if not cid or not p.get("manager_name"):
            continue
        prior = latest.get(cid)
        if not prior or (p.get("updated_on_crm") or "") > (prior.get("updated_on_crm") or ""):
            latest[cid] = p
    return {cid: p["manager_name"] for cid, p in latest.items()}


# ----------------------------------------------------------------- templates
def _template(trigger: TriggerType, ctx: dict) -> str:
    nome = (ctx.get("nome") or "").split(" ")[0] or "amigo(a)"
    loja = settings.LOJA_NAME

    if trigger == "aniversario":
        return (
            f"Olá {nome}, parabéns! 🎉\n\n"
            f"A equipa da {loja} deseja-lhe um feliz aniversário e um ano cheio de boas notícias.\n\n"
            f"Estamos cá para o que precisar."
        )

    if trigger == "escritura_3m":
        return (
            f"Olá {nome}, esperamos que esteja tudo bem consigo.\n\n"
            f"Passaram já 3 meses desde a sua escritura. Está tudo a correr conforme esperado "
            f"com a sua prestação e a relação com o banco?\n\n"
            f"Qualquer dúvida ou ajuste que faça sentido, conte connosco. Equipa {loja}."
        )

    if trigger == "escritura_6m":
        return (
            f"Olá {nome}, faz hoje 6 meses desde a sua escritura. 🎊\n\n"
            f"Aproveitamos para perguntar se está tudo bem com o seu crédito e se há algo "
            f"que possamos rever consigo (taxa, seguros associados, condições).\n\n"
            f"Estamos sempre disponíveis. Equipa {loja}."
        )

    if trigger == "escritura_12m":
        return (
            f"{nome}, faz hoje 1 ano que comprou a sua casa! 🏡✨\n\n"
            f"Parabéns por mais este passo. Se quiser que revejamos as condições do seu "
            f"crédito ou seguros, é o momento ideal — o mercado mudou.\n\n"
            f"Equipa {loja}."
        )

    if trigger == "apolice_60d":
        ramo = ctx.get("ramo", "seguro")
        return (
            f"Olá {nome}, o seu {ramo} aproxima-se da renovação (próximos 60 dias).\n\n"
            f"Antes de renovar automaticamente, podemos comparar com outras seguradoras "
            f"e garantir que continua a ter as melhores condições?\n\n"
            f"Equipa {loja}."
        )

    if trigger == "taxa_fixa_90d":
        return (
            f"Olá {nome}, o período de taxa fixa do seu crédito termina nos próximos 90 dias.\n\n"
            f"Este é o momento certo para revermos as condições — taxa fixa, variável, mista — "
            f"e ver o que faz mais sentido para si com o mercado actual.\n\n"
            f"Quando lhe der jeito, marcamos uma conversa. Equipa {loja}."
        )

    if trigger == "doc_atraso":
        docs = ctx.get("docs_em_falta", [])
        docs_str = ", ".join(d.replace("_", " ") for d in docs) if docs else "documentação pendente"
        stage = ctx.get("stage") or "nudge"
        return _doc_atraso_template(stage, nome, docs_str, loja)

    if trigger == "lead_dormente":
        return (
            f"Olá {nome}, há algum tempo falámos sobre uma possível solução de crédito/seguro.\n\n"
            f"O mercado mudou nas últimas semanas — taxas, condições, ofertas — e talvez faça "
            f"sentido revermos a sua situação consigo.\n\n"
            f"Quando lhe der jeito, retomamos a conversa. Equipa {loja}."
        )

    raise HTTPException(400, f"Unknown trigger: {trigger}")


# --------------------------------------------------------------- list rows
@router.get("/list")
def list_trigger_rows(
    request: Request,
    trigger: TriggerType,
    date_from: str | None = Query(None, description="ISO date — start of a custom range"),
    date_to: str | None = Query(None, description="ISO date — end of a custom range"),
):
    sb = supabase()
    today = _today()
    scope = user_scope(request)  # scope processos/leads to the logged-in user's profile
    rng_lo = _parse(date_from)
    rng_hi = _parse(date_to)
    has_range = rng_lo is not None and rng_hi is not None
    if has_range and rng_lo > rng_hi:
        rng_lo, rng_hi = rng_hi, rng_lo

    if trigger == "aniversario":
        clientes = _select_all(sb, "clientes_real", "crm_id, name, telephone, date_of_birth, manager_name")
        # Primary source is the customer's own manager (100% populated in the CRM);
        # the process-based lookup stays only as a fallback for the rare null.
        mgr_by_customer = _manager_by_customer(sb)
        out = []
        for c in clientes:
            dn = _parse(c.get("date_of_birth"))
            if not dn:
                continue
            if has_range:
                by = _birthday_in_range(dn, rng_lo, rng_hi)
                if by is None:
                    continue
            else:
                try:
                    by = dn.replace(year=today.year)
                except ValueError:
                    continue
                if by < today:
                    by = by.replace(year=today.year + 1)
                if (by - today).days > 7:
                    continue
            days_until = (by - today).days
            out.append({
                "cliente_id": str(c["crm_id"]),
                "cliente_crm_id": c["crm_id"],
                "nome": c["name"],
                "telefone": c.get("telephone"),
                "gestor": c.get("manager_name") or mgr_by_customer.get(c["crm_id"]),
                "data": by.isoformat(),
                "dias_ate": days_until,
                "data_source": "live",
            })
        return {"trigger": trigger, "rows": sorted(out, key=lambda r: r["dias_ate"])}

    if trigger in ("escritura_3m", "escritura_6m", "escritura_12m"):
        months = {"escritura_3m": 3, "escritura_6m": 6, "escritura_12m": 12}[trigger]
        delta_days = round(months * 30.4375)
        clientes = _select_all(sb, "clientes_real", "crm_id, name, telephone")
        cli_by_id = {c["crm_id"]: c for c in clientes}
        processos = _select_all(
            sb, "processos_real",
            "crm_id, customer_crm_id, state_name, updated_on_crm, financing_amount, financing_amount_finished, manager_name"
        )
        ganho_by_customer: dict[int, dict] = {}
        for p in processos:
            if p.get("state_name") not in GANHO_STATE_NAMES:
                continue
            cid = p.get("customer_crm_id")
            if not cid:
                continue
            prior = ganho_by_customer.get(cid)
            if not prior or (p.get("updated_on_crm") or "") > (prior.get("updated_on_crm") or ""):
                ganho_by_customer[cid] = p
        out = []
        for cid, p in ganho_by_customer.items():
            esc = _parse(p.get("updated_on_crm"))
            if not esc:
                continue
            anniv = esc + timedelta(days=delta_days)
            if has_range:
                if not (rng_lo <= anniv <= rng_hi):
                    continue
            elif abs((anniv - today).days) > ESCRITURA_TOLERANCE_DAYS:
                continue
            c = cli_by_id.get(cid) or {}
            out.append({
                "cliente_id": str(cid),
                "cliente_crm_id": cid,
                "processo_crm_id": p["crm_id"],
                "nome": c.get("name"),
                "telefone": c.get("telephone"),
                "gestor": p.get("manager_name"),
                "data_escritura": esc.isoformat(),
                "aniversario": anniv.isoformat(),
                "valor_credito": valor_financiamento(p),
                "data_source": "live_approx",
            })
        return {"trigger": trigger, "rows": sorted(out, key=lambda r: r["aniversario"])}

    if trigger == "apolice_60d":
        lo = rng_lo if has_range else today
        hi = rng_hi if has_range else today + timedelta(days=60)
        apols = sb.table("apolices").select(
            "id, cliente_id, ramo, seguradora, data_vencimento, premio_anual, consultor_id"
        ).gte("data_vencimento", lo.isoformat()).lte("data_vencimento", hi.isoformat()).execute().data
        cli = {c["id"]: c for c in sb.table("clientes").select("id, nome, telefone").execute().data}
        ges = {g["id"]: g["nome"] for g in sb.table("gestores").select("id, nome").execute().data}
        out = []
        for a in apols:
            c = cli.get(a["cliente_id"]) or {}
            out.append({
                "apolice_id": a["id"],
                "cliente_id": a["cliente_id"],
                "nome": c.get("nome"),
                "telefone": c.get("telefone"),
                "gestor": ges.get(a.get("consultor_id")),
                "ramo": a.get("ramo"),
                "seguradora": a.get("seguradora"),
                "data_vencimento": a.get("data_vencimento"),
                "premio_anual": a.get("premio_anual"),
                "data_source": "mock",
            })
        return {"trigger": trigger, "rows": sorted(out, key=lambda r: r["data_vencimento"])}

    if trigger == "taxa_fixa_90d":
        lo = rng_lo if has_range else today
        hi = rng_hi if has_range else today + timedelta(days=90)
        procs = sb.table("processos").select(
            "id, cliente_id, taxa_fixa_ate, taxa_tipo, valor_credito, consultor_id"
        ).gte("taxa_fixa_ate", lo.isoformat()).lte("taxa_fixa_ate", hi.isoformat()).execute().data
        cli = {c["id"]: c for c in sb.table("clientes").select("id, nome, telefone").execute().data}
        ges = {g["id"]: g["nome"] for g in sb.table("gestores").select("id, nome").execute().data}
        out = []
        for p in procs:
            c = cli.get(p["cliente_id"]) or {}
            out.append({
                "processo_id": p["id"],
                "cliente_id": p["cliente_id"],
                "nome": c.get("nome"),
                "telefone": c.get("telefone"),
                "gestor": ges.get(p.get("consultor_id")),
                "taxa_fixa_ate": p.get("taxa_fixa_ate"),
                "taxa_tipo": p.get("taxa_tipo"),
                "valor_credito": p.get("valor_credito"),
                "data_source": "mock",
            })
        return {"trigger": trigger, "rows": sorted(out, key=lambda r: r["taxa_fixa_ate"])}

    if trigger == "doc_atraso":
        processos = _select_all(
            sb, "processos_real",
            "crm_id, customer_crm_id, customer_name, customer_telephone, "
            "state_id, state_name, docs_mandatory, docs_uploaded, docs_validated, "
            "updated_on_crm, type_name, manager_name",
            scope=scope,
        )
        d_minus_7 = today - timedelta(days=7)

        # Pull all previous doc_atraso sends for these processos so we can show
        # ladder history per row (and so the gestor knows what stage was last fired)
        history_rows = (
            sb.table("triggers_fired")
            .select("processo_crm_id, fired_at, mensagem, status")
            .eq("trigger_type", "doc_atraso")
            .not_.is_("processo_crm_id", "null")
            .order("fired_at", desc=True)
            .execute()
            .data or []
        )
        history_by_processo: dict[int, list[dict]] = {}
        for h in history_rows:
            pid = h.get("processo_crm_id")
            if pid is None:
                continue
            history_by_processo.setdefault(pid, []).append({
                "fired_at": h.get("fired_at"),
                "status": h.get("status"),
                "preview": (h.get("mensagem") or "")[:120],
            })

        out = []
        for p in processos:
            if p.get("state_id") in OPEN_STATE_IDS_EXCLUDE:
                continue
            mandatory = p.get("docs_mandatory") or 0
            uploaded = p.get("docs_uploaded") or 0
            if mandatory == 0 or uploaded >= mandatory:
                continue
            upd = _parse(p.get("updated_on_crm"))
            if upd and upd > d_minus_7:
                continue
            falta = mandatory - uploaded
            dias_atraso = (today - upd).days if upd else None
            stage_info = _doc_atraso_stage(dias_atraso)
            hist = history_by_processo.get(p["crm_id"], [])
            out.append({
                "cliente_id": str(p["customer_crm_id"]),
                "cliente_crm_id": p["customer_crm_id"],
                "processo_id": str(p["crm_id"]),
                "processo_crm_id": p["crm_id"],
                "nome": p.get("customer_name"),
                "telefone": p.get("customer_telephone"),
                "gestor": p.get("manager_name"),
                "documentos_em_falta": [],
                "documentos_em_falta_count": falta,
                "docs_mandatory": mandatory,
                "docs_uploaded": uploaded,
                "ultima_atividade": p.get("updated_on_crm"),
                "dias_atraso": dias_atraso,
                "tipo": p.get("type_name"),
                "estado": p.get("state_name"),
                "stage_key": stage_info["key"],
                "stage_label": stage_info["label"],
                "previous_sends": hist,
                "data_source": "live",
            })
        return {"trigger": trigger, "rows": sorted(out, key=lambda r: (r["dias_atraso"] or 0), reverse=True)}

    if trigger == "lead_dormente":
        leads = _select_all(
            sb, "leads_real",
            "crm_id, name, telephone, type_full_name, state_name, origin_name, "
            "manager_name, updated_on_crm, created_on_crm",
            scope=scope,
        )
        out = []
        thirty_days_ago = today - timedelta(days=30)
        for ld in leads:
            if ld.get("state_name") != "Pendente":
                continue
            ult = _parse(ld.get("updated_on_crm"))
            if ult and ult > thirty_days_ago:
                continue
            out.append({
                "cliente_id": str(ld["crm_id"]),
                "cliente_crm_id": ld["crm_id"],
                "lead_id": str(ld["crm_id"]),
                "nome": ld.get("name"),
                "telefone": ld.get("telephone"),
                "produto": ld.get("type_full_name"),
                "origem": ld.get("origin_name"),
                "gestor": ld.get("manager_name"),
                "estado": ld.get("state_name"),
                "ultima_acao": ld.get("updated_on_crm"),
                "dias_dormente": (today - ult).days if ult else None,
                "data_source": "live",
            })
        return {"trigger": trigger, "rows": sorted(out, key=lambda r: (r["dias_dormente"] or 0), reverse=True)}

    raise HTTPException(400, f"Unknown trigger: {trigger}")


# ------------------------------------------------------------- preview send
class FireBody(BaseModel):
    trigger: TriggerType
    cliente_id: str
    processo_id: str | None = None
    apolice_id: str | None = None
    telefone_override: str | None = None  # demo: redirect to a verified recipient
    mensagem_override: str | None = None  # operator-edited preview text


def _load_recipient(sb, body: FireBody) -> dict:
    """Resolve the recipient row from the right table for the trigger type.

    Returns dict with: nome, telefone, is_lead, source ("live" or "mock"),
    and either cliente_uuid (mock path) or cliente_crm_id (live path).
    """
    if body.trigger == "lead_dormente":
        try:
            crm_id = int(body.cliente_id)
        except (TypeError, ValueError):
            raise HTTPException(400, f"Live lead trigger expects numeric crm_id, got {body.cliente_id!r}")
        rows = sb.table("leads_real").select("crm_id, name, telephone").eq("crm_id", crm_id).execute().data
        if not rows:
            raise HTTPException(404, "Lead não encontrada no espelho CRM")
        return {
            "nome": rows[0]["name"], "telefone": rows[0].get("telephone"),
            "is_lead": True, "source": "live", "cliente_crm_id": rows[0]["crm_id"],
        }

    if body.trigger in LIVE_TRIGGERS:
        # cliente_id is the crm_id (bigint as string)
        try:
            crm_id = int(body.cliente_id)
        except (TypeError, ValueError):
            raise HTTPException(400, f"Live trigger expects numeric crm_id, got {body.cliente_id!r}")
        rows = sb.table("clientes_real").select("crm_id, name, telephone").eq("crm_id", crm_id).execute().data
        if not rows:
            raise HTTPException(404, "Cliente não encontrado no espelho CRM")
        return {
            "nome": rows[0]["name"], "telefone": rows[0].get("telephone"),
            "is_lead": False, "source": "live", "cliente_crm_id": rows[0]["crm_id"],
        }

    # mock path
    rows = sb.table("clientes").select("id, nome, telefone").eq("id", body.cliente_id).execute().data
    if not rows:
        raise HTTPException(404, "Cliente não encontrado")
    return {
        "nome": rows[0]["nome"], "telefone": rows[0].get("telefone"),
        "is_lead": False, "source": "mock", "cliente_uuid": rows[0]["id"],
    }


def _first_demo_recipient() -> str | None:
    rs = [r.strip() for r in (settings.DEMO_RECIPIENTS or "").split(",") if r.strip()]
    return rs[0] if rs else None


def _load_context(sb, body: FireBody, cli: dict) -> dict:
    ctx = {"nome": cli["nome"]}
    if body.apolice_id and cli["source"] == "mock":
        a = sb.table("apolices").select("ramo").eq("id", body.apolice_id).execute().data
        if a:
            ctx["ramo"] = a[0].get("ramo")
    if body.processo_id and body.trigger == "doc_atraso" and cli["source"] == "live":
        try:
            p_crm_id = int(body.processo_id)
        except (TypeError, ValueError):
            p_crm_id = None
        if p_crm_id:
            p = sb.table("processos_real").select(
                "docs_mandatory, docs_uploaded, type_name, updated_on_crm"
            ).eq("crm_id", p_crm_id).execute().data
            if p:
                falta = (p[0].get("docs_mandatory") or 0) - (p[0].get("docs_uploaded") or 0)
                ctx["docs_em_falta"] = [f"{falta} documento(s) pendente(s)"] if falta > 0 else []
                upd = _parse(p[0].get("updated_on_crm"))
                if upd:
                    dias = (_today() - upd).days
                    ctx["stage"] = _doc_atraso_stage(dias)["key"]
    elif body.processo_id and cli["source"] == "mock":
        p = sb.table("processos").select("documentos_em_falta").eq("id", body.processo_id).execute().data
        if p:
            ctx["docs_em_falta"] = p[0].get("documentos_em_falta") or []
    return ctx


@router.post("/preview")
def preview_trigger(body: FireBody):
    sb = supabase()
    cli = _load_recipient(sb, body)
    ctx = _load_context(sb, body, cli)
    msg = _template(body.trigger, ctx)
    cliente_phone = cli.get("telefone") or ""
    demo_phone = _first_demo_recipient()
    return {
        "preview": msg,
        "cliente_nome": cli["nome"],
        "cliente_telefone": cliente_phone,
        "demo_redirect_to": demo_phone if not is_demo_recipient(cliente_phone) else None,
        "data_source": cli["source"],
    }


@router.post("/fire")
async def fire_trigger(body: FireBody):
    sb = supabase()
    cli = _load_recipient(sb, body)
    ctx = _load_context(sb, body, cli)
    msg = body.mensagem_override.strip() if body.mensagem_override else _template(body.trigger, ctx)

    cliente_phone = cli.get("telefone") or ""
    demo_redirected = False
    if body.telefone_override and is_demo_recipient(body.telefone_override):
        to = body.telefone_override
    elif is_demo_recipient(cliente_phone):
        to = cliente_phone
    else:
        to = _first_demo_recipient() or ""
        demo_redirected = bool(to)

    is_real_send = bool(to) and is_demo_recipient(to)
    wa_resp = await send_text(to, msg) if is_real_send else {"stub": True, "to": to, "body": msg}
    meta_id = (wa_resp.get("messages") or [{}])[0].get("id") if isinstance(wa_resp, dict) else None

    # uuid cliente_id only for mock + non-lead path; live triggers use cliente_crm_id
    trigger_cliente_id = cli.get("cliente_uuid") if cli["source"] == "mock" and not cli.get("is_lead") else None
    trigger_cliente_crm_id = cli.get("cliente_crm_id")

    processo_uuid = body.processo_id if cli["source"] == "mock" else None
    processo_crm_id = None
    if cli["source"] == "live" and body.processo_id:
        try:
            processo_crm_id = int(body.processo_id)
        except (TypeError, ValueError):
            processo_crm_id = None

    fired = sb.table("triggers_fired").insert({
        "cliente_id": trigger_cliente_id,
        "cliente_crm_id": trigger_cliente_crm_id,
        "processo_id": processo_uuid,
        "processo_crm_id": processo_crm_id,
        "apolice_id": body.apolice_id if cli["source"] == "mock" else None,
        "trigger_type": body.trigger,
        "canal": "whatsapp",
        "mensagem": msg,
        "meta_wa_message_id": meta_id,
        "status": "enviado" if is_real_send else "agendado",
    }).execute().data[0]

    if to:
        sb.table("mensagens").insert({
            "cliente_id": trigger_cliente_id,
            "cliente_crm_id": trigger_cliente_crm_id,
            "to_e164": to,
            "canal": "whatsapp",
            "corpo": msg,
            "meta_wa_message_id": meta_id,
            "trigger_id": fired["id"],
            "status": "sent" if is_real_send else "stubbed",
        }).execute()

    return {
        "trigger": body.trigger,
        "preview": msg,
        "sent": is_real_send,
        "to": to,
        "cliente_nome": cli["nome"],
        "cliente_telefone": cliente_phone,
        "demo_redirected": demo_redirected,
        "data_source": cli["source"],
        "wa_response": wa_resp,
        "fired_id": fired["id"],
    }
