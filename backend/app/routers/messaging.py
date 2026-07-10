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
from ..core.dispatcher import enqueue, process_due
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
    return {"configured": True, "instance": inst, "connected": st.get("connected"), "state": st.get("state")}


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
