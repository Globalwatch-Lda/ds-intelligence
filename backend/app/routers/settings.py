"""Settings — user management (CRUD) by profile + loja config.

Profiles (platform_users.role):
  diretor_loja      — manages any diretor_comercial / comercial in the loja; sees
                      the whole loja's data.
  diretor_comercial — manages only their own team (comerciais with manager_id ==
                      them); sees own + team (their CRM account's view).
  comercial         — no user management; sees only their own processos.

The old service-PIN model is gone: access is governed entirely by the acting
user's profile. All routes sit behind the global session gate (main.py).
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..core.crypto import encrypt_secret, hash_password
from ..core.names import fix_name
from ..core.scope import acting_data_scope, apply_scope, has_cap, require_cap, user_scope
from ..db import supabase
from .auth import COOKIE_NAME, token_user

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid_roles(sb) -> set[str]:
    """The set of assignable profile keys (ds.perfis.chave)."""
    return {r["chave"] for r in sb.table("perfis").select("chave").execute().data or []}


def _equipa_lider(sb, equipa_id: int | None) -> int | None:
    """The platform_users.id of a team's leader (for keeping manager_id in sync)."""
    if not equipa_id:
        return None
    r = sb.table("equipas").select("lider_id").eq("id", equipa_id).limit(1).execute().data
    return (r or [{}])[0].get("lider_id")


def _acting_led_team(sb, acting: dict) -> int | None:
    """The single team the acting user leads, if exactly one (used to auto-assign a
    consultor created by a team-level manager)."""
    if not acting.get("id"):
        return None
    rows = sb.table("equipas").select("id").eq("lider_id", acting["id"]).execute().data or []
    return rows[0]["id"] if len(rows) == 1 else None


# ---- acting user + permissions ------------------------------------------
def _acting_user(request: Request) -> dict:
    """The logged-in user as {id, username, role, manager_id}. Env-only admin
    logins (ds/amin, no platform_users row) act as an administrator."""
    username = token_user(request.cookies.get(COOKIE_NAME))
    row = None
    if username:
        try:
            row = (
                supabase()
                .table("platform_users")
                .select("id, username, role, manager_id, is_active")
                .eq("username", username)
                .eq("is_active", True)
                .limit(1)
                .execute()
                .data
                or [None]
            )[0]
        except Exception:
            row = None
    if not row:
        return {"id": None, "username": username, "role": "administrador", "manager_id": None}
    return row


def _is_loja_manager(request: Request, acting: dict) -> bool:
    """A loja-wide manager: can manage every user in the loja. True for an
    Administrador, or anyone whose profile has `users.manage` + loja data scope."""
    if acting["role"] == "administrador":
        return True
    return has_cap(request, "users.manage") and acting_data_scope(request) == "loja"


def _can_manage(request: Request, acting: dict, target: dict) -> bool:
    """Whether `acting` may view/edit `target`."""
    if not has_cap(request, "users.manage"):
        return False
    if acting["role"] == "administrador":
        return True
    # Only an Administrador may touch another Administrador account.
    if target.get("role") == "administrador":
        return False
    if _is_loja_manager(request, acting):
        return True
    # Team-level manager (e.g. Diretor Comercial): only their own team.
    return target.get("manager_id") == acting["id"]


def _can_assign_role(request: Request, acting: dict, role: str) -> bool:
    """Whether `acting` may create a user with / assign the profile `role`."""
    if not has_cap(request, "users.manage"):
        return False
    if role == "administrador":
        return acting["role"] == "administrador"
    if _is_loja_manager(request, acting):
        return True
    # Team-level managers can only ever create/assign Consultores.
    return role == "consultor"


def _get_user_or_404(sb, user_id: int, columns: str) -> dict:
    res = sb.table("platform_users").select(columns).eq("id", user_id).limit(1).execute()
    row = (res.data or [None])[0]
    if not row:
        raise HTTPException(404, "Utilizador não encontrado.")
    return row


