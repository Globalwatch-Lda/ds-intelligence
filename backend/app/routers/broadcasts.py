"""Contactos dos consultores + welcome-blast / broadcasts.

Contacts come from the CRM: each consultor's contacts are the clients they own in
ds.clientes_real (raw->>managerName). Extra contacts can still be uploaded/added
manually into ds.contactos_consultor (keyed by the manager name). The welcome-blast
is queued on the WhatsApp (Evolution) channel — throttled — and goes out from the
consultor's OWN number when they have a linked WhatsApp, else the operator's.
"""
from __future__ import annotations
import csv
import io
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel

from ..config import settings
from ..core.dispatcher import enqueue_many
from ..core.evolution import instance_name_for
from ..core.names import fix_name
from ..db import supabase

router = APIRouter()


# --------------------------------------------------------- CRM clients
def _all_clientes(sb) -> list[dict]:
    """All clients with their owning gestor (raw->>managerName) + phone."""
    out: list[dict] = []
    off, PAGE = 0, 1000
    while True:
        chunk = (
            sb.table("clientes_real")
            .select("crm_id, name, telephone, manager_name:raw->>managerName")
            .range(off, off + PAGE - 1)
            .execute()
            .data
            or []
        )
        out.extend(chunk)
        if len(chunk) < PAGE:
            break
        off += PAGE
    return out


def _clientes_do_gestor(sb, consultor_id: str) -> list[dict]:
    """This consultor's contacts: CRM clients (owned by them) + any extra uploaded
    contacts, de-duplicated by phone. consultor_id is the raw managerName."""
    out: list[dict] = []
    seen: set[str] = set()

    def _add(nome, tel):
        t = (tel or "").strip()
        if not t:
            return
        key = "".join(ch for ch in t if ch.isdigit())
        if key and key not in seen:
            seen.add(key)
            out.append({"nome_cliente": nome, "telefone": t})

    for c in _all_clientes(sb):
        if (c.get("manager_name") or "") == consultor_id:
            _add(c.get("name"), c.get("telephone"))
    extra = (
        sb.table("contactos_consultor").select("nome_cliente, telefone")
        .eq("consultor_id", consultor_id).execute().data or []
    )
    for e in extra:
        _add(e.get("nome_cliente"), e.get("telefone"))
    return out


def _consultor_instance(sb, consultor_id: str) -> str | None:
    """The consultor's own WhatsApp instance, if they have an app account whose name
    matches this CRM gestor. None → caller falls back to the operator's number."""
    target = fix_name(consultor_id)
    for u in sb.table("platform_users").select("username, nome, evolution_instance").execute().data or []:
        if fix_name(u.get("nome")) == target:
            return u.get("evolution_instance") or instance_name_for(u.get("username") or "")
    return None


def _welcome_template(loja: str) -> str:
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
    return {"template": _welcome_template(settings.LOJA_NAME)}


@router.get("/consultores")
def list_consultores_com_contagem(request: Request):
    """Consultores (owning gestores from the CRM) + how many contacts each has.
    n_contactos = clients owned in clientes_real + any extra uploaded contacts."""
    sb = supabase()
    counts: dict[str, int] = {}
    for c in _all_clientes(sb):
        m = c.get("manager_name")
        if m:
            counts[m] = counts.get(m, 0) + 1
    extra = sb.table("contactos_consultor").select("consultor_id").execute().data or []
    for e in extra:
        cid = e.get("consultor_id")
        if cid and cid not in counts:
            counts[cid] = 0
        if cid:
            counts[cid] += 1
    out = [
        {"id": m, "nome": fix_name(m), "cargo": "Consultor", "n_contactos": n}
        for m, n in counts.items()
    ]
    return {"consultores": sorted(out, key=lambda g: (-g["n_contactos"], g["nome"] or ""))}


@router.get("/contactos")
def list_contactos(consultor_id: str):
    contactos = _clientes_do_gestor(supabase(), consultor_id)
    return {"contactos": [{"id": i, **c} for i, c in enumerate(contactos)]}


