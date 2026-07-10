"""Perfis — editable RBAC profiles (capabilities + data scope).

Gated behind the `profiles.manage` capability (Administrador and Diretor de Loja by
default). System profiles (is_system) may be edited but not deleted, and their
`chave` is immutable (platform_users.role references it). Every write clears the
in-process profile cache in core.scope.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..core.capabilities import catalog, valid_caps
from ..core.scope import invalidate_perfil_cache, require_cap
from ..db import supabase

router = APIRouter()

VALID_SCOPES = {"loja", "equipa", "propria", "nenhuma"}


def _slugify(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s or "perfil"


@router.get("/catalog")
def get_catalog(request: Request):
    """Capability catalog + valid data scopes, for the profile editor UI."""
    require_cap(request, "profiles.manage")
    return {
        "capabilities": catalog(),
        "data_scopes": [
            {"key": "loja", "rotulo": "Loja toda"},
            {"key": "equipa", "rotulo": "Equipa (própria + equipa)"},
            {"key": "propria", "rotulo": "Apenas a própria carteira"},
            {"key": "nenhuma", "rotulo": "Sem acesso a dados CRM"},
        ],
    }


@router.get("")
@router.get("/")
def list_perfis(request: Request):
    require_cap(request, "profiles.manage")
    rows = (
        supabase()
        .table("perfis")
        .select("id, chave, nome, is_system, data_scope, permissoes")
        .order("id")
        .execute()
        .data
        or []
    )
    return {"perfis": rows}


@router.get("/{perfil_id}")
def get_perfil(perfil_id: int, request: Request):
    require_cap(request, "profiles.manage")
    row = (
        supabase()
        .table("perfis")
        .select("id, chave, nome, is_system, data_scope, permissoes")
        .eq("id", perfil_id)
        .limit(1)
        .execute()
        .data
        or [None]
    )[0]
    if not row:
        raise HTTPException(404, "Perfil não encontrado.")
    return row


class PerfilIn(BaseModel):
    nome: str | None = None
    data_scope: str | None = None
    permissoes: list[str] | None = None


@router.post("")
@router.post("/")
def create_perfil(body: PerfilIn, request: Request):
    require_cap(request, "profiles.manage")
    sb = supabase()
    nome = (body.nome or "").strip()
    if not nome:
        raise HTTPException(400, "O nome do perfil é obrigatório.")
    scope = body.data_scope or "propria"
    if scope not in VALID_SCOPES:
        raise HTTPException(400, "Âmbito de dados inválido.")

    # Unique chave derived from the name (custom profiles are never is_system).
    base = _slugify(nome)
    chave = base
    n = 2
    existing = {r["chave"] for r in sb.table("perfis").select("chave").execute().data or []}
    while chave in existing:
        chave = f"{base}_{n}"
        n += 1

    row = {
        "chave": chave,
        "nome": nome,
        "is_system": False,
        "data_scope": scope,
        "permissoes": valid_caps(body.permissoes),
    }
    res = sb.table("perfis").insert(row).execute().data
    invalidate_perfil_cache()
    return {"ok": True, "id": (res or [{}])[0].get("id"), "chave": chave}


@router.put("/{perfil_id}")
def update_perfil(perfil_id: int, body: PerfilIn, request: Request):
    require_cap(request, "profiles.manage")
    sb = supabase()
    target = (
        sb.table("perfis").select("id, chave, is_system").eq("id", perfil_id).limit(1).execute().data
        or [None]
    )[0]
    if not target:
        raise HTTPException(404, "Perfil não encontrado.")

    patch: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if body.nome is not None:
        nome = body.nome.strip()
        if not nome:
            raise HTTPException(400, "O nome do perfil não pode ficar vazio.")
        patch["nome"] = nome
    if body.data_scope is not None:
        if body.data_scope not in VALID_SCOPES:
            raise HTTPException(400, "Âmbito de dados inválido.")
        patch["data_scope"] = body.data_scope
    if body.permissoes is not None:
        patch["permissoes"] = valid_caps(body.permissoes)

    sb.table("perfis").update(patch).eq("id", perfil_id).execute()
    invalidate_perfil_cache()
    return {"ok": True}


@router.delete("/{perfil_id}")
def delete_perfil(perfil_id: int, request: Request):
    require_cap(request, "profiles.manage")
    sb = supabase()
    target = (
        sb.table("perfis").select("id, chave, is_system").eq("id", perfil_id).limit(1).execute().data
        or [None]
    )[0]
    if not target:
        raise HTTPException(404, "Perfil não encontrado.")
    if target["is_system"]:
        raise HTTPException(403, "Os perfis de sistema não podem ser apagados.")
    in_use = (
        sb.table("platform_users").select("id").eq("role", target["chave"]).limit(1).execute().data
    )
    if in_use:
        raise HTTPException(409, "Há utilizadores com este perfil. Reatribua-os antes de apagar.")
    sb.table("perfis").delete().eq("id", perfil_id).execute()
    invalidate_perfil_cache()
    return {"ok": True}
