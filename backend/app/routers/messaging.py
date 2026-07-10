"""Messaging — generic communication layer API.

  GET  /config           channel throttle/sender settings           (messaging.config)
  PUT  /config/{canal}    update a channel                           (messaging.config)
  POST /send              enqueue a message to recipients            (messaging.send)
  GET  /queue             queue status + recent envios               (messaging.config)
  POST /dispatch          send due messages now (also run by cron)   (messaging.config)
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..core import evolution as evo
from ..core.channels import CHANNELS
from ..core.dispatcher import enqueue, enqueue_many, process_due
from ..core.scope import require_cap
from ..db import supabase
from .auth import COOKIE_NAME, token_user

router = APIRouter()


def _acting_username(request: Request) -> str | None:
    return token_user(request.cookies.get(COOKIE_NAME))


@router.get("/config")
def get_config(request: Request):
    require_cap(request, "messaging.config")
    rows = supabase().table("messaging_config").select("*").order("canal").execute().data or []
    return {"config": rows}


class ConfigIn(BaseModel):
    ativo: bool | None = None
    batch_size: int | None = None
    intervalo_segundos: int | None = None
    cap_diario: int | None = None
    remetente: str | None = None


@router.put("/config/{canal}")
def put_config(canal: str, body: ConfigIn, request: Request):
    require_cap(request, "messaging.config")
    if canal not in CHANNELS:
        raise HTTPException(404, "Canal desconhecido.")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        return {"ok": True}
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    supabase().table("messaging_config").update(patch).eq("canal", canal).execute()
    return {"ok": True}


class SendIn(BaseModel):
    canal: str
    destinatarios: list[str]
    corpo: str
    assunto: str | None = None
    ref_tipo: str | None = "sistema"
    ref_id: str | None = None


@router.post("/send")
def send(body: SendIn, request: Request):
    """Enqueue a message to one or more recipients over a channel (throttled by config)."""
    require_cap(request, "messaging.send")
    if body.canal not in CHANNELS:
        raise HTTPException(400, "Canal desconhecido.")
    if not body.destinatarios:
        raise HTTPException(400, "Sem destinatários.")
    if not (body.corpo or "").strip():
        raise HTTPException(400, "Mensagem vazia.")
    user = token_user(request.cookies.get(COOKIE_NAME))
    return enqueue(
        body.canal,
        body.destinatarios,
        body.corpo,
        assunto=body.assunto,
        ref_tipo=body.ref_tipo or "sistema",
        ref_id=body.ref_id,
        criado_por=user,
    )


@router.get("/queue")
def queue(request: Request):
    require_cap(request, "messaging.config")
    sb = supabase()

    def _count(status: str) -> int:
        return (
            sb.table("envios").select("id", count="exact").eq("status", status).limit(1).execute().count or 0
        )

    recent = (
        sb.table("envios")
        .select("id, canal, destinatario, status, ref_tipo, agendado_para, enviado_em, erro")
        .order("id", desc=True)
        .limit(50)
        .execute()
        .data
        or []
    )
    return {
        "pendentes": _count("pendente"),
        "enviados": _count("enviado"),
        "falhados": _count("falhou"),
        "recent": recent,
    }


@router.post("/dispatch")
def dispatch(request: Request):
    """Send due messages now. Idempotent; also invoked by the cron worker."""
    require_cap(request, "messaging.config")
    return process_due()


# ---- WhatsApp (Evolution) — each user connects their OWN number ----------
@router.get("/whatsapp/status")
def wa_status(request: Request):
    require_cap(request, "messaging.send")
    if not evo.configured():
        return {"configured": False, "instance": None, "connected": False, "state": None}
    username = _acting_username(request)
    sb = supabase()
    row = (
        sb.table("platform_users").select("evolution_instance").eq("username", username).limit(1).execute().data
        or [None]
    )[0]
    # Resolve deterministically (ds_<username>) so a login without a stored instance
    # — e.g. the env-admin 'ds' — still reflects a live WhatsApp connection.
    inst = (row or {}).get("evolution_instance") or evo.instance_name_for(username or "")
    st = evo.connection_state(inst)
    connected = bool(st.get("connected"))
    profile = evo.instance_profile(inst) if connected else {}
    return {
        "configured": True,
        "instance": inst,
        "connected": connected,
        "state": st.get("state"),
        "profile_name": profile.get("profileName"),
        "numero": profile.get("numero"),
    }


@router.post("/whatsapp/connect")
def wa_connect(request: Request):
    """Create (if needed) the acting user's WhatsApp instance and return the QR to scan."""
    require_cap(request, "messaging.send")
    if not evo.configured():
        raise HTTPException(400, "O serviço WhatsApp (Evolution) não está configurado no servidor.")
    username = _acting_username(request)
    sb = supabase()
    row = (
        sb.table("platform_users").select("id, evolution_instance").eq("username", username).limit(1).execute().data
        or [None]
    )[0]
    inst = (row or {}).get("evolution_instance") or evo.instance_name_for(username or "user")
    evo.create_instance(inst)  # tolerated if it already exists
    if row and not row.get("evolution_instance"):
        sb.table("platform_users").update({"evolution_instance": inst}).eq("id", row["id"]).execute()
    conn = evo.connect_instance(inst)
    return {"configured": True, "instance": inst, "qr": conn.get("qr"), "code": conn.get("code")}


