"""Pluggable email sender (AWS SES) — shared by password recovery and, later, the
general communication layer (Workstream D).

If SES is configured (settings.SES_FROM set) an HTML email is sent via boto3 SES —
using the EC2 instance's IAM role or ambient AWS credentials. If it is NOT
configured, the mailer logs the message and returns delivered=False so callers can,
in non-production, surface a dev link instead. Nothing here ever raises to the
caller: a delivery failure returns delivered=False, it does not 500 the request.
"""
from __future__ import annotations

import logging

from ..config import settings, loja_nome

log = logging.getLogger("ds.mailer")


def email_configured() -> bool:
    return bool(settings.SES_FROM)


def send_email(to: str | None, subject: str, html_body: str, text_body: str | None = None) -> dict:
    """Best-effort send. Returns {'delivered': bool, 'error': str|None}."""
    if not to:
        return {"delivered": False, "error": "no recipient"}
    if not email_configured():
        log.warning("[mailer] SES not configured — would email %s: %s", to, subject)
        return {"delivered": False, "error": "email not configured"}
    try:
        import boto3  # lazy: only needed when SES is actually configured

        ses = boto3.client("ses", region_name=settings.SES_REGION)
        body: dict = {"Html": {"Data": html_body, "Charset": "UTF-8"}}
        if text_body:
            body["Text"] = {"Data": text_body, "Charset": "UTF-8"}
        ses.send_email(
            Source=settings.SES_FROM,
            Destination={"ToAddresses": [to]},
            Message={"Subject": {"Data": subject, "Charset": "UTF-8"}, "Body": body},
        )
        return {"delivered": True, "error": None}
    except Exception as e:  # missing boto3, unverified identity, sandbox, etc.
        log.error("[mailer] SES send failed to %s: %s", to, e)
        return {"delivered": False, "error": str(e)}


def branded_email(
    titulo: str,
    corpo_html: str,
    cta_label: str | None = None,
    cta_url: str | None = None,
    unsub_url: str | None = None,
) -> str:
    """Wrap content in a simple DS Crédito-branded HTML shell (inline styles for
    email-client compatibility). The logo is referenced from the public site; if the
    asset is missing the alt text ("DS Crédito") shows instead."""
    red = settings.BRAND_RED
    logo = f"{settings.APP_BASE_URL}/ds-logo-email.png"
    cta = ""
    if cta_label and cta_url:
        cta = (
            f'<tr><td style="padding:8px 0 24px 0;">'
            f'<a href="{cta_url}" style="background:{red};color:#ffffff;text-decoration:none;'
            f'display:inline-block;padding:12px 22px;border-radius:8px;font-weight:600;">{cta_label}</a>'
            f"</td></tr>"
        )
    unsub = ""
    if unsub_url:
        unsub = (
            f'<br><span style="color:#8e8e93;">Não deseja receber estas comunicações? '
            f'<a href="{unsub_url}" style="color:#8e8e93;">Cancelar subscrição</a>.</span>'
        )
    return f"""\
<!doctype html>
<html lang="pt"><body style="margin:0;background:#f5f5f7;font-family:Arial,Helvetica,sans-serif;color:#1c1c1e;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f7;padding:24px 0;">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;max-width:560px;">
        <tr><td style="background:{red};padding:18px 28px;">
          <img src="{logo}" alt="DS Crédito" height="34" style="height:34px;display:block;border:0;" />
        </td></tr>
        <tr><td style="padding:28px;">
          <h1 style="margin:0 0 12px 0;font-size:20px;color:#1c1c1e;">{titulo}</h1>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:15px;line-height:1.55;color:#3a3a3c;">
            <tr><td style="padding-bottom:16px;">{corpo_html}</td></tr>
            {cta}
          </table>
        </td></tr>
        <tr><td style="padding:16px 28px;border-top:1px solid #ececee;font-size:12px;color:#8e8e93;">
          {loja_nome()}{unsub}
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
