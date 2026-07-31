"""Wire do módulo empacotado `synertia-multicanal` no dscredito.

Constrói o `MulticanalCtx` que o pacote precisa a partir das peças do host: o
cliente Supabase (schema `ds`), as credenciais do env, o RBAC (`require_cap`), a
auth por cookie, e os hooks específicos do DS — instância WhatsApp por-utilizador
(em `platform_users`) e pesquisa de clientes do CRM (`clientes_real`).

O módulo é um checkout git à parte (github.com/Globalwatch-Lda/synertia-multicanal),
clonado em `backend/multicanal/` — o mesmo modelo do synertia-correio no bot. Não é
vendorizado no repo do dscredito (está no .gitignore); o deploy faz git clone/pull.
Aqui pomo-lo no sys.path.
"""
from __future__ import annotations

import os
import sys

from fastapi import Request

# backend/multicanal (checkout do módulo) no sys.path — um nível acima de app/.
_MODULE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "multicanal")
if _MODULE not in sys.path:
    sys.path.insert(0, _MODULE)

from synertia_multicanal import MulticanalCtx, MulticanalSettings  # noqa: E402

from .config import settings as _cfg  # noqa: E402
from .core.scope import require_cap  # noqa: E402
from .db import supabase  # noqa: E402
from .routers.auth import COOKIE_NAME, token_user  # noqa: E402


def _prefixo_instancias() -> str:
    """Namespace das instâncias WhatsApp desta loja: `ds<numero da loja>_`.

    O número vem do `loja_config` (Configurações → Loja), não de uma variável que
    alguém tem de se lembrar de pôr no .env. Era esse o risco: o prefixo é a ÚNICA
    coisa que separa as instâncias de duas lojas no servidor Evolution partilhado,
    e um .env esquecido fazia a loja nova aterrar nas instâncias da Ramada — o
    utilizador `ds` das duas resolvia para a mesma sessão de WhatsApp.

    Devolve "" se o número não estiver definido: o canal fica inerte com erro
    explícito, que é infinitamente melhor do que enviar pelo número de outra loja.
    O env EVOLUTION_INSTANCE_PREFIX ainda ganha, para uma loja poder fugir à regra.
    """
    import os

    if os.environ.get("EVOLUTION_INSTANCE_PREFIX"):
        return os.environ["EVOLUTION_INSTANCE_PREFIX"]
    try:
        row = (
            supabase().table("loja_config").select("numero").eq("id", 1).limit(1).execute().data or [{}]
        )[0]
        numero = (row.get("numero") or "").strip()
    except Exception:  # BD indisponível → inerte, nunca um prefixo adivinhado
        return ""
    return f"ds{numero}_" if numero else ""


def _settings() -> MulticanalSettings:
    s = MulticanalSettings.from_env()
    # Marca DS: logo do email a partir do APP_BASE_URL (mesmo asset do mailer local).
    if not s.brand_logo_url and _cfg.APP_BASE_URL:
        s.brand_logo_url = f"{_cfg.APP_BASE_URL.rstrip('/')}/ds-logo-email.png"
    if not s.brand_name:
        s.brand_name = _cfg.LOJA_NAME
    s.evolution_instance_prefix = _prefixo_instancias()
    return s


def _current_user(request: Request) -> str | None:
    return token_user(request.cookies.get(COOKIE_NAME))


def _get_user_instance(username: str | None) -> str | None:
    if not username:
        return None
    row = (
        supabase().table("platform_users").select("evolution_instance")
        .eq("username", username).limit(1).execute().data or [None]
    )[0]
    return (row or {}).get("evolution_instance")


def _set_user_instance(username: str, instance: str) -> None:
    # Só grava se o utilizador tiver linha (logins env-only não têm) e ainda não tiver
    # instância — preserva a ligação existente.
    row = (
        supabase().table("platform_users").select("id, evolution_instance")
        .eq("username", username).limit(1).execute().data or [None]
    )[0]
    if row and not row.get("evolution_instance"):
        supabase().table("platform_users").update({"evolution_instance": instance}).eq("id", row["id"]).execute()


def _client_search(q: str) -> list[dict]:
    rows = (
        supabase().table("clientes_real").select("crm_id, name, telephone")
        .ilike("name", f"%{q}%").limit(15).execute().data or []
    )
    return [{"crm_id": r["crm_id"], "nome": r.get("name"), "telefone": r.get("telephone")} for r in rows]


def build_ctx() -> MulticanalCtx:
    """Contexto completo (API): supabase + settings + RBAC + auth + hooks DS."""
    return MulticanalCtx(
        supabase=supabase(),
        settings=_settings(),
        require_cap=require_cap,
        current_user=_current_user,
        get_user_instance=_get_user_instance,
        set_user_instance=_set_user_instance,
        client_search=_client_search,
    )