def _username_taken(sb, username: str, exclude_id: int | None = None) -> bool:
    q = sb.table("platform_users").select("id").eq("username", username)
    if exclude_id is not None:
        q = q.neq("id", exclude_id)
    return bool(q.limit(1).execute().data)


# ---- list / read ---------------------------------------------------------
@router.get("/users")
def list_users(request: Request):
    """Users the acting profile may see: loja-manager → all; team-manager →
    self + team; otherwise → self."""
    acting = _acting_user(request)
    sb = supabase()
    loja_manager = _is_loja_manager(request, acting)
    can_manage = has_cap(request, "users.manage")
    q = sb.table("platform_users").select("id, username, nome, role, manager_id, equipa_id, is_active").order("id")
    if loja_manager:
        pass  # all users in the loja
    elif can_manage:
        q = q.or_(f"id.eq.{acting['id']},manager_id.eq.{acting['id']}")
    else:
        q = q.eq("id", acting["id"])
    return {
        "users": q.execute().data or [],
        "acting": {"id": acting["id"], "role": acting["role"], "loja_manager": loja_manager, "can_manage": can_manage},
    }


def _shape_user(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "username": row.get("username"),
        "nome": row.get("nome"),
        "telefone": row.get("telefone"),
        "email": row.get("email"),
        "role": row.get("role"),
        "manager_id": row.get("manager_id"),
        "equipa_id": row.get("equipa_id"),
        "manager_crm_id": row.get("manager_crm_id"),
        "crm_username": row.get("crm_username"),
        "crm_password_set": bool(row.get("crm_password_enc")),
        "can_newsletter": bool(row.get("can_newsletter")),
    }


@router.get("/users/{user_id}")
def get_user(user_id: int, request: Request):
    acting = _acting_user(request)
    sb = supabase()
    target = _get_user_or_404(
        sb, user_id,
        "id, username, nome, telefone, email, role, manager_id, equipa_id, manager_crm_id, crm_username, crm_password_enc, can_newsletter",
    )
    if not (acting["id"] == target["id"] or _can_manage(request, acting, target)):
        raise HTTPException(403, "Sem permissão para ver este utilizador.")
    return _shape_user(target)


# ---- create / update / delete -------------------------------------------
class UserIn(BaseModel):
    username: str | None = None
    password: str | None = None
    nome: str | None = None
    telefone: str | None = None
    email: str | None = None
    role: str | None = None
    manager_id: int | None = None
    equipa_id: int | None = None
    manager_crm_id: int | None = None
    crm_username: str | None = None
    crm_password: str | None = None
    can_newsletter: bool | None = None


@router.post("/users")
def create_user(body: UserIn, request: Request):
    acting = _acting_user(request)
    sb = supabase()
    role = body.role or "consultor"
    manager_id = body.manager_id
    equipa_id = body.equipa_id
    # A team-level manager (e.g. Diretor Comercial) can only spawn Consultores on
    # their own team; loja-level managers assign freely.
    if not _is_loja_manager(request, acting):
        role = "consultor"
        equipa_id = _acting_led_team(sb, acting)
        manager_id = acting["id"]
    # equipa_id is the source of truth for team membership; manager_id mirrors the
    # team's leader so the existing management/permission logic keeps working.
    if equipa_id:
        manager_id = _equipa_lider(sb, equipa_id)
    if role not in _valid_roles(sb) or not _can_assign_role(request, acting, role):
        raise HTTPException(403, "Sem permissão para criar este perfil.")
    username = (body.username or "").strip()
    if not username or not body.password:
        raise HTTPException(400, "Utilizador e palavra-passe são obrigatórios.")
    if _username_taken(sb, username):
        raise HTTPException(409, "Esse nome de utilizador já existe.")
    h, salt = hash_password(body.password)
    row: dict = {
        "username": username,
        "nome": body.nome,
        "telefone": body.telefone,
        "email": body.email,
        "role": role,
        "manager_id": manager_id,
        "equipa_id": equipa_id,
        "manager_crm_id": body.manager_crm_id,
        "password_hash": h,
        "password_salt": salt,
        "crm_username": body.crm_username,
        "is_active": True,
        # Newsletter authoring is a loja-manager grant only.
        "can_newsletter": bool(body.can_newsletter) if _is_loja_manager(request, acting) else False,
    }
    if body.crm_password:
        row["crm_password_enc"] = encrypt_secret(body.crm_password)
    res = sb.table("platform_users").insert(row).execute()
    return {"ok": True, "id": (res.data or [{}])[0].get("id")}


