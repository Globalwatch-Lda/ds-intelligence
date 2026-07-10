"""Outbound channel adapters — a generic communication layer.

Each adapter sends ONE message and returns {'delivered': bool, 'error': str|None}.
When a channel's service isn't configured (no SES identity, no AWS creds, no
Evolution instance) the adapter stays inert — it logs and returns delivered=False
instead of raising, so the platform never crashes on a missing credential. The
dispatcher only ever calls a channel that an operator has marked `ativo` in
ds.messaging_config, so nothing is sent (or billed) until it is deliberately turned on.

Channels are content-agnostic: email/SMS/WhatsApp are reusable for ANY platform
communication (to colaboradores or clientes), not just newsletters.
"""
from __future__ import annotations

import json
import logging
import urllib.request

from ..config import settings
from .mailer import send_email

log = logging.getLogger("ds.channels")

CHANNELS = ("email", "sms", "whatsapp_evolution")


def _send_email(dest: str, assunto: str | None, corpo: str) -> dict:
    # corpo may be HTML (newsletter) or plain text; either renders acceptably.
    return send_email(dest, assunto or "Mensagem da DS Crédito", corpo, text_body=corpo)


def _send_sms(dest: str, corpo: str, remetente: str | None) -> dict:
    try:
        import boto3  # lazy: only when SMS is actually attempted

        sns = boto3.client("sns", region_name=settings.AWS_SMS_REGION)
        attrs: dict = {"AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"}}
        sender = remetente or settings.SMS_SENDER
        if sender:
            attrs["AWS.SNS.SMS.SenderID"] = {"DataType": "String", "StringValue": sender}
        sns.publish(PhoneNumber=dest, Message=corpo, MessageAttributes=attrs)
        return {"delivered": True, "error": None}
    except Exception as e:  # missing boto3 / creds / origination
        log.error("[channels] SMS send failed to %s: %s", dest, e)
        return {"delivered": False, "error": str(e)}


def _send_evolution(dest: str, corpo: str) -> dict:
    url, key, inst = settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY, settings.EVOLUTION_INSTANCE
    if not (url and key and inst):
        log.warning("[channels] Evolution not configured — would WhatsApp %s", dest)
        return {"delivered": False, "error": "evolution not configured"}
    try:
        payload = json.dumps({"number": dest, "text": corpo}).encode("utf-8")
        req = urllib.request.Request(
            f"{url.rstrip('/')}/message/sendText/{inst}",
            data=payload,
            headers={"Content-Type": "application/json", "apikey": key},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (trusted, configured URL)
            resp.read()
        return {"delivered": True, "error": None}
    except Exception as e:
        log.error("[channels] Evolution send failed to %s: %s", dest, e)
        return {"delivered": False, "error": str(e)}


def send_now(canal: str, destinatario: str, assunto: str | None, corpo: str, remetente: str | None = None) -> dict:
    """Dispatch a single message over `canal`. Never raises."""
    if canal == "email":
        return _send_email(destinatario, assunto, corpo)
    if canal == "sms":
        return _send_sms(destinatario, corpo, remetente)
    if canal == "whatsapp_evolution":
        return _send_evolution(destinatario, corpo)
    return {"delivered": False, "error": f"canal desconhecido: {canal}"}
