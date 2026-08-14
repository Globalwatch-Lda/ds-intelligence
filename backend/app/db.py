"""Supabase client singleton.

DS Intelligence shares the Clara_Production Supabase project (same pattern as
the voicebot multi-tenancy) but lives entirely under its own schema (settings
.DB_SCHEMA: "ds" = Ramada, "dsl" = Loulé) so it cannot read or write any other
app's tables. The schema scoping is set here via ClientOptions so every query
in the codebase is automatically `<schema>.*`.
"""
from __future__ import annotations
from functools import lru_cache
from supabase import create_client, Client
from supabase.client import ClientOptions
from .config import settings


@lru_cache(maxsize=1)
def supabase() -> Client:
    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY):
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured")
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
        # Default é 120s — uma única ligação lenta/instável ao Supabase (já visto
        # antes, ConnectionTerminated intermitente) prendia o worker uvicorn
        # (--workers 1) até 2 minutos por pedido, sem responder a mais nada
        # entretanto. 15s é generoso para qualquer query desta app e falha rápido
        # em vez de pendurar o servidor inteiro. Ver worklog 14 ago 2026.
        options=ClientOptions(schema=settings.DB_SCHEMA, postgrest_client_timeout=15),
    )
