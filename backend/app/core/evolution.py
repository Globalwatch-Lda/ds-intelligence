"""Evolution API admin helpers — per-user WhatsApp instances.

One Evolution server hosts many instances; each instance = one WhatsApp number,
authenticated once by scanning a QR with that phone. A user "sends in their own
name" by routing through their own instance. These helpers manage the lifecycle
(create → connect/QR → state → logout) and the low-level send; the channel layer
(core/channels.py) calls `send_text` with the sender's instance.

Dependency-free (urllib). Every call returns a dict and never raises to the caller:
when Evolution isn't configured it returns {'configured': False}, and on any HTTP
error it returns {'ok': False, 'error': ...}.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

from ..config import settings

log = logging.getLogger("ds.evolution")


def configured() -> bool:
    return bool(settings.EVOLUTION_API_URL and settings.EVOLUTION_API_KEY)


def instance_name_for(username: str) -> str:
    """Deterministic instance name for a user (namespaced, safe chars)."""
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", (username or "").strip()).strip("_").lower()
    return f"ds_{safe or 'user'}"


def _request(method: str, path: str, body: dict | None = None) -> dict:
    if not configured():
        return {"configured": False, "ok": False, "error": "evolution not configured"}
    url = f"{settings.EVOLUTION_API_URL.rstrip('/')}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json", "apikey": settings.EVOLUTION_API_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (configured host)
            raw = resp.read().decode("utf-8") or "{}"
        return {"ok": True, "configured": True, "data": json.loads(raw)}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace") if hasattr(e, "read") else str(e)
        log.warning("[evolution] %s %s -> HTTP %s: %s", method, path, e.code, detail[:200])
        return {"ok": False, "configured": True, "status": e.code, "error": detail[:300]}
    except Exception as e:
        log.error("[evolution] %s %s failed: %s", method, path, e)
        return {"ok": False, "configured": True, "error": str(e)}


def create_instance(instance: str) -> dict:
    """Create an instance (idempotent-ish: a 'already exists' error is tolerated)."""
    return _request(
        "POST", "/instance/create",
        {"instanceName": instance, "integration": "WHATSAPP-BAILEYS", "qrcode": True},
    )


def connect_instance(instance: str) -> dict:
    """Fetch the QR/pairing payload to link the phone. Returns {'qr': base64|None,
    'code': str|None, 'raw': ...}."""
    r = _request("GET", f"/instance/connect/{instance}")
    if not r.get("ok"):
        return r
    d = r.get("data") or {}
    qr = d.get("base64") or (d.get("qrcode") or {}).get("base64")
    code = d.get("code") or d.get("pairingCode") or (d.get("qrcode") or {}).get("code")
    return {"ok": True, "configured": True, "qr": qr, "code": code, "raw": d}


def connection_state(instance: str) -> dict:
    """Returns {'connected': bool, 'state': 'open'|'connecting'|'close'|None}."""
    r = _request("GET", f"/instance/connectionState/{instance}")
    if not r.get("ok"):
        return {**r, "connected": False, "state": None}
    d = r.get("data") or {}
    state = (d.get("instance") or {}).get("state") or d.get("state")
    return {"ok": True, "configured": True, "connected": state == "open", "state": state}


def logout_instance(instance: str) -> dict:
    return _request("DELETE", f"/instance/logout/{instance}")


def send_text(instance: str, number: str, text: str) -> dict:
    """Send a text message through a specific instance (the sender's number)."""
    return _request("POST", f"/message/sendText/{instance}", {"number": number, "text": text})


def instance_profile(instance: str) -> dict:
    """The instance's WhatsApp profile — {profileName, numero} — i.e. how it appears
    to recipients. Empty dict if not found."""
    r = _request("GET", "/instance/fetchInstances")
    if not r.get("ok"):
        return {}
    for i in r.get("data") or []:
        name = i.get("name") or (i.get("instance") or {}).get("instanceName")
        if name == instance:
            jid = i.get("ownerJid") or (i.get("instance") or {}).get("owner") or ""
            return {
                "profileName": i.get("profileName") or (i.get("instance") or {}).get("profileName"),
                "numero": jid.split("@")[0] if jid else None,
            }
    return {}