@router.post("/whatsapp/logout")
def wa_logout(request: Request):
    require_cap(request, "messaging.send")
    username = _acting_username(request)
    sb = supabase()
    row = (
        sb.table("platform_users").select("evolution_instance").eq("username", username).limit(1).execute().data
        or [None]
    )[0]
    inst = (row or {}).get("evolution_instance") or evo.instance_name_for(username or "")
    if inst:
        evo.logout_instance(inst)
    return {"ok": True}


def _wa_number(raw: str | None) -> str | None:
    """Digits-only number with PT country code (no +) for Evolution."""
    if not raw:
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if not digits:
        return None
    if len(digits) == 9 and digits[0] == "9":
        digits = "351" + digits
    return digits


def _user_instance(sb, username: str | None) -> str:
    row = (
        sb.table("platform_users").select("evolution_instance").eq("username", username).limit(1).execute().data
        or [None]
    )[0]
    return (row or {}).get("evolution_instance") or evo.instance_name_for(username or "")


# ---- WhatsApp composer: send (with optional schedule) + history ----------
class WaSendIn(BaseModel):
    numero: str
    corpo: str
    agendado_para: str | None = None  # ISO datetime; None = enviar já


@router.post("/whatsapp/send")
def wa_send(body: WaSendIn, request: Request):
    """Send/schedule a WhatsApp message from the acting user's own number."""
    require_cap(request, "messaging.send")
    dest = _wa_number(body.numero)
    if not dest:
        raise HTTPException(400, "Número de telemóvel inválido.")
    if not (body.corpo or "").strip():
        raise HTTPException(400, "Mensagem vazia.")
    username = _acting_username(request)
    sb = supabase()
    inst = _user_instance(sb, username)
    r = enqueue_many(
        "whatsapp_evolution",
        [{"destinatario": dest, "corpo": body.corpo}],
        ref_tipo="user_msg",
        criado_por=username,
        canal_conta=inst,
        quando=body.agendado_para,
    )
    return {"enqueued": r["enqueued"], "agendado": bool(body.agendado_para)}


@router.get("/whatsapp/history")
def wa_history(request: Request):
    require_cap(request, "messaging.send")
    username = _acting_username(request)
    rows = (
        supabase()
        .table("envios")
        .select("id, destinatario, corpo, status, agendado_para, enviado_em, erro")
        .eq("canal", "whatsapp_evolution")
        .eq("criado_por", username)
        .order("id", desc=True)
        .limit(50)
        .execute()
        .data
        or []
    )
    return {"mensagens": rows}


@router.get("/whatsapp/clientes")
def search_clientes(request: Request, q: str = ""):
    """Search CRM clients by name for the composer (loja-wide)."""
    require_cap(request, "messaging.send")
    q = (q or "").strip()
    if len(q) < 2:
        return {"clientes": []}
    rows = (
        supabase().table("clientes_real").select("crm_id, name, telephone")
        .ilike("name", f"%{q}%").limit(15).execute().data or []
    )
    return {"clientes": [{"crm_id": r["crm_id"], "nome": r.get("name"), "telefone": r.get("telephone")} for r in rows]}


# ---- Message templates (loja-wide; edit gated on messaging.config) --------
@router.get("/templates")
def list_templates(request: Request):
    require_cap(request, "messaging.send")
    rows = (
        supabase().table("msg_templates").select("id, nome, categoria, corpo, ativo")
        .eq("ativo", True).order("categoria").order("nome").execute().data or []
    )
    return {"templates": rows}


class TemplateIn(BaseModel):
    nome: str | None = None
    categoria: str | None = None
    corpo: str | None = None
    ativo: bool | None = None


@router.post("/templates")
def create_template(body: TemplateIn, request: Request):
    require_cap(request, "messaging.config")
    if not (body.nome and body.corpo):
        raise HTTPException(400, "Nome e corpo são obrigatórios.")
    res = supabase().table("msg_templates").insert(
        {"nome": body.nome, "categoria": body.categoria, "corpo": body.corpo}
    ).execute().data
    return {"ok": True, "id": (res or [{}])[0].get("id")}


@router.put("/templates/{template_id}")
def update_template(template_id: int, body: TemplateIn, request: Request):
    require_cap(request, "messaging.config")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        return {"ok": True}
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    supabase().table("msg_templates").update(patch).eq("id", template_id).execute()
    return {"ok": True}


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, request: Request):
    require_cap(request, "messaging.config")
    supabase().table("msg_templates").delete().eq("id", template_id).execute()
    return {"ok": True}
