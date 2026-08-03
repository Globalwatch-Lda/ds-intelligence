"""Envio dos lembretes de notas de leads que já venceram (canal email).

O canal `app` (sino + aviso no ecrã) não precisa de worker nenhum — a página lê
ds.lead_notas directamente. Só o email precisa de alguém a correr fora do browser,
senão um lembrete marcado para as 9h só saía quando o consultor abrisse a app.

Corre dentro do `run_dispatcher.py`, que o cron já executa de minuto a minuto, para
não haver mais uma entrada de crontab a manter em duas lojas (ver DEPLOY.md §2).
O email vai para quem CRIOU o lembrete (decisão do cliente, 3 Ago 2026), nunca para
a lead — isto é um aviso interno, não uma comunicação a cliente, por isso passa pelo
mailer directo (SES) e não pela fila ds.envios, que existe para respeitar limites e
opt-outs de destinatários externos.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..config import settings
from ..db import supabase
from .mailer import branded_email, email_configured, send_email

log = logging.getLogger("ds.lembretes")

try:  # o servidor é Linux (tem tzdata); num Windows sem tzdata cai para UTC
    from zoneinfo import ZoneInfo

    LISBOA = ZoneInfo("Europe/Lisbon")
except Exception:  # pragma: no cover - ambiente sem base de fusos
    LISBOA = timezone.utc


def _quando_pt(valor: str | None) -> str:
    if not valor:
        return "—"
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return str(valor)
    return dt.astimezone(LISBOA).strftime("%d/%m/%Y às %H:%M")


def _email_do_autor(sb, username: str) -> tuple[str | None, str | None]:
    row = (
        sb.table("platform_users").select("email, nome").eq("username", username)
        .eq("is_active", True).limit(1).execute().data or [None]
    )[0]
    if not row:
        return None, None
    return row.get("email"), row.get("nome")


def processar_lembretes(limite: int = 50) -> dict:
    """Envia os emails dos lembretes vencidos. Devolve um resumo para o log.

    Idempotente: cada nota é marcada com `notificado_em` assim que é tratada, e
    uma falha de envio grava o erro em `notificacao_erro` sem voltar à fila — um
    email que a SES rejeita hoje vai rejeitar outra vez daqui a um minuto, e o
    lembrete continua visível no sino, que é o canal que não falha.
    """
    sb = supabase()
    agora = datetime.now(timezone.utc)
    pendentes = (
        sb.table("lead_notas")
        .select("id, lead_crm_id, lead_nome, texto, data_nota, lembrete_em, lembrete_canais, criado_por")
        .not_.is_("lembrete_em", "null")
        .is_("notificado_em", "null")
        .is_("concluida_em", "null")
        .lte("lembrete_em", agora.isoformat())
        .order("lembrete_em")
        .limit(limite)
        .execute()
        .data
        or []
    )
    enviados = falhados = ignorados = 0
    for nota in pendentes:
        canais = nota.get("lembrete_canais") or ["app"]
        if "email" not in canais:
            # Só sino: nada a enviar, mas fica marcado para não voltar a ser lido.
            sb.table("lead_notas").update({"notificado_em": agora.isoformat()}).eq("id", nota["id"]).execute()
            ignorados += 1
            continue
        destino, nome = _email_do_autor(sb, nota["criado_por"])
        if not destino or not email_configured():
            motivo = "sem email na conta" if not destino else "SES não configurado"
            sb.table("lead_notas").update(
                {"notificado_em": agora.isoformat(), "notificacao_erro": motivo}
            ).eq("id", nota["id"]).execute()
            falhados += 1
            continue

        lead = nota.get("lead_nome") or f"lead {nota['lead_crm_id']}"
        html = branded_email(
            "Lembrete de lead",
            (
                f"Olá {nome or nota['criado_por']},<br><br>"
                f"Tem um lembrete marcado para <strong>{_quando_pt(nota.get('lembrete_em'))}</strong> "
                f"sobre a lead <strong>{lead}</strong>.<br><br>"
                f"<em>{(nota.get('texto') or '').strip()[:1000]}</em>"
            ),
            cta_label="Abrir a lead",
            cta_url=f"{settings.APP_BASE_URL}/leads?lead={nota['lead_crm_id']}",
        )
        resultado = send_email(
            destino,
            f"Lembrete: {lead}",
            html,
            text_body=f"Lembrete ({_quando_pt(nota.get('lembrete_em'))}) sobre {lead}: {(nota.get('texto') or '')[:500]}",
        )
        patch = {"notificado_em": agora.isoformat()}
        if resultado.get("delivered"):
            enviados += 1
        else:
            patch["notificacao_erro"] = str(resultado.get("error"))[:300]
            falhados += 1
        sb.table("lead_notas").update(patch).eq("id", nota["id"]).execute()

    resumo = {"lembretes_devidos": len(pendentes), "emails": enviados, "falhas": falhados, "so_app": ignorados}
    if pendentes:
        log.info("[lembretes] %s", resumo)
    return resumo