@router.put("/users/{user_id}")
def update_user(user_id: int, body: UserIn, request: Request):
    acting = _acting_user(request)
    sb = supabase()
    target = _get_user_or_404(sb, user_id, "id, role, manager_id")
    is_self = acting["id"] == target["id"]
    can_manage = _can_manage(request, acting, target)
    if not (is_self or can_manage):
        raise HTTPException(403, "Sem permissão para alterar este utilizador.")

    patch: dict = {"updated_at": _now()}
    for field in ("nome", "telefone", "email"):
        val = getattr(body, field)
        if val is not None:
            patch[field] = val
    if body.username:
        new_username = body.username.strip()
        if new_username and _username_taken(sb, new_username, exclude_id=user_id):
            raise HTTPException(409, "Esse nome de utilizador já existe.")
        if new_username:
            patch["username"] = new_username
    if body.password:
        h, salt = hash_password(body.password)
        patch["password_hash"] = h
        patch["password_salt"] = salt
    # CRM creds — self or a manager.
    if body.crm_username is not None:
        patch["crm_username"] = body.crm_username
    if body.crm_password:
        patch["crm_password_enc"] = encrypt_secret(body.crm_password)
    # Newsletter-authoring grant: only a loja-manager may toggle it, on any user —
    # it's a per-user permission, not structure.
    if body.can_newsletter is not None and _is_loja_manager(request, acting):
        patch["can_newsletter"] = bool(body.can_newsletter)
    # Structural fields (role / team / CRM identity) only when managing the target
    # and never on an Administrador account (protects the super-admin from being
    # restructured by a loja-level manager).
    if can_manage and target.get("role") != "administrador":
        if body.role and body.role != target.get("role"):
            if body.role not in _valid_roles(sb) or not _can_assign_role(request, acting, body.role):
                raise HTTPException(403, "Sem permissão para atribuir esse perfil.")
            patch["role"] = body.role
        if body.equipa_id is not None:
            # 0 / null clears the team; otherwise join it and mirror the leader.
            equipa_id = body.equipa_id or None
            patch["equipa_id"] = equipa_id
            patch["manager_id"] = _equipa_lider(sb, equipa_id) if equipa_id else None
        elif body.manager_id is not None:
            patch["manager_id"] = body.manager_id
        if body.manager_crm_id is not None:
            patch["manager_crm_id"] = body.manager_crm_id

    sb.table("platform_users").update(patch).eq("id", user_id).execute()
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, request: Request):
    acting = _acting_user(request)
    sb = supabase()
    target = _get_user_or_404(sb, user_id, "id, role, manager_id")
    if acting["id"] == target["id"]:
        raise HTTPException(400, "Não pode apagar a própria conta.")
    if target.get("role") == "administrador" and acting["role"] != "administrador":
        raise HTTPException(403, "Não é possível apagar um Administrador.")
    if not _can_manage(request, acting, target):
        raise HTTPException(403, "Sem permissão para apagar este utilizador.")
    # Orphan any reports (e.g. deleting a diretor_comercial): null their team link.
    sb.table("platform_users").update({"manager_id": None}).eq("manager_id", user_id).execute()
    sb.table("platform_users").delete().eq("id", user_id).execute()
    return {"ok": True}


