"""Notas com data e lembrete nas leads (ds.lead_notas).

Funcionalidade da plataforma, não do CRM: os workers CrediDesk são read-only por
decisão documentada (DEPLOY.md §3), portanto o que o consultor escreve aqui fica
aqui. A coluna "Última acção" da página de Leads continua a espelhar o CRM
(ver integrations/ds_crm/ingest_leads.py); estas notas são o registo interno.

Visibilidade (decisão do cliente, 3 Ago 2026):
  * o LEMBRETE avisa quem o criou — o sino e o email são sempre do autor;
  * quem tem visão de loja (perfil com data_scope='loja', tipicamente o Diretor
    de Loja, e os logins de ambiente) vê e gere as notas todas.
Quem tem visão de equipa/própria vê apenas as suas — não há aqui a mesma coluna
de scoping do CRM (uma nota não tem `manager_crm_id`), e mostrar a nota de outro
consultor a quem não vê a carteira dele seria uma fuga por outro caminho.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..core.scope import acting_data_scope, current_username
from ..db import supabase

router = APIRouter()

CANAIS_VALIDOS = {"app", "email"}
COLUNAS = (
    "id, lead_crm_id, lead_nome, texto, data_nota, lembrete_em, lembrete_canais, "
    "notificado_em, visto_em, concluida_em, criado_por, criado_por_nome, created_at, updated_at"
)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ve_tudo(request: Request) -> bool:
    """Diretor de loja (ou admin): vê as notas de toda a gente."""
    return acting_data_scope(request) == "loja"


def _quem(request: Request) -> str:
    username = current_username(request)
    if not username:
        raise HTTPException(401, "Não autenticado.")
    return username


def _nome_de(sb, username: str) -> str | None:
    try:
        row = (
            sb.table("platform_users").select("nome").eq("username", username)
            .limit(1).execute().data or [None]
        )[0]
    except Exception:
        return None
    return (row or {}).get("nome")


def _normalizar_instante(valor: str | None) -> str | None:
    """ISO-8601 → ISO com timezone. O frontend envia sempre com offset (converte o
    input datetime-local com toISOString), mas um valor sem tz não pode ficar
    ambíguo na base: assume-se UTC, e o erro é explícito se a string for inválida."""
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "Data do lembrete inválida.")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _canais(valor: list[str] | None) -> list[str]:
    dados = [c for c in (valor or []) if c in CANAIS_VALIDOS]
    return dados or ["app"]


def _nota_ou_404(sb, nota_id: int, request: Request) -> dict:
    row = (
        sb.table("lead_notas").select(COLUNAS).eq("id", nota_id).limit(1).execute().data or [None]
    )[0]
    if not row:
        raise HTTPException(404, "Nota não encontrada.")
    if row["criado_por"] != _quem(request) and not _ve_tudo(request):
        raise HTTPException(403, "Sem acesso a esta nota.")
    return row


# ---- leitura -------------------------------------------------------------
@router.get("/lead/{crm_id}")
def notas_da_lead(crm_id: int, request: Request):
    sb = supabase()
    q = sb.table("lead_notas").select(COLUNAS).eq("lead_crm_id", crm_id)
    if not _ve_tudo(request):
        q = q.eq("criado_por", _quem(request))
    notas = q.order("created_at", desc=True).limit(200).execute().data or []
    return {"notas": notas, "pode_ver_todas": _ve_tudo(request)}


@router.get("/resumo")
def resumo(request: Request, limit: int = 2000):
    """Por lead: quantas notas e qual o próximo lembrete — alimenta o símbolo na
    tabela de Leads sem uma chamada por linha."""
    sb = supabase()
    q = sb.table("lead_notas").select(
        "lead_crm_id, lembrete_em, notificado_em, visto_em, concluida_em"
    )
    if not _ve_tudo(request):
        q = q.eq("criado_por", _quem(request))
    rows = q.limit(limit).execute().data or []

    agora = datetime.now(timezone.utc)
    por_lead: dict[str, dict] = {}
    for r in rows:
        chave = str(r["lead_crm_id"])
        item = por_lead.setdefault(chave, {"notas": 0, "proximo_lembrete": None, "vencido": False})
        item["notas"] += 1
        quando = r.get("lembrete_em")
        if not quando or r.get("concluida_em"):
            continue
        try:
            dt = datetime.fromisoformat(str(quando).replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt <= agora:
            item["vencido"] = True
        anterior = item["proximo_lembrete"]
        if anterior is None or str(quando) < str(anterior):
            item["proximo_lembrete"] = quando
    return {"por_lead": por_lead}


@router.get("/lembretes")
def lembretes(request: Request, horizonte_dias: int = 7):
    """Lembretes DO PRÓPRIO — vencidos (por dispensar) e os que estão a chegar.
    O sino conta os vencidos; o aviso no ecrã mostra-os."""
    sb = supabase()
    username = _quem(request)
    rows = (
        sb.table("lead_notas").select(COLUNAS)
        .eq("criado_por", username)
        .not_.is_("lembrete_em", "null")
        .is_("concluida_em", "null")
        .order("lembrete_em")
        .limit(200)
        .execute()
        .data
        or []
    )
    agora = datetime.now(timezone.utc)
    vencidos, proximos = [], []
    for r in rows:
        try:
            dt = datetime.fromisoformat(str(r["lembrete_em"]).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if dt <= agora:
            if not r.get("visto_em"):
                vencidos.append(r)
        elif (dt - agora).days <= horizonte_dias:
            proximos.append(r)
    return {"vencidos": vencidos, "proximos": proximos, "total_vencidos": len(vencidos)}


# ---- escrita -------------------------------------------------------------
class NotaIn(BaseModel):
    lead_crm_id: int
    lead_nome: str | None = None
    texto: str = Field(min_length=1, max_length=4000)
    data_nota: str | None = None          # 'YYYY-MM-DD'
    lembrete_em: str | None = None        # ISO-8601 com offset
    lembrete_canais: list[str] | None = None


@router.post("")
def criar(body: NotaIn, request: Request):
    sb = supabase()
    username = _quem(request)
    texto = body.texto.strip()
    if not texto:
        raise HTTPException(400, "A nota não pode estar vazia.")
    nome_lead = body.lead_nome
    if not nome_lead:
        lead = (
            sb.table("leads_real").select("name").eq("crm_id", body.lead_crm_id)
            .limit(1).execute().data or [None]
        )[0]
        nome_lead = (lead or {}).get("name")
    row = {
        "lead_crm_id": body.lead_crm_id,
        "lead_nome": nome_lead,
        "texto": texto,
        "data_nota": body.data_nota or None,
        "lembrete_em": _normalizar_instante(body.lembrete_em),
        "lembrete_canais": _canais(body.lembrete_canais),
        "criado_por": username,
        "criado_por_nome": _nome_de(sb, username),
    }
    criada = sb.table("lead_notas").insert(row).execute().data[0]
    return {"nota": criada}


class NotaPatch(BaseModel):
    texto: str | None = None
    data_nota: str | None = None
    lembrete_em: str | None = None
    lembrete_canais: list[str] | None = None
    limpar_lembrete: bool = False
    concluida: bool | None = None
    visto: bool | None = None


@router.patch("/{nota_id}")
def editar(nota_id: int, body: NotaPatch, request: Request):
    sb = supabase()
    _nota_ou_404(sb, nota_id, request)
    patch: dict = {"updated_at": _agora()}
    if body.texto is not None:
        texto = body.texto.strip()
        if not texto:
            raise HTTPException(400, "A nota não pode estar vazia.")
        patch["texto"] = texto
    if body.data_nota is not None:
        patch["data_nota"] = body.data_nota or None
    if body.limpar_lembrete:
        patch.update({"lembrete_em": None, "notificado_em": None, "visto_em": None})
    elif body.lembrete_em is not None:
        # Reagendar reabre a notificação: o worker volta a avisar à nova hora.
        patch.update({
            "lembrete_em": _normalizar_instante(body.lembrete_em),
            "notificado_em": None,
            "visto_em": None,
        })
    if body.lembrete_canais is not None:
        patch["lembrete_canais"] = _canais(body.lembrete_canais)
    if body.concluida is not None:
        patch["concluida_em"] = _agora() if body.concluida else None
    if body.visto is not None:
        patch["visto_em"] = _agora() if body.visto else None
    atualizada = sb.table("lead_notas").update(patch).eq("id", nota_id).execute().data
    return {"nota": (atualizada or [None])[0]}


@router.delete("/{nota_id}")
def apagar(nota_id: int, request: Request):
    sb = supabase()
    _nota_ou_404(sb, nota_id, request)
    sb.table("lead_notas").delete().eq("id", nota_id).execute()
    return {"ok": True}
