"""Leads — read-only view over the live CrediDesk mirror (ds.leads_real).

The page used to read ds.leads, a demo/mock table only ever populated by
seed_mock_data.py or the old "Nova lead" form — empty in production, which is
why the page showed no leads. Real leads live in ds.leads_real (ingested from
CrediDesk), so this now reads that mirror, scoped to the logged-in user's
profile like the dashboard / crm-live views.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..core.documentos_credito import documentos_para
from ..core.mailer import branded_email
from ..core.names import fix_name
from ..core.scope import apply_scope, current_username, require_cap, user_scope
from ..db import supabase

router = APIRouter()

# Estados de lead fechados no CrediDesk — não são pipeline de leads:
#   Concluido = já convertida em processo (hoje é cliente, vive em Clientes-live)
#   Perdido/Anulado = morta. Só "Pendente" (em aberto) é uma lead por trabalhar.
CLOSED_STATES = {"Concluido", "Concluído", "Perdido", "Anulado"}


def _texto_acao(r: dict) -> str | None:
    """O que foi a última intervenção, em texto legível.

    O CRM guarda o teor da acção em `observation` — nota escrita pelo consultor
    (typeId 0) ou evento de sistema (typeId 1/-1: "criou a lead", "arquivou a Lead
    com o motivo: ..."). Quando o registo não traz texto (typeId 3), cai para o
    estado que a lead tomou nesse momento, que é a única informação útil que resta.
    HTML solto (<br />) aparece nas mensagens de arquivo — limpo aqui, porque a
    tabela do frontend mostra texto, não markup.
    """
    texto = (r.get("last_action_text") or "").replace("<br />", " ").replace("<br>", " ").strip()
    if texto:
        return " ".join(texto.split())
    estado = r.get("last_action_state")
    return f"Estado: {estado}" if estado else None


def _e_nova(r: dict) -> bool:
    """Lead POR TRABALHAR: ninguém registou contacto no CRM.

    `interacoes_agente` conta as entradas do histórico escritas por uma pessoa.
    Enquanto o ingest nocturno não passar pela lead o campo é nulo — nesse caso
    caímos no sinal que já temos: um único registo de histórico, do tipo sistema
    ("criou a lead"), ou nenhum de todo.
    """
    interacoes = r.get("interacoes_agente")
    if interacoes is not None:
        return interacoes == 0
    total = r.get("last_action_count")
    if total in (None, 0):
        return True
    return total == 1 and r.get("last_action_type") != 0


def _shape(r: dict, boas_vindas: dict[str, str] | None = None) -> dict:
    """Map a leads_real row to the shape the frontend Lead table expects."""
    # Data da última acção: a do histórico do CRM quando a temos (é a real), senão
    # o `updatedon` da lead — que marca qualquer edição, não uma intervenção.
    ultima = r.get("last_action_at") or r.get("updated_on_crm") or r.get("created_on_crm")
    return {
        "id": str(r.get("crm_id")),
        "nome": r.get("name"),
        "telefone": r.get("telephone"),
        "email": r.get("email"),
        "nif": None,  # not mirrored on leads_real
        "produto": r.get("type_name"),
        "consultor_id": r.get("manager_name"),
        "consultor_nome": fix_name(r.get("manager_name")),
        "status": r.get("state_name"),  # Pendente / Concluido / Perdido
        "ultima_acao": ultima,
        "ultima_acao_texto": _texto_acao(r),
        "ultima_acao_agente": fix_name(r.get("last_action_agent")),
        "ultima_acao_tipo": r.get("last_action_type"),
        "acoes_total": r.get("last_action_count"),
        "nova": _e_nova(r),
        "boas_vindas_em": (boas_vindas or {}).get(str(r.get("crm_id"))),
        "created_at": r.get("created_on_crm"),
    }


@router.get("/list")
def list_leads(request: Request, limit: int = 1000):
    sb = supabase()
    scope = user_scope(request)  # None = loja-wide; else this user's filter
    q = apply_scope(
        sb.table("leads_real").select(
            "crm_id, name, telephone, email, type_name, manager_name, "
            "state_name, archived, updated_on_crm, created_on_crm, "
            "last_action_at, last_action_text, last_action_type, last_action_state, "
            "last_action_agent, last_action_count, interacoes_agente"
        ),
        scope,
    )
    rows = (
        q.eq("archived", False)
        .order("created_on_crm", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    # Só leads em aberto (Pendente) — as convertidas/perdidas não são pipeline.
    abertas = [r for r in rows if r.get("state_name") not in CLOSED_STATES]
    return {"leads": [_shape(r, _boas_vindas_enviadas(sb)) for r in abertas]}


# ---- Email de boas-vindas -------------------------------------------------
TIPO_BOAS_VINDAS = "boas_vindas"


def _boas_vindas_enviadas(sb) -> dict[str, str]:
    """{lead_crm_id: data do envio} — uma query para a tabela toda, em vez de uma
    por linha. Guarda o PRIMEIRO envio: é o que interessa saber ("já foi feito")."""
    rows = (
        sb.table("lead_emails").select("lead_crm_id, enviado_em")
        .eq("tipo", TIPO_BOAS_VINDAS).order("enviado_em").limit(5000).execute().data or []
    )
    out: dict[str, str] = {}
    for r in rows:
        out.setdefault(str(r["lead_crm_id"]), r["enviado_em"])
    return out


def _lead_no_ambito(sb, request: Request, crm_id: int) -> dict:
    """A lead, se o utilizador a puder ver — o mesmo scoping da listagem. Sem isto,
    o endpoint de envio seria uma porta lateral para leads fora da carteira."""
    q = apply_scope(
        sb.table("leads_real").select(
            "crm_id, name, email, telephone, type_name, type_full_name, manager_name, state_name"
        ).eq("crm_id", crm_id),
        user_scope(request),
    )
    row = (q.limit(1).execute().data or [None])[0]
    if not row:
        raise HTTPException(404, "Lead não encontrada no âmbito da sua carteira.")
    return row


def _loja_nome(sb) -> str:
    try:
        row = (sb.table("loja_config").select("nome").limit(1).execute().data or [None])[0]
    except Exception:
        row = None
    return (row or {}).get("nome") or settings.LOJA_NAME


def _intro_personalizada(sb) -> str | None:
    """Texto de abertura editável em ds.msg_templates (categoria `boas_vindas_email`).
    Sem linha activa, usa-se o texto por omissão desta função — assim a loja pode
    afinar a mensagem sem passar por um deploy."""
    try:
        row = (
            sb.table("msg_templates").select("corpo")
            .eq("categoria", "boas_vindas_email").eq("ativo", True)
            .limit(1).execute().data or [None]
        )[0]
    except Exception:
        return None
    return (row or {}).get("corpo")


def _preparar_boas_vindas(sb, lead: dict) -> dict:
    """Assunto + HTML + lista de documentos para esta lead."""
    nome = (lead.get("name") or "").strip() or "Cliente"
    primeiro = nome.split()[0]
    consultor = fix_name(lead.get("manager_name")) or None
    loja = _loja_nome(sb)
    produto, documentos = documentos_para(lead.get("type_full_name"), lead.get("type_name"))

    intro = _intro_personalizada(sb) or (
        "Obrigado pelo seu interesse. A partir de agora acompanhamos o seu pedido de "
        "{{produto}} e tratamos de tudo consigo — da análise à melhor proposta do mercado."
    )
    intro = (
        intro.replace("{{nome_cliente}}", nome)
        .replace("{{nome_consultor}}", consultor or "a nossa equipa")
        .replace("{{produto}}", produto)
        .replace("{{loja}}", loja)
    )

    # `list-style` inline: sem isto os marcadores desaparecem em clientes de email
    # (e na pré-visualização, onde o reset de CSS da plataforma os remove).
    lista = "".join(f"<li style='margin:4px 0;list-style:disc'>{d}</li>" for d in documentos)
    corpo = (
        f"Olá {primeiro},<br><br>"
        f"{intro}<br><br>"
        f"<strong>Documentos necessários — {produto}</strong>"
        f"<ul style='padding-left:18px;margin:8px 0'>{lista}</ul>"
        "Se houver mais do que um titular, cada um deve enviar os seus documentos. "
        "Pode responder a este email com os ficheiros digitalizados ou fotografados, "
        "desde que estejam legíveis e completos (todas as páginas).<br><br>"
        + (f"Fico ao seu dispor,<br><strong>{consultor}</strong><br>{loja}"
           if consultor else f"Ficamos ao seu dispor,<br><strong>{loja}</strong>")
    )
    return {
        "produto": produto,
        "documentos": documentos,
        "destinatario": (lead.get("email") or "").strip(),
        "assunto": f"Bem-vindo(a) à DS Crédito — documentos para o seu {produto}",
        "html": branded_email("Bem-vindo(a) à DS Crédito", corpo),
        "consultor": consultor,
        "loja": loja,
    }


@router.get("/{crm_id}/boas-vindas")
def preview_boas_vindas(crm_id: int, request: Request):
    """Pré-visualização do email — o consultor vê exactamente o que sai antes de enviar."""
    sb = supabase()
    lead = _lead_no_ambito(sb, request, crm_id)
    dados = _preparar_boas_vindas(sb, lead)
    enviados = (
        sb.table("lead_emails").select("enviado_em, destinatario, entregue, erro, enviado_por")
        .eq("lead_crm_id", crm_id).eq("tipo", TIPO_BOAS_VINDAS)
        .order("enviado_em", desc=True).limit(5).execute().data or []
    )
    return {
        "lead": {"id": str(crm_id), "nome": lead.get("name"), "produto": dados["produto"]},
        "destinatario": dados["destinatario"],
        "assunto": dados["assunto"],
        "documentos": dados["documentos"],
        "html": dados["html"],
        "consultor": dados["consultor"],
        "envios": enviados,
    }


@router.post("/{crm_id}/boas-vindas")
def enviar_boas_vindas(crm_id: int, request: Request):
    """Enfileira (e entrega já) o email de boas-vindas com a checklist de documentos.

    Passa pela fila multicanal e não pelo mailer directo: é comunicação a um
    cliente, logo tem de ficar no registo de envios e respeitar canal activo,
    tecto diário e cancelamento de subscrição. Como é um destinatário só, pede-se
    a entrega imediata — esperar pelo tique do worker (até 60s) lê-se como avaria.
    """
    require_cap(request, "messaging.send")
    sb = supabase()
    lead = _lead_no_ambito(sb, request, crm_id)
    dados = _preparar_boas_vindas(sb, lead)
    if not dados["destinatario"]:
        raise HTTPException(400, "Esta lead não tem email no CRM.")

    # Import tardio: o módulo multicanal é um pacote à parte, instalado na box.
    from synertia_multicanal.dispatcher import enqueue_many, send_pending_now

    from ..multicanal_ctx import build_ctx

    ctx = build_ctx()
    quem = current_username(request)
    r = enqueue_many(
        ctx,
        "email",
        [{"destinatario": dados["destinatario"], "assunto": dados["assunto"], "corpo": dados["html"]}],
        ref_tipo=TIPO_BOAS_VINDAS,
        ref_id=str(crm_id),
        criado_por=quem,
    )
    envio_id = (r.get("ids") or [None])[0]
    entregue, erro = None, None
    if envio_id:
        res = send_pending_now(ctx, envio_id)
        entregue = bool(res.get("delivered"))
        erro = res.get("error") or res.get("skipped")

    sb.table("lead_emails").insert({
        "lead_crm_id": crm_id,
        "tipo": TIPO_BOAS_VINDAS,
        "destinatario": dados["destinatario"],
        "assunto": dados["assunto"],
        "envio_id": envio_id,
        "entregue": entregue,
        "erro": str(erro)[:300] if erro else None,
        "enviado_por": quem,
        "enviado_em": datetime.now(timezone.utc).isoformat(),
    }).execute()
    return {
        "enfileirado": bool(envio_id),
        "entregue": entregue,
        "erro": erro,
        "destinatario": dados["destinatario"],
    }