@router.post("/upload")
async def upload_contactos(file: UploadFile = File(...)):
    """CSV: Nome do Consultor, Nome do Cliente, Número de contacto — extra contacts
    added on top of the CRM clients (matched to a gestor by name)."""
    sb = supabase()
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))

    def norm(s: str) -> str:
        return s.strip().lower().replace(" do ", "_").replace(" de ", "_").replace(" ", "_")

    # Known gestores (raw managerName) → match CSV names by fixed form.
    managers = {c.get("manager_name") for c in _all_clientes(sb) if c.get("manager_name")}
    fixed_to_raw = {fix_name(m): m for m in managers}

    inserted: dict[str, int] = {}
    skipped = 0
    rows_to_insert = []
    for raw_row in reader:
        row = {norm(k): (v or "").strip() for k, v in raw_row.items()}
        nome_consultor = row.get("nome_consultor") or row.get("consultor") or ""
        nome_cliente = row.get("nome_cliente") or row.get("cliente") or ""
        telefone = row.get("número_contacto") or row.get("numero_contacto") or row.get("telefone") or ""
        if not (nome_consultor and nome_cliente and telefone):
            skipped += 1
            continue
        cid = fixed_to_raw.get(fix_name(nome_consultor))
        if not cid:
            skipped += 1
            continue
        rows_to_insert.append({
            "consultor_id": cid,
            "nome_cliente": nome_cliente,
            "telefone": telefone if telefone.startswith("+") else f"+351{telefone.lstrip('0')}",
        })
        inserted[cid] = inserted.get(cid, 0) + 1
    if rows_to_insert:
        sb.table("contactos_consultor").insert(rows_to_insert).execute()
    return {"inserted_total": len(rows_to_insert), "skipped": skipped, "by_consultor": inserted}


class ManualContactsBody(BaseModel):
    consultor_id: str
    contactos: list[dict]


@router.post("/contactos/add")
def add_contactos_manual(body: ManualContactsBody):
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
    template: str | None = None


@router.post("/preview")
def preview_broadcast(body: BroadcastBody):
    sb = supabase()
    nome_consultor = fix_name(body.consultor_id) or body.consultor_id
    contactos = _clientes_do_gestor(sb, body.consultor_id)
    template = body.template or _welcome_template(settings.LOJA_NAME)
    sample = contactos[0] if contactos else {"nome_cliente": "(exemplo)"}
    instance = _consultor_instance(sb, body.consultor_id)
    return {
        "consultor_nome": nome_consultor,
        "n_contactos": len(contactos),
        "sample_recipient": sample["nome_cliente"],
        "sample_message": _render(template, nome_consultor, sample["nome_cliente"]),
        "template": template,
        "por_numero_proprio": bool(instance),
    }


@router.post("/send")
def send_broadcast(body: BroadcastBody, request: Request):
    """Queue the blast on the WhatsApp (Evolution) channel — throttled — from the
    consultor's own number when linked, else the operator's."""
    from .auth import COOKIE_NAME, token_user

    sb = supabase()
    nome_consultor = fix_name(body.consultor_id) or body.consultor_id
    contactos = _clientes_do_gestor(sb, body.consultor_id)
    if not contactos:
        raise HTTPException(400, "Este consultor não tem contactos com telefone.")

    template = body.template or _welcome_template(settings.LOJA_NAME)
    instance = _consultor_instance(sb, body.consultor_id)
    user = token_user(request.cookies.get(COOKIE_NAME))

    def _num(raw: str) -> str | None:
        digits = "".join(ch for ch in str(raw) if ch.isdigit())
        if not digits:
            return None
        return "351" + digits if len(digits) == 9 and digits[0] == "9" else digits

    itens = []
    for c in contactos:
        dest = _num(c["telefone"])
        if dest:
            itens.append({"destinatario": dest, "corpo": _render(template, nome_consultor, c["nome_cliente"])})

    r = enqueue_many(
        "whatsapp_evolution", itens,
        ref_tipo=body.tipo, ref_id=body.consultor_id, criado_por=user, canal_conta=instance,
    )
    sb.table("broadcasts").insert({
        "consultor_id": body.consultor_id, "tipo": body.tipo, "template": template,
        "destinatarios_count": r["enqueued"], "enviado_em": datetime.now(timezone.utc).isoformat(),
    }).execute()
    return {"consultor_nome": nome_consultor, "enqueued": r["enqueued"], "total": len(contactos), "por_numero_proprio": bool(instance)}


@router.get("/history")
def broadcast_history(limit: int = 30):
    rows = supabase().table("broadcasts").select(
        "id, consultor_id, tipo, template, enviado_em, destinatarios_count, enviados_ok, enviados_falha, created_at"
    ).order("created_at", desc=True).limit(limit).execute().data
    return {"broadcasts": rows}