# ---- assignable profiles (for the role dropdown in the user form) ---------
@router.get("/roles")
def list_assignable_roles(request: Request):
    """All profiles (for display labels) tagged with whether the acting user may
    assign each one — drives the role dropdown without needing `profiles.manage`."""
    acting = _acting_user(request)
    sb = supabase()
    rows = sb.table("perfis").select("chave, nome").order("id").execute().data or []
    return {"roles": [{**r, "assignable": _can_assign_role(request, acting, r["chave"])} for r in rows]}


# ---- managers dropdown (for mapping a comercial to a CRM gestor) ----------
@router.get("/managers")
def list_managers(request: Request):
    """Distinct CRM gestores visible to the acting user — for the manager_crm_id
    dropdown when creating/editing a comercial."""
    sb = supabase()
    q = apply_scope(sb.table("processos_real").select("manager_crm_id, manager_name"), user_scope(request))
    rows = q.execute().data or []
    seen: dict[int, str | None] = {}
    for r in rows:
        mid = r.get("manager_crm_id")
        if mid is None:
            continue
        seen.setdefault(mid, fix_name(r.get("manager_name")))
    managers = sorted(
        ({"crm_id": mid, "nome": nome} for mid, nome in seen.items()),
        key=lambda m: (m["nome"] or ""),
    )
    return {"managers": managers}


# ---- loja config ---------------------------------------------------------
@router.get("/loja")
def get_loja():
    sb = supabase()
    row = (sb.table("loja_config").select("numero, nome").eq("id", 1).limit(1).execute().data or [{}])[0]
    return {"numero": row.get("numero"), "nome": row.get("nome")}


class LojaIn(BaseModel):
    numero: str | None = None
    nome: str | None = None


@router.put("/loja")
def put_loja(body: LojaIn, request: Request):
    require_cap(request, "loja.edit")
    sb = supabase()
    sb.table("loja_config").update(
        {"numero": body.numero, "nome": body.nome, "updated_at": _now()}
    ).eq("id", 1).execute()
    return {"ok": True}


# ---- CRM sync (re-ingest, so a new diretor_comercial's team gets tagged) ----
_SYNC_SOURCES = ["credidesk_processos", "credidesk_leads"]


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[2]  # app/routers/settings.py -> backend/


@router.post("/sync")
def sync_crm(request: Request):
    """Requires the `crm.sync` capability. Spawns a DETACHED re-ingest of
    processos+leads over all CRM accounts (so a newly-added diretor_comercial's rows
    get tagged with their username). Runs out-of-process — the single uvicorn worker
    is never blocked."""
    require_cap(request, "crm.sync")
    sb = supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    running = (
        sb.table("crm_sync_runs").select("id")
        .in_("source", _SYNC_SOURCES).is_("finished_at", "null").gte("started_at", cutoff)
        .limit(1).execute().data
    )
    if running:
        raise HTTPException(409, "Já existe uma sincronização em curso.")

    backend = _backend_dir()
    py = sys.executable
    # `;` (not `&&`) so leads still runs even if processos errors on one account.
    cmd = (
        f'"{py}" integrations/ds_crm/ingest_processos.py ; '
        f'"{py}" integrations/ds_crm/ingest_leads.py'
    )
    try:
        logf = open(backend.parent / "ds-sync.log", "a")  # ~/ds-engine/ds-sync.log
    except OSError:
        logf = subprocess.DEVNULL
    subprocess.Popen(cmd, shell=True, cwd=str(backend), stdout=logf, stderr=logf, start_new_session=True)
    return {"started": True}


@router.get("/sync/status")
def sync_status():
    """Last processos/leads ingest runs (for the sync button to poll)."""
    sb = supabase()

    def _last(source: str) -> dict | None:
        r = (
            sb.table("crm_sync_runs")
            .select("source, started_at, finished_at, rows_upserted, error")
            .eq("source", source).order("started_at", desc=True).limit(1).execute().data
        )
        return r[0] if r else None

    proc, leads = _last("credidesk_processos"), _last("credidesk_leads")
    running = bool((proc and not proc.get("finished_at")) or (leads and not leads.get("finished_at")))
    return {"processos": proc, "leads": leads, "running": running}
