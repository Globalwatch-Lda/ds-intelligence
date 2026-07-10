"""Data-driven RBAC: per-profile capabilities + CRM read-scoping.

Each platform user's `role` is the `chave` of a row in ds.perfis. A profile carries
a set of capability keys (`permissoes`, catalog in core/capabilities.py) and a
`data_scope` that governs which CRM rows the user may read:
  * loja     → the whole loja (no filter)
  * equipa   → own + team = what their CRM account ingests (source_accounts @> {username})
  * propria  → only their own (manager_crm_id == theirs)
  * nenhuma  → nothing (-1 sentinel)

Env-only admin logins (ds/amin, no platform_users row) are treated as full admins
(all capabilities, loja-wide) so nobody is locked out.

Public API:
  user_capabilities(request) / has_cap / require_cap  — feature access
  user_scope(request) / apply_scope(query, scope) / scope_label(request)  — data access
  acting_data_scope(request)  — the raw scope string (for management-breadth checks)
  invalidate_perfil_cache()   — call after editing ds.perfis
"""
from __future__ import annotations

from fastapi import HTTPException, Request

from ..routers.auth import COOKIE_NAME, token_user
from .capabilities import ALL_CAPABILITIES


def current_username(request: Request) -> str | None:
    return token_user(request.cookies.get(COOKIE_NAME))


def _user_row(username: str) -> dict | None:
    try:
        from ..db import supabase

        return (
            supabase()
            .table("platform_users")
            .select("id, username, nome, role, manager_id, manager_crm_id, is_active")
            .eq("username", username)
            .eq("is_active", True)
            .limit(1)
            .execute()
            .data
            or [None]
        )[0]
    except Exception:
        return None


# Process-local cache of profiles (chave -> row). Cleared on edit via the perfis
# router (single uvicorn worker, so a plain dict is enough).
_perfil_cache: dict[str, dict] = {}


def invalidate_perfil_cache() -> None:
    _perfil_cache.clear()


def _load_perfil(chave: str | None) -> dict | None:
    if not chave:
        return None
    if chave in _perfil_cache:
        return _perfil_cache[chave]
    try:
        from ..db import supabase

        row = (
            supabase()
            .table("perfis")
            .select("chave, nome, data_scope, permissoes")
            .eq("chave", chave)
            .limit(1)
            .execute()
            .data
            or [None]
        )[0]
    except Exception:
        row = None
    if row:
        _perfil_cache[chave] = row
    return row


def _acting(request: Request) -> tuple[dict | None, dict | None]:
    """(platform_users row, perfis row). Both None for an env-only admin login
    (ds/amin, no DB row) or an unauthenticated request — callers treat env-admins
    as full admins based on current_username()."""
    username = current_username(request)
    if not username:
        return None, None
    urow = _user_row(username)
    if not urow:
        return None, None
    return urow, _load_perfil(urow.get("role"))


# ---- capabilities (feature access) --------------------------------------
def user_capabilities(request: Request) -> set[str]:
    urow, perfil = _acting(request)
    if urow is None:
        # env-only admin login → all capabilities; no session → none.
        return set(ALL_CAPABILITIES) if current_username(request) else set()
    if not perfil:
        return set()
    return {c for c in (perfil.get("permissoes") or []) if c in ALL_CAPABILITIES}


def has_cap(request: Request, cap: str) -> bool:
    return cap in user_capabilities(request)


def require_cap(request: Request, cap: str) -> None:
    if not has_cap(request, cap):
        raise HTTPException(403, "Sem permissão para esta ação.")


# ---- data scope (CRM read visibility) -----------------------------------
def acting_data_scope(request: Request) -> str:
    urow, perfil = _acting(request)
    if urow is None:
        return "loja"  # env admin
    return (perfil or {}).get("data_scope") or "propria"


def user_scope(request: Request) -> dict | None:
    """None = loja-wide; else {'kind': 'source_account'|'manager_crm_id', 'value': ...}."""
    urow, perfil = _acting(request)
    if urow is None:
        return None  # env admin → loja-wide
    scope = (perfil or {}).get("data_scope") or "propria"
    if scope == "loja":
        return None
    if scope == "nenhuma":
        return {"kind": "manager_crm_id", "value": -1}
    if scope == "equipa":
        return {"kind": "source_account", "value": urow["username"]}
    # propria → own processos only; unmapped (no manager_crm_id) sees nothing (-1)
    mid = urow.get("manager_crm_id")
    return {"kind": "manager_crm_id", "value": mid if mid is not None else -1}


def scope_label(request: Request) -> str:
    """Human label (pt) of the logged-in user's CRM data scope."""
    urow, perfil = _acting(request)
    if urow is None:
        return "Loja toda"
    scope = (perfil or {}).get("data_scope") or "propria"
    nome = urow.get("nome") or urow.get("username")
    if scope == "loja":
        return "Loja toda"
    if scope == "equipa":
        return f"Equipa de {nome}"
    if scope == "nenhuma":
        return "Sem acesso a dados"
    return f"Carteira de {nome}"


def apply_scope(query, scope: dict | None):
    """Apply a user_scope descriptor to a Supabase query builder."""
    if scope is None:
        return query
    if scope["kind"] == "source_account":
        return query.contains("source_accounts", [scope["value"]])
    if scope["kind"] == "manager_crm_id":
        return query.eq("manager_crm_id", scope["value"])
    return query
