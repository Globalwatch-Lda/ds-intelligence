"""Equipas — named teams (org structure).

A team has a name and a leader (a Diretor Comercial). Consultores join a team via
platform_users.equipa_id; the API keeps platform_users.manager_id in sync with the
team's leader so the existing user-management/permission logic keeps working.

Gated behind `teams.manage`:
  * loja-level (Administrador or teams.manage + loja scope) → all teams; create,
    delete, set leader.
  * team-level (e.g. Diretor Comercial) → only the team(s) they lead: rename +
    add/remove members.
Team membership/name is org structure and is independent of CRM data visibility.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..core.scope import acting_data_scope, has_cap, require_cap
from ..db import supabase
from .settings import _acting_user

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loja_team_admin(request: Request, acting: dict) -> bool:
    if acting["role"] == "administrador":
        return True
    return has_cap(request, "teams.manage") and acting_data_scope(request) == "loja"


def _team_or_404(sb, team_id: int) -> dict:
    row = (
        sb.table("equipas").select("id, nome, lider_id").eq("id", team_id).limit(1).execute().data
        or [None]
    )[0]
    if not row:
        raise HTTPException(404, "Equipa não encontrada.")
    return row


def _can_edit_team(request: Request, acting: dict, team: dict) -> bool:
    return _loja_team_admin(request, acting) or team.get("lider_id") == acting["id"]


@router.get("")
@router.get("/")
def list_equipas(request: Request):
    require_cap(request, "teams.manage")
    acting = _acting_user(request)
    sb = supabase()
    loja_admin = _loja_team_admin(request, acting)

    teams = sb.table("equipas").select("id, nome, lider_id").order("nome").execute().data or []
    if not loja_admin:
        teams = [t for t in teams if t.get("lider_id") == acting["id"]]

    users = (
        sb.table("platform_users")
        .select("id, username, nome, role, equipa_id")
        .eq("is_active", True)
        .order("nome")
        .execute()
        .data
        or []
    )
    by_id = {u["id"]: u for u in users}
    members: dict[int, list] = {}
    for u in users:
        eid = u.get("equipa_id")
        if eid:
            members.setdefault(eid, []).append(
                {"id": u["id"], "nome": u.get("nome"), "username": u.get("username"), "role": u.get("role")}
            )

    equipas = [
        {
            **t,
            "lider_nome": (by_id.get(t.get("lider_id")) or {}).get("nome"),
            "membros": members.get(t["id"], []),
        }
        for t in teams
    ]
    return {
        "equipas": equipas,
        "loja_admin": loja_admin,
        "acting": {"id": acting["id"]},
        # Candidate leaders (Diretores Comerciais) and the consultor pool, for the UI.
        "liders": [
            {"id": u["id"], "nome": u.get("nome"), "username": u.get("username")}
            for u in users
            if u.get("role") == "diretor_comercial"
        ],
        "consultores": [
            {"id": u["id"], "nome": u.get("nome"), "username": u.get("username"), "equipa_id": u.get("equipa_id")}
            for u in users
            if u.get("role") == "consultor"
        ],
    }


class EquipaIn(BaseModel):
    nome: str | None = None
    lider_id: int | None = None


@router.post("")
@router.post("/")
def create_equipa(body: EquipaIn, request: Request):
    require_cap(request, "teams.manage")
    acting = _acting_user(request)
    if not _loja_team_admin(request, acting):
        raise HTTPException(403, "Só um gestor de loja pode criar equipas.")
    nome = (body.nome or "").strip()
    if not nome:
        raise HTTPException(400, "O nome da equipa é obrigatório.")
    sb = supabase()
    res = sb.table("equipas").insert({"nome": nome, "lider_id": body.lider_id}).execute().data
    return {"ok": True, "id": (res or [{}])[0].get("id")}


@router.put("/{team_id}")
def update_equipa(team_id: int, body: EquipaIn, request: Request):
    require_cap(request, "teams.manage")
    acting = _acting_user(request)
    sb = supabase()
    team = _team_or_404(sb, team_id)
    if not _can_edit_team(request, acting, team):
        raise HTTPException(403, "Sem permissão para alterar esta equipa.")

    patch: dict = {"updated_at": _now()}
    if body.nome is not None:
        nome = body.nome.strip()
        if not nome:
            raise HTTPException(400, "O nome da equipa não pode ficar vazio.")
        patch["nome"] = nome
    # Only a loja-level admin may reassign the leader.
    if body.lider_id is not None and _loja_team_admin(request, acting):
        patch["lider_id"] = body.lider_id or None
        # Keep members' manager_id mirroring the new leader.
        sb.table("platform_users").update({"manager_id": body.lider_id or None}).eq("equipa_id", team_id).execute()

    sb.table("equipas").update(patch).eq("id", team_id).execute()
    return {"ok": True}


@router.delete("/{team_id}")
def delete_equipa(team_id: int, request: Request):
    require_cap(request, "teams.manage")
    acting = _acting_user(request)
    if not _loja_team_admin(request, acting):
        raise HTTPException(403, "Só um gestor de loja pode apagar equipas.")
    sb = supabase()
    _team_or_404(sb, team_id)
    # Detach members before deleting the team.
    sb.table("platform_users").update({"equipa_id": None, "manager_id": None}).eq("equipa_id", team_id).execute()
    sb.table("equipas").delete().eq("id", team_id).execute()
    return {"ok": True}


class MembroIn(BaseModel):
    user_id: int


@router.post("/{team_id}/membros")
def add_membro(team_id: int, body: MembroIn, request: Request):
    require_cap(request, "teams.manage")
    acting = _acting_user(request)
    sb = supabase()
    team = _team_or_404(sb, team_id)
    if not _can_edit_team(request, acting, team):
        raise HTTPException(403, "Sem permissão para alterar esta equipa.")
    sb.table("platform_users").update(
        {"equipa_id": team_id, "manager_id": team.get("lider_id")}
    ).eq("id", body.user_id).execute()
    return {"ok": True}


@router.delete("/{team_id}/membros/{user_id}")
def remove_membro(team_id: int, user_id: int, request: Request):
    require_cap(request, "teams.manage")
    acting = _acting_user(request)
    sb = supabase()
    team = _team_or_404(sb, team_id)
    if not _can_edit_team(request, acting, team):
        raise HTTPException(403, "Sem permissão para alterar esta equipa.")
    sb.table("platform_users").update({"equipa_id": None, "manager_id": None}).eq("id", user_id).eq(
        "equipa_id", team_id
    ).execute()
    return {"ok": True}
