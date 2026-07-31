"""Shared-credential in-app login (item 1).

Replaces the nginx HTTP basic-auth popup with a login screen inside the
platform. A single shared credential (APP_USER / APP_PASSWORD) is checked; on
success we set a signed, httpOnly session cookie. Per-user accounts and roles
(Coordenador vs Gestor) are a later step — they need the loja-coordinator login
the DS will provide.

The session token is a stdlib HMAC over the issued-at timestamp: no external
deps, self-contained, verified with a constant-time comparison and a max age.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ..config import settings
from ..core.crypto import hash_password, verify_password
from ..core.mailer import branded_email, send_email

router = APIRouter()

COOKIE_NAME = "ds_session"
MAX_AGE = 7 * 24 * 3600  # 7 days

# Display name per login account (shown in the header pill). Unknown usernames
# fall back to the username itself.
DISPLAY_NAMES = {
    "ds": "DS Crédito",
    "amin": "Amin Martins",
    "bs": "Bruno Sousa",
    "jg": "Jorge Gonçalves",
}


def _db_user(username: str) -> dict | None:
    """Look up an active platform_users row by username. Returns None if the
    table/project isn't reachable or no such active user exists — callers then
    fall back to the env-based shared credentials (`ds`/`amin`)."""
    try:
        from ..db import supabase

        res = (
            supabase()
            .table("platform_users")
            .select("id, username, nome, role, can_newsletter, password_hash, password_salt, is_active, is_superadmin")
            .eq("username", username)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        return (res.data or [None])[0]
    except Exception:
        return None


def _users() -> dict[str, str]:
    """All accepted username→password pairs: the primary shared credential plus
    any extra accounts (e.g. test logins) declared in APP_USERS as JSON."""
    users: dict[str, str] = {}
    if settings.APP_USERS:
        try:
            data = json.loads(settings.APP_USERS)
            if isinstance(data, dict):
                users.update({str(k): str(v) for k, v in data.items() if v})
        except (ValueError, TypeError):
            pass
    if settings.APP_PASSWORD:
        users.setdefault(settings.APP_USER, settings.APP_PASSWORD)
    return users


def _sign(payload: str) -> str:
    sig = hmac.new(settings.APP_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def make_token(username: str) -> str:
    iat = int(time.time())
    payload = f"{iat}.{username}"
    return f"{payload}.{_sign(payload)}"


def token_user(token: str | None) -> str | None:
    """Return the username if the cookie is well-formed, correctly signed and
    unexpired; else None (also when the server has no session secret)."""
    if not token or not settings.APP_SESSION_SECRET:
        return None
    try:
        iat_str, username, sig = token.split(".", 2)
        iat = int(iat_str)
    except (ValueError, AttributeError):
        return None
    if not hmac.compare_digest(sig, _sign(f"{iat}.{username}")):
        return None
    if not (0 <= (int(time.time()) - iat) <= MAX_AGE):
        return None
    return username


def valid_token(token: str | None) -> bool:
    """Fails closed when the server has no session secret or the cookie is
    invalid/expired. Used by the API session gate."""
    return token_user(token) is not None


class LoginIn(BaseModel):
    username: str | None = None
    password: str


@router.post("/login")
def login(body: LoginIn, response: Response):
    if not settings.APP_SESSION_SECRET:
        raise HTTPException(503, "Login não configurado no servidor.")
    uname = (body.username or settings.APP_USER).strip()

    # 1) DB-backed platform users (source of truth). 2) env shared credentials
    # (`ds`/`amin` admin/test logins) as a fallback so nobody is locked out.
    db_row = _db_user(uname)
    if db_row:
        ok = verify_password(body.password or "", db_row.get("password_hash"), db_row.get("password_salt"))
    else:
        users = _users()
        if not users:
            raise HTTPException(503, "Login não configurado no servidor.")
        expected = users.get(uname)
        ok = bool(expected) and hmac.compare_digest(body.password or "", expected)
    if not ok:
        raise HTTPException(401, "Credenciais inválidas.")

    response.set_cookie(
        COOKIE_NAME,
        make_token(uname),
        max_age=MAX_AGE,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    user = token_user(request.cookies.get(COOKIE_NAME))
    if not user:
        return {"authenticated": False}
    # Prefer the DB display name; fall back to the static map, then the username.
    row = _db_user(user)
    nome = (row.get("nome") if row else None) or DISPLAY_NAMES.get(user, user)
    # role drives what the frontend shows (user management UI, loja tab). Env-only
    # admin logins (ds/amin) have no DB row → treated as diretor_loja (loja-wide).
    role = (row.get("role") if row else None) or "diretor_loja"
    # Newsletter authoring is a per-user grant. Env-only admin logins (ds/amin,
    # no DB row) keep access so nobody is locked out during a demo.
    can_newsletter = bool(row.get("can_newsletter")) if row else True
    # RBAC: capabilities + CRM data scope come from the user's profile (ds.perfis).
    # Lazy import — core.scope imports from this module.
    from ..core.scope import user_capabilities, acting_data_scope

    return {
        "authenticated": True,
        "username": user,
        "nome": nome,
        "role": role,
        "user_id": (row.get("id") if row else None),
        "can_newsletter": can_newsletter,
        # Sentinela GlobalWatch (migração 027): ortogonal ao perfil, por isso vai
        # à parte das capabilities. A UI usa-o para deixar editar o catálogo de lojas.
        "is_superadmin": bool(row.get("is_superadmin")) if row else False,
        "capabilities": sorted(user_capabilities(request)),
        "data_scope": acting_data_scope(request),
    }


# ---- Password recovery ---------------------------------------------------
RESET_TTL = timedelta(hours=1)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _find_user_by_login(sb, login: str) -> dict | None:
    """Match by username first, then email. Separate queries (not PostgREST or_)
    to avoid filter-injection from raw user input."""
    for col in ("username", "email"):
        r = (
            sb.table("platform_users")
            .select("id, username, nome, email")
            .eq(col, login)
            .eq("is_active", True)
            .limit(1)
            .execute()
            .data
        )
        if r:
            return r[0]
    return None


class ForgotIn(BaseModel):
    login: str  # username or email


@router.post("/forgot")
def forgot(body: ForgotIn):
    """Start a password reset. Always returns 200 (no account enumeration). If email
    is unconfigured, non-production surfaces a dev link so the flow is testable."""
    from ..db import supabase

    login = (body.login or "").strip()
    resp: dict = {"ok": True}
    if not login:
        return resp
    try:
        sb = supabase()
        user = _find_user_by_login(sb, login)
        if user:
            raw = secrets.token_urlsafe(32)
            expires = datetime.now(timezone.utc) + RESET_TTL
            sb.table("password_resets").insert(
                {"user_id": user["id"], "token_hash": _hash_token(raw), "expires_at": expires.isoformat()}
            ).execute()
            link = f"{settings.APP_BASE_URL}/reset?token={raw}"
            html = branded_email(
                "Recuperação de palavra-passe",
                (
                    f"Olá {user.get('nome') or user['username']},<br><br>"
                    "Recebemos um pedido para repor a palavra-passe da sua conta. "
                    "Clique no botão abaixo para definir uma nova — o link é válido por 1 hora.<br><br>"
                    "Se não foi você, ignore este email."
                ),
                cta_label="Repor palavra-passe",
                cta_url=link,
            )
            result = send_email(
                user.get("email"),
                "Recuperação de palavra-passe — DS Crédito",
                html,
                text_body=f"Reponha a sua palavra-passe: {link}",
            )
            if not result.get("delivered") and settings.ENVIRONMENT != "production":
                resp["dev_link"] = link
    except Exception:
        pass  # never leak internal errors on this endpoint
    return resp


def _valid_reset(sb, raw: str) -> dict | None:
    row = (
        sb.table("password_resets")
        .select("id, user_id, expires_at, used_at")
        .eq("token_hash", _hash_token(raw))
        .limit(1)
        .execute()
        .data
        or [None]
    )[0]
    if not row or row.get("used_at"):
        return None
    try:
        exp = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
    except ValueError:
        return None
    if exp < datetime.now(timezone.utc):
        return None
    return row


@router.get("/reset/validate")
def reset_validate(token: str):
    from ..db import supabase

    try:
        return {"valid": bool(_valid_reset(supabase(), token))}
    except Exception:
        return {"valid": False}


class ResetIn(BaseModel):
    token: str
    password: str


@router.post("/reset")
def reset(body: ResetIn):
    from ..db import supabase

    if len(body.password or "") < 8:
        raise HTTPException(400, "A palavra-passe deve ter pelo menos 8 caracteres.")
    sb = supabase()
    row = _valid_reset(sb, body.token)
    if not row:
        raise HTTPException(400, "Link inválido ou expirado. Peça um novo.")
    h, salt = hash_password(body.password)
    now = datetime.now(timezone.utc).isoformat()
    sb.table("platform_users").update(
        {"password_hash": h, "password_salt": salt, "updated_at": now}
    ).eq("id", row["user_id"]).execute()
    sb.table("password_resets").update({"used_at": now}).eq("id", row["id"]).execute()
    return {"ok": True}
