"""Enqueue + throttled delivery over ds.envios, respecting ds.messaging_config.

Enqueue schedules each recipient with a spaced `agendado_para` — `batch_size`
messages go out together, then the next batch waits `intervalo_segundos` — so a
large blast is spread over time and doesn't trip anti-spam alarms. A dispatcher
worker (scripts/run_dispatcher.py, run by cron, or POST /api/messaging/dispatch)
calls `process_due`, which sends every due message per active channel up to that
channel's `cap_diario` for the day.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..db import supabase
from .channels import CHANNELS, send_now

_DEFAULT_CFG = {"ativo": False, "batch_size": 50, "intervalo_segundos": 2, "cap_diario": 500, "remetente": None}


def _cfg(sb, canal: str) -> dict:
    row = (
        sb.table("messaging_config").select("*").eq("canal", canal).limit(1).execute().data or [None]
    )[0]
    return {**_DEFAULT_CFG, **(row or {})}


def _user_evolution_instance(sb, username: str | None) -> str | None:
    """The sender's own WhatsApp instance (their number), for 'em nome do utilizador'."""
    if not username:
        return None
    row = (
        sb.table("platform_users").select("evolution_instance").eq("username", username).limit(1).execute().data
        or [None]
    )[0]
    return (row or {}).get("evolution_instance")


def enqueue_many(
    canal: str,
    itens: list[dict],
    ref_tipo: str | None = None,
    ref_id: str | None = None,
    criado_por: str | None = None,
) -> dict:
    """Queue per-recipient messages (each with its own corpo/assunto) for one
    channel, spacing batches per config. `itens`: [{destinatario, corpo, assunto?}].
    Used when the body is personalised (e.g. a per-client unsubscribe link)."""
    sb = supabase()
    cfg = _cfg(sb, canal)
    batch = max(1, int(cfg["batch_size"]))
    interval = max(0, int(cfg["intervalo_segundos"]))
    now = datetime.now(timezone.utc)

    # For WhatsApp, freeze the sender's own instance now so each message goes out
    # from their number even if their profile changes later.
    canal_conta = _user_evolution_instance(sb, criado_por) if canal == "whatsapp_evolution" else None

    rows = []
    for i, it in enumerate(x for x in itens if x.get("destinatario")):
        offset = (i // batch) * interval
        rows.append(
            {
                "canal": canal,
                "destinatario": it["destinatario"],
                "assunto": it.get("assunto"),
                "corpo": it.get("corpo", ""),
                "ref_tipo": ref_tipo,
                "ref_id": ref_id,
                "criado_por": criado_por,
                "canal_conta": canal_conta,
                "status": "pendente",
                "agendado_para": (now + timedelta(seconds=offset)).isoformat(),
            }
        )
    if rows:
        for k in range(0, len(rows), 500):
            sb.table("envios").insert(rows[k : k + 500]).execute()
    return {"enqueued": len(rows), "canal": canal}


def enqueue(
    canal: str,
    destinatarios: list[str],
    corpo: str,
    assunto: str | None = None,
    ref_tipo: str | None = None,
    ref_id: str | None = None,
    criado_por: str | None = None,
) -> dict:
    """Queue the SAME body to many recipients (spaced per config)."""
    itens = [{"destinatario": d, "corpo": corpo, "assunto": assunto} for d in destinatarios]
    return enqueue_many(canal, itens, ref_tipo=ref_tipo, ref_id=ref_id, criado_por=criado_por)


def process_due(max_per_run: int = 200) -> dict:
    """Send all due, pending messages per ACTIVE channel, up to each channel's daily
    cap. Called by the cron worker or the dispatch endpoint. Returns per-channel counts."""
    sb = supabase()
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    result: dict = {"sent": 0, "falhou": 0, "por_canal": {}}

    for canal in CHANNELS:
        cfg = _cfg(sb, canal)
        if not cfg.get("ativo"):
            continue
        sent_today = (
            sb.table("envios").select("id", count="exact")
            .eq("canal", canal).eq("status", "enviado").gte("enviado_em", today.isoformat())
            .limit(1).execute().count or 0
        )
        remaining = max(0, int(cfg["cap_diario"]) - sent_today)
        if remaining <= 0:
            continue
        due = (
            sb.table("envios").select("id, destinatario, assunto, corpo, canal_conta")
            .eq("canal", canal).eq("status", "pendente").lte("agendado_para", now.isoformat())
            .order("agendado_para").limit(min(remaining, max_per_run)).execute().data or []
        )
        sent = falhou = 0
        for e in due:
            res = send_now(
                canal, e["destinatario"], e.get("assunto"), e["corpo"],
                cfg.get("remetente"), instance=e.get("canal_conta"),
            )
            sb.table("envios").update(
                {
                    "status": "enviado" if res["delivered"] else "falhou",
                    "enviado_em": datetime.now(timezone.utc).isoformat(),
                    "erro": res.get("error"),
                }
            ).eq("id", e["id"]).execute()
            if res["delivered"]:
                sent += 1
            else:
                falhou += 1
        result["por_canal"][canal] = {"enviado": sent, "falhou": falhou}
        result["sent"] += sent
        result["falhou"] += falhou
    return result
