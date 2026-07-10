"""Welcome blast + custom broadcasts to a consultant's personal contact list.

Flow:
  1. Operator uploads CSV (Nome do Consultor, Nome do Cliente, Número de contacto)
     — we resolve consultor name to gestor_id (best-effort fuzzy match) and bulk-insert
     into ds.contactos_consultor.
  2. Operator clicks "Boas-vindas" on a consultor → fires the welcome template
     ("o {{nome_consultor}} está agora a colaborar com a DS…") to every contact.
  3. Operator can also send a custom broadcast with {{nome_consultor}} and
     {{nome_cliente}} placeholders.

For the demo, sends respect the same DEMO_RECIPIENTS auto-redirect as triggers —
synthetic contact numbers redirect to the first verified demo recipient so the
operator sees the actual delivery during the meeting.
"""
from __future__ import annotations
import csv
import io
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel

from ..config import settings
from ..core.names import fix_name
from ..core.scope import apply_scope, user_scope
from ..core.wa_client import send_text, is_demo_recipient
from ..db import supabase

router = APIRouter()


def _crm_consultores(sb, scope=None) -> list[dict]:
    """Distinct consultores from the CRM (processos_real managers), optionally scoped.
    Returns [{crm_id, nome}]."""
    q = apply_scope(sb.table("processos_real").select("manager_crm_id, manager_name"), scope)
    rows = q.execute().data or []
    seen: dict = {}
    for r in rows:
        mid = r.get("manager_crm_id")
        if mid is None:
            continue
        seen.setdefault(mid, fix_name(r.get("manager_name")))
    return [{"crm_id": mid, "nome": nome} for mid, nome in seen.items()]


def _consultor_nome(sb, consultor_id: str) -> str | None:
    """Consultor display name from the CRM by manager_crm_id (stored as text)."""
    try:
        mid = int(consultor_id)
    except (ValueError, TypeError):
        return None
    r = sb.table("processos_real").select("manager_name").eq("manager_crm_id", mid).limit(1).execute().data
    return fix_name(r[0]["manager_name"]) if r else None


def _first_demo_recipient() -> str | None:
    rs = [r.strip() for r in (settings.DEMO_RECIPIENTS or "").split(",") if r.strip()]
    return rs[0] if rs else None


def _welcome_template(loja: str) -> str:
    """Default welcome blast template. The placeholders are filled per-recipient."""
    return (
        "Olá {{nome_cliente}}, é o {{nome_consultor}}.\n\n"
        f"Quero informar que, desde já, estou a colaborar com a {loja} "
        "como consultor de crédito e seguros. Terei muito gosto em ser-lhe útil "
        "sempre que necessitar — análise de crédito habitação, refinanciamento, "
        "revisão de seguros ou qualquer outra questão financeira.\n\n"
        "Não hesite em contactar-me. Estou disponível.\n\n"
        "Um abraço,\n{{nome_consultor}}"
    )


def _render(template: str, nome_consultor: str, nome_cliente: str) -> str:
    return (template
            .replace("{{nome_consultor}}", nome_consultor or "")
            .replace("{{nome_cliente}}", nome_cliente or ""))


# --------------------------------------------------------- contacts CRUD


@router.get("/welcome-template")
def get_welcome_template():
    """The default welcome-blast message, so the UI can show it and let the
    operator edit it before sending."""
    return {"template": _welcome_template(settings.LOJA_NAME)}


@router.get("/consultores")
def list_consultores_com_contagem(request: Request):
    """Consultores from the CRM (scoped to the acting user) + how many personal
    contacts each has loaded. The contacts themselves are uploaded per consultor —
    the CRM doesn't hold those, so counts start at 0 until loaded."""
    sb = supabase()
    consultores = _crm_consultores(sb, user_scope(request))
    contactos = sb.table("contactos_consultor").select("consultor_id").execute().data or []
    counts: dict[str, int] = {}
    for c in contactos:
        cid = str(c["consultor_id"])
        counts[cid] = counts.get(cid, 0) + 1
    out = [
        {
            "id": str(c["crm_id"]),
            "nome": c["nome"] or f"Gestor {c['crm_id']}",
            "cargo": "Consultor",
            "n_contactos": counts.get(str(c["crm_id"]), 0),
        }
        for c in consultores
    ]
    return {"consultores": sorted(out, key=lambda g: (-g["n_contactos"], g["nome"] or ""))}


@router.get("/contactos")
def list_contactos(consultor_id: str):
    rows = supabase().table("contactos_consultor").select(
        "id, nome_cliente, telefone, email, created_at"
    ).eq("consultor_id", consultor_id).order("created_at", desc=True).execute().data
    return {"contactos": rows}


