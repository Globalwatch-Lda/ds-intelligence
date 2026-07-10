"""DS Intelligence v1 — FastAPI entrypoint.

Pilot loja: DS Crédito Ramada – Jardim da Amoreira.
Phase 1 deliverables (per Amin 5 May 2026 follow-up):
  1. Base de dados WhatsApp para comunicação inicial dos colaboradores
  2. Integração IA × CRM (crédito + seguros)
  3. Newsletter via WhatsApp

Voice cold-call agent and "Bruna" personal assistant are Phase 2 — parked
per Sílvia's preference for human-led brand experience.
"""
from __future__ import annotations
from dotenv import load_dotenv

load_dotenv()  # must happen before importing config

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .routers import dashboard, triggers, newsletter, chat, whatsapp, leads, broadcasts, crm_live, recap, auth, perfis, equipas, messaging, public, settings as settings_router
from .routers.auth import COOKIE_NAME, valid_token

app = FastAPI(
    title="DS Intelligence v1",
    version="0.1.0",
    description="Plataforma de Inteligência Comercial para DS Crédito + DS Seguros",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dscredito.synertia-gw.ai",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# In-app session gate (item 1). Every /api/* call requires a valid session
# cookie, EXCEPT the auth endpoints themselves. This is what lets us drop the
# nginx basic-auth popup: the platform now authenticates itself. The WhatsApp
# webhook stays gated (it was already behind basic-auth, so no regression —
# enabling inbound Meta callbacks is a separate task with signature checks).
_AUTH_EXEMPT = ("/api/auth", "/api/public")


@app.middleware("http")
async def require_session(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not path.startswith(_AUTH_EXEMPT):
        if not valid_token(request.cookies.get(COOKIE_NAME)):
            return JSONResponse({"detail": "Não autenticado."}, status_code=401)
    return await call_next(request)


@app.get("/")
def root():
    return {
        "service": "ds-intelligence-api",
        "env": settings.ENVIRONMENT,
        "version": "0.1.0",
        "loja": settings.LOJA_NAME,
    }


@app.get("/health")
def health():
    return {"ok": True}


app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(triggers.router, prefix="/api/triggers", tags=["triggers"])
app.include_router(newsletter.router, prefix="/api/newsletter", tags=["newsletter"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(whatsapp.router, prefix="/api/whatsapp", tags=["whatsapp"])
app.include_router(leads.router, prefix="/api/leads", tags=["leads"])
app.include_router(broadcasts.router, prefix="/api/broadcasts", tags=["broadcasts"])
app.include_router(crm_live.router, prefix="/api/crm-live", tags=["crm-live"])
app.include_router(recap.router, prefix="/api/recap", tags=["recap"])
app.include_router(perfis.router, prefix="/api/perfis", tags=["perfis"])
app.include_router(equipas.router, prefix="/api/equipas", tags=["equipas"])
app.include_router(messaging.router, prefix="/api/messaging", tags=["messaging"])
app.include_router(public.router, prefix="/api/public", tags=["public"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
