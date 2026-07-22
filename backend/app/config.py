"""Centralised settings loaded from env (.env via python-dotenv in main.py)."""
from __future__ import annotations
import os


class Settings:
    ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
    SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_ANON_KEY: str = os.environ.get("SUPABASE_ANON_KEY", "")

    META_WA_VERIFY_TOKEN: str = os.environ.get("META_WA_VERIFY_TOKEN", "")
    META_WA_PHONE_NUMBER_ID: str = os.environ.get("META_WA_PHONE_NUMBER_ID", "")
    META_WA_ACCESS_TOKEN: str = os.environ.get("META_WA_ACCESS_TOKEN", "")
    META_WA_APP_SECRET: str = os.environ.get("META_WA_APP_SECRET", "")
    DEMO_RECIPIENTS: str = os.environ.get("DEMO_RECIPIENTS", "")

    # In-app login (item 1). Set in .env on deploy; empty APP_PASSWORD +
    # APP_USERS means login is unconfigured and fails closed (nobody can
    # authenticate) rather than open. Never hardcode credentials here.
    #  - APP_USER / APP_PASSWORD: the primary shared credential.
    #  - APP_USERS: extra accounts as a JSON object, e.g. test logins —
    #      APP_USERS={"amin":"<senha>"}  (merged with the primary one).
    APP_USER: str = os.environ.get("APP_USER", "ds")
    APP_PASSWORD: str = os.environ.get("APP_PASSWORD", "")
    APP_USERS: str = os.environ.get("APP_USERS", "")
    APP_SESSION_SECRET: str = os.environ.get("APP_SESSION_SECRET", "")
    # Fernet key (urlsafe-base64, 32 bytes) used to encrypt CRM credentials at
    # rest in ds.platform_users. Generate once with cryptography.fernet.Fernet.
    APP_CRYPTO_KEY: str = os.environ.get("APP_CRYPTO_KEY", "")
    # Global service PIN that unlocks the CRM-credentials ("Definições") tab.
    # Default matches the agreed operator PIN; override via env in production.
    APP_SERVICE_PIN: str = os.environ.get("APP_SERVICE_PIN", "28021904")
    # Session cookie Secure flag. True in production (HTTPS); set COOKIE_SECURE=false
    # to allow login over plain HTTP (e.g. testing by IP before a domain + SSL).
    COOKIE_SECURE: bool = os.environ.get("COOKIE_SECURE", "true").strip().lower() != "false"

    ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "development")
    LOJA_NAME: str = os.environ.get("LOJA_NAME", "DS Crédito Ramada – Jardim da Amoreira")
    # Short form for headers/prompts (no location suffix). Defaults to LOJA_NAME
    # truncated at the " – " separator (e.g. "DS Crédito Ramada").
    LOJA_SHORT_NAME: str = os.environ.get("LOJA_SHORT_NAME", "") or LOJA_NAME.split(" – ")[0]
    BRAND_RED: str = os.environ.get("BRAND_RED", "#E30613")

    # Public base URL of the frontend (used to build links inside emails, e.g. the
    # password-reset link). Override per environment (staging vs prod).
    APP_BASE_URL: str = os.environ.get("APP_BASE_URL", "https://dscredito.synertia-gw.ai")

    # ---- Email (AWS SES) ----
    # Reused by password recovery AND any platform communication (Workstream D).
    # Empty SES_FROM → email is UNCONFIGURED: the mailer logs instead of sending, and
    # non-production endpoints surface a dev link so the flow is testable on staging.
    # On EC2 prefer an IAM role over static keys; region defaults to the box's region.
    SES_REGION: str = os.environ.get("SES_REGION", os.environ.get("AWS_REGION", "eu-west-1"))
    SES_FROM: str = os.environ.get("SES_FROM", "")  # e.g. "DS Crédito <noreply@dscredito.pt>"

    # ---- SMS (AWS: SNS / End User Messaging) ----
    # Uses the EC2 IAM role; region defaults to the box's. SMS_SENDER is the
    # alphanumeric sender ID (needs registration/origination for PT). Empty region
    # or a boto3/permission failure → channel stays inert (logs, delivered=False).
    AWS_SMS_REGION: str = os.environ.get("AWS_SMS_REGION", os.environ.get("AWS_REGION", "eu-west-1"))
    SMS_SENDER: str = os.environ.get("SMS_SENDER", "DSCredito")

    # ---- WhatsApp via Evolution API (self-hosted) ----
    # All three must be set for the channel to be active; otherwise it stays inert.
    EVOLUTION_API_URL: str = os.environ.get("EVOLUTION_API_URL", "")
    EVOLUTION_API_KEY: str = os.environ.get("EVOLUTION_API_KEY", "")
    EVOLUTION_INSTANCE: str = os.environ.get("EVOLUTION_INSTANCE", "")
    # Namespace prefix for per-user instance names on the SHARED Evolution server.
    # Must be unique per loja/deployment (e.g. "ds_" Ramada, "dsl_" Loulé) so two
    # instâncias never collide on the same Evolution box.
    EVOLUTION_INSTANCE_PREFIX: str = os.environ.get("EVOLUTION_INSTANCE_PREFIX", "ds_")

    CHAT_MODEL: str = "claude-sonnet-4-6"
    NEWSLETTER_MODEL: str = "claude-sonnet-4-6"


settings = Settings()
