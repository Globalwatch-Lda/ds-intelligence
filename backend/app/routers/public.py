"""Public, unauthenticated endpoints (exempt from the session gate in main.py):

  POST /api/public/unsubscribe        one-click marketing opt-out (signed token)
  GET  /api/public/unsubscribe/check  validate a token before showing the page
  POST /api/public/ses-events         AWS SNS webhook for SES bounces/complaints

Both mutate only the marketing-consent flag (clientes_real.authorized_contact), a
low-harm, reversible action. The SES webhook verifies the SNS message signature.
"""
from __future__ import annotations

import base64
import json
import logging
import urllib.request
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..core.tokens import read_unsub_token
from ..db import supabase

router = APIRouter()
log = logging.getLogger("ds.public")


def _crm_val(crm_id: str):
    s = str(crm_id)
    return int(s) if s.lstrip("-").isdigit() else crm_id


def _clear_consent_by_crm(crm_id: str) -> None:
    supabase().table("clientes_real").update({"authorized_contact": False}).eq(
        "crm_id", _crm_val(crm_id)
    ).execute()


def _clear_consent_by_email(email: str) -> None:
    if email:
        supabase().table("clientes_real").update({"authorized_contact": False}).eq("email", email).execute()


# ---- unsubscribe ---------------------------------------------------------
class UnsubBody(BaseModel):
    t: str


@router.get("/unsubscribe/check")
def unsubscribe_check(t: str):
    return {"valid": bool(read_unsub_token(t))}


@router.post("/unsubscribe")
def unsubscribe(body: UnsubBody):
    crm_id = read_unsub_token(body.t)
    if not crm_id:
        raise HTTPException(400, "Ligação inválida ou expirada.")
    _clear_consent_by_crm(crm_id)
    return {"ok": True}


# ---- SES bounce/complaint webhook (AWS SNS) ------------------------------
def _sns_verify(msg: dict) -> bool:
    """Verify an SNS message signature (SignatureVersion 1/2). Returns False on any
    problem, so a bad/forged message is ignored rather than trusted."""
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.x509 import load_pem_x509_certificate

        cert_url = msg.get("SigningCertURL") or msg.get("SigningCertUrl")
        host = urlparse(cert_url).hostname or ""
        if not (cert_url.startswith("https://") and host.endswith(".amazonaws.com")):
            return False
        mtype = msg.get("Type")
        if mtype == "Notification":
            keys = ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"]
        else:  # SubscriptionConfirmation / UnsubscribeConfirmation
            keys = ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"]
        canonical = "".join(f"{k}\n{msg[k]}\n" for k in keys if k in msg)
        with urllib.request.urlopen(cert_url, timeout=10) as r:  # noqa: S310 (validated amazonaws host)
            cert = load_pem_x509_certificate(r.read())
        algo = hashes.SHA256() if msg.get("SignatureVersion") == "2" else hashes.SHA1()
        cert.public_key().verify(
            base64.b64decode(msg["Signature"]), canonical.encode(), padding.PKCS1v15(), algo
        )
        return True
    except Exception as e:
        log.warning("[public] SNS signature verify failed: %s", e)
        return False


@router.post("/ses-events")
async def ses_events(request: Request):
    """AWS SNS → SES bounce/complaint notifications. Confirms the subscription and,
    on a permanent bounce or a complaint, clears that recipient's marketing consent."""
    try:
        msg = json.loads(await request.body())
    except (ValueError, TypeError):
        raise HTTPException(400, "Payload inválido.")
    if not _sns_verify(msg):
        raise HTTPException(403, "Assinatura SNS inválida.")

    mtype = msg.get("Type")
    if mtype in ("SubscriptionConfirmation", "UnsubscribeConfirmation"):
        try:
            urllib.request.urlopen(msg["SubscribeURL"], timeout=10).read()  # noqa: S310
        except Exception as e:
            log.warning("[public] SNS subscribe confirm failed: %s", e)
        return {"ok": True}

    if mtype == "Notification":
        inner = json.loads(msg.get("Message") or "{}")
        ntype = inner.get("notificationType") or inner.get("eventType")
        emails: list[str] = []
        if ntype == "Bounce" and (inner.get("bounce") or {}).get("bounceType") == "Permanent":
            emails = [r.get("emailAddress") for r in inner["bounce"].get("bouncedRecipients", [])]
        elif ntype == "Complaint":
            emails = [r.get("emailAddress") for r in (inner.get("complaint") or {}).get("complainedRecipients", [])]
        for e in emails:
            _clear_consent_by_email(e)
        if emails:
            log.info("[public] SES %s → cleared consent for %d recipient(s)", ntype, len(emails))
    return {"ok": True}
