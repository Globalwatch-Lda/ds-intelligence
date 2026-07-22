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
        options=ClientOptions(schema=settings.DB_SCHEMA),
    )
