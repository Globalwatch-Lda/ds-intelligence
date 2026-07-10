"""Signed, stateless tokens for public one-click actions (e.g. unsubscribe).

An unsubscribe token binds a client's CRM id with an HMAC over the app session
secret, so the public link can't be forged or enumerated. No DB table needed.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

from ..config import settings


def _sign(payload: str) -> str:
    sig = hmac.new(settings.APP_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def make_unsub_token(crm_id) -> str:
    return f"{crm_id}.{_sign(f'unsub.{crm_id}')}"


def read_unsub_token(token: str | None) -> str | None:
    """Return the crm_id (as string) if the token is well-formed and correctly
    signed; else None. Fails closed when there is no session secret."""
    if not token or not settings.APP_SESSION_SECRET:
        return None
    try:
        crm_id, sig = token.rsplit(".", 1)
    except (ValueError, AttributeError):
        return None
    if not crm_id or not hmac.compare_digest(sig, _sign(f"unsub.{crm_id}")):
        return None
    return crm_id