@router.post("/upload")
async def upload_contactos(file: UploadFile = File(...)):
    """CSV upload. Expected columns (header row, case-insensitive):
       Nome do Consultor, Nome do Cliente, Número de contacto

    Returns a summary of how many rows inserted per consultor (matched by name).
    """
    sb = supabase()
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))

    # Normalise headers
    def norm(s: str) -> str:
        return s.strip().lower().replace(" do ", "_").replace(" de ", "_").replace(" ", "_")

    consultores = _crm_consultores(sb)
    name_to_id = {c["nome"].lower().strip(): str(c["crm_id"]) for c in consultores if c["nome"]}

    inserted: dict[str, int] = {}
    skipped = 0
    rows_to_insert = []

    for raw_row in reader:
        row = {norm(k): (v or "").strip() for k, v in raw_row.items()}
        nome_consultor = row.get("nome_consultor") or row.get("consultor") or ""
        nome_cliente   = row.get("nome_cliente") or row.get("cliente") or ""
        telefone       = row.get("número_contacto") or row.get("numero_contacto") or row.get("telefone") or ""
        if not (nome_consultor and nome_cliente and telefone):
            skipped += 1
            continue
        consultor_id = name_to_id.get(nome_consultor.lower().strip())
        if not consultor_id:
            # Fallback: first-name partial match against CRM consultores
            parts = nome_consultor.lower().split()
            for c in consultores:
                c_parts = (c["nome"] or "").lower().split()
                if parts and c_parts and parts[0] == c_parts[0]:
                    consultor_id = str(c["crm_id"])
                    break
        if not consultor_id:
            skipped += 1
            continue
        rows_to_insert.append({
            "consultor_id": consultor_id,
            "nome_cliente": nome_cliente,
            "telefone": telefone if telefone.startswith("+") else f"+351{telefone.lstrip('0')}",
        })
        inserted[consultor_id] = inserted.get(consultor_id, 0) + 1

    if rows_to_insert:
        sb.table("contactos_consultor").insert(rows_to_insert).execute()

    return {
        "inserted_total": len(rows_to_insert),
        "skipped": skipped,
        "by_consultor_id": inserted,
    }


class ManualContactsBody(BaseModel):
    consultor_id: str
    contactos: list[dict]   # each: {nome_cliente, telefone, email?}


@router.post("/contactos/add")
def add_contactos_manual(body: ManualContactsBody):
    """Add contacts without CSV upload — useful for the demo to quickly seed."""
    sb = supabase()
    rows = []
    for c in body.contactos:
        if not c.get("nome_cliente") or not c.get("telefone"):
            continue
        rows.append({
            "consultor_id": body.consultor_id,
            "nome_cliente": c["nome_cliente"],
            "telefone": c["telefone"],
            "email": c.get("email"),
        })
    if rows:
        sb.table("contactos_consultor").insert(rows).execute()
    return {"inserted": len(rows)}


# --------------------------------------------------------- broadcasts


class BroadcastBody(BaseModel):
    consultor_id: str
    tipo: Literal["welcome", "custom"] = "welcome"
    template: str | None = None      # for custom; if None and tipo=welcome we use default


@router.post("/preview")
def preview_broadcast(body: BroadcastBody):
    sb = supabase()
    nome_consultor = _consultor_nome(sb, body.consultor_id)
    if not nome_consultor:
        raise HTTPException(404, "Consultor não encontrado")

    contactos = sb.table("contactos_consultor").select(
        "id, nome_cliente, telefone"
    ).eq("consultor_id", body.consultor_id).execute().data

    template = body.template or _welcome_template(settings.LOJA_NAME)
    sample = contactos[0] if contactos else {"nome_cliente": "(exemplo)", "telefone": ""}
    sample_render = _render(template, nome_consultor, sample["nome_cliente"])

    demo_phone = _first_demo_recipient()
    redirect_count = sum(1 for c in contactos if not is_demo_recipient(c["telefone"]))

    return {
        "consultor_nome": nome_consultor,
        "n_contactos": len(contactos),
        "sample_recipient": sample["nome_cliente"],
        "sample_message": sample_render,
        "template": template,
        "demo_redirect_to": demo_phone,
        "demo_redirect_count": redirect_count,
    }


@router.post("/send")
async def send_broadcast(body: BroadcastBody):
    sb = supabase()
    nome_consultor = _consultor_nome(sb, body.consultor_id)
    if not nome_consultor:
        raise HTTPException(404, "Consultor não encontrado")

    contactos = sb.table("contactos_consultor").select(
        "id, nome_cliente, telefone"
    ).eq("consultor_id", body.consultor_id).execute().data
    if not contactos:
        raise HTTPException(400, "Este consultor ainda não tem contactos carregados.")

    template = body.template or _welcome_template(settings.LOJA_NAME)
    demo_fallback = _first_demo_recipient()

    bc = sb.table("broadcasts").insert({
        "consultor_id": body.consultor_id,
        "tipo": body.tipo,
        "template": template,
        "destinatarios_count": len(contactos),
    }).execute().data[0]

    ok = 0
    fail = 0
    results = []

    for c in contactos:
        msg = _render(template, nome_consultor, c["nome_cliente"])
        to_phone = c["telefone"] if is_demo_recipient(c["telefone"]) else demo_fallback
        if not to_phone:
            fail += 1
            results.append({"to": c["telefone"], "ok": False, "reason": "no_demo_recipient_configured"})
            continue
        try:
            resp = await send_text(to_phone, msg)
            if isinstance(resp, dict) and resp.get("meta_error"):
                fail += 1
                results.append({"to": to_phone, "ok": False, "meta": resp.get("body")})
                continue
            ok += 1
            results.append({"to": to_phone, "ok": True, "for_cliente": c["nome_cliente"]})
            sb.table("mensagens").insert({
                "to_e164": to_phone,
                "canal": "whatsapp",
                "corpo": msg,
                "status": "sent",
            }).execute()
        except Exception as e:
            fail += 1
            results.append({"to": to_phone, "ok": False, "error": str(e)})

    sb.table("broadcasts").update({
        "enviado_em": "now()",
        "enviados_ok": ok,
        "enviados_falha": fail,
    }).eq("id", bc["id"]).execute()

    return {
        "broadcast_id": bc["id"],
        "consultor_nome": nome_consultor,
        "total": len(contactos),
        "ok": ok,
        "fail": fail,
        "results": results,
    }


@router.get("/history")
def broadcast_history(limit: int = 30):
    rows = supabase().table("broadcasts").select(
        "id, consultor_id, tipo, template, enviado_em, destinatarios_count, enviados_ok, enviados_falha, created_at"
    ).order("created_at", desc=True).limit(limit).execute().data
    return {"broadcasts": rows}
