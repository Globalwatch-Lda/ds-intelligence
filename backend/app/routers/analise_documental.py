"""Análise Documental — deteção de sinais de fraude documental num processo do CRM.

Base de análise (validada com o cliente): os manuais da DS na pasta verifica/,
destilados em core/analise_documental_kb.py. O motor só assinala sinais previstos
nesse catálogo.

FASE 1 (estrutural): resolve o número de processo no mirror da PRÓPRIA loja,
lê AO VIVO do CRM da própria loja os proponentes e a checklist de documentos, e
cruza-os com o catálogo. Não descarrega os ficheiros — os sinais que exigem ver o
conteúdo são devolvidos como "a verificar no documento".

ISOLAMENTO ENTRE LOJAS (garantido por construção):
  * a referência é procurada em `processos_real` do schema desta instância
    (DB_SCHEMA: ds=Ramada, dsl=Loulé) e com o scope RBAC do utilizador — uma
    referência de outra loja não existe aqui → 404;
  * a leitura ao vivo usa uma conta CRM desta instância (list_crm_accounts lê
    platform_users desta loja: Ramada agência 839, Loulé agência 824), escolhida
    pelo source_account do próprio processo.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import anthropic
from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..core.analise_documental_kb import (
    FONTE, METODO, SINAIS_ALERTA, catalogo_para_prompt,
)
from ..core.scope import user_scope, apply_scope, scope_label
from ..db import supabase

router = APIRouter()


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        try:
            return date.fromisoformat(s[:10])
        except (ValueError, TypeError):
            return None


def _pick_account(source_accounts: list[str] | None):
    """Conta CRM DESTA loja que consegue ver o processo. Escolhe uma cujo
    username esteja em source_accounts; senão a primeira disponível."""
    from integrations.ds_crm.accounts import list_crm_accounts

    accounts = list_crm_accounts()
    if not accounts:
        raise HTTPException(503, "Sem credenciais CRM configuradas nesta loja.")
    sa = set(source_accounts or [])
    for a in accounts:
        if a.username in sa:
            return a
    return accounts[0]


def _proponentes_factos(prop_raw: list[dict], today: date) -> list[dict]:
    out = []
    for p in prop_raw:
        cc_val = _parse_date(p.get("identityCardExpirationDate"))
        out.append({
            "id": p.get("creditProcessProponentId") or p.get("id"),
            "nome": p.get("name") or p.get("customerName"),
            "idade": p.get("proponentAge"),
            "data_nascimento": p.get("dateBirth") or p.get("dateofbirth"),
            "nacionalidade": p.get("nationality"),
            "profissao": p.get("profession") or None,
            "situacao_profissional": p.get("professionalSituation"),
            "rendimento_mensal": p.get("monthlyIncomeAmount"),
            "encargos_mensais": p.get("monthlyChargesAmount"),
            "credito_mensal": p.get("monthlyCreditAmount"),
            "nif": p.get("taxIdNumber") or p.get("taxidnumber"),
            "cc_validade": p.get("identityCardExpirationDate"),
            "cc_expirado": bool(cc_val and cc_val < today),
            "consentimento_rgpd": bool(p.get("rgpdAuthorized") or p.get("rdpgAuthorized")),
            "garante": str(p.get("iscreditGuarantor") or "0") == "1",
        })
    return out


def _documentos_factos(docs_raw: list[dict]) -> dict:
    """Agrupa a checklist por proponente. validated==1 => validado."""
    grupos: dict = {}
    total = validados = 0
    obrigatorios_pendentes: list[dict] = []
    for d in docs_raw:
        gname = d.get("groupName") or "—"
        mand = str(d.get("ismandatory") or "0") == "1"
        val = int(d.get("validated") or 0) == 1
        total += 1
        if val:
            validados += 1
        g = grupos.setdefault(gname, {"proponente": gname, "documentos": []})
        g["documentos"].append({
            "documento": d.get("name"),
            "obrigatorio": mand,
            "validado": val,
            "validade": d.get("validity") if d.get("hasExpirationDate") == "1" else None,
        })
        if mand and not val:
            obrigatorios_pendentes.append({"proponente": gname, "documento": d.get("name")})
    return {
        "total": total,
        "validados": validados,
        "por_proponente": list(grupos.values()),
        "obrigatorios_pendentes": obrigatorios_pendentes,
    }


def _verificacoes(proponentes: list[dict], docs: dict) -> list[dict]:
    """Verificações objetivas (determinísticas), independentes do modelo."""
    v: list[dict] = []
    # documentos obrigatórios
    if docs["obrigatorios_pendentes"]:
        det = "; ".join(f"{o['proponente']}: {o['documento']}" for o in docs["obrigatorios_pendentes"][:12])
        v.append({"estado": "alerta", "titulo": "Documentos obrigatórios por validar",
                  "detalhe": det})
    else:
        v.append({"estado": "ok", "titulo": "Documentos obrigatórios",
                  "detalhe": "Todos os documentos obrigatórios estão validados."})
    # CC / consentimento / rendimento por proponente
    for p in proponentes:
        nome = p["nome"]
        if p["cc_expirado"]:
            v.append({"estado": "alerta", "titulo": "Documento de identificação fora de validade",
                      "detalhe": f"{nome}: CC/validade {p['cc_validade']}."})
        if not p["consentimento_rgpd"]:
            v.append({"estado": "alerta", "titulo": "Consentimento RGPD em falta",
                      "detalhe": f"{nome} sem consentimento RGPD autorizado."})
        if not p["rendimento_mensal"]:
            v.append({"estado": "info", "titulo": "Rendimento não preenchido",
                      "detalhe": f"{nome} tem rendimento mensal a 0 no CRM — impede o cruzamento rendimento/profissão."})
    return v


def _sinais_llm(processo: dict, proponentes: list[dict], docs: dict) -> list[dict]:
    """Sinais de alerta fundamentados no catálogo dos manuais (verifica/)."""
    if not settings.ANTHROPIC_API_KEY:
        return []
    dados = {
        "processo": processo,
        "proponentes": proponentes,
        "documentos": {
            "validados": docs["validados"], "total": docs["total"],
            "por_proponente": docs["por_proponente"],
        },
    }
    system = (
        "És um analista de prevenção de fraude documental de um intermediário de "
        "crédito português (DS Crédito). Analisas UM processo de crédito e "
        "assinalas sinais de alerta de possível falsificação de documentos.\n\n"
        "REGRA ABSOLUTA: a tua ÚNICA base de análise é o catálogo de sinais de "
        "alerta a seguir (extraído dos manuais internos da DS). Não inventes "
        "critérios fora deste catálogo.\n\n"
        + catalogo_para_prompt() +
        "\n\nINSTRUÇÕES:\n"
        "- Recebes os dados ESTRUTURADOS do processo (proponentes + checklist de "
        "documentos). NÃO tens acesso ao conteúdo dos ficheiros.\n"
        "- Para sinais [estrutural] que os dados confirmem, assinala com "
        "verificacao='confirmado_dados' e cita a evidência concreta (nomes, datas, "
        "idades, valores).\n"
        "- Para sinais [conteúdo], se o processo tem documentos desse tipo, "
        "assinala-os como verificacao='a_verificar_no_ficheiro' (recomendação de "
        "inspeção), NUNCA como facto confirmado.\n"
        "- Não gerar falsos positivos: rendimento a 0 é falta de dados, não fraude. "
        "Idades e antiguidades só são sinal se implausíveis.\n"
        "- Responde APENAS com JSON válido, sem texto à volta, no formato:\n"
        '{"sinais": [{"id": "<id do catálogo>", "categoria": "...", '
        '"severidade": "alto|medio|baixo", "titulo": "...", "evidencia": "...", '
        '"verificacao": "confirmado_dados|a_verificar_no_ficheiro"}]}'
    )
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=settings.CHAT_MODEL,
        max_tokens=2000,
        temperature=0,
        system=system,
        messages=[{"role": "user",
                   "content": f"<dados_processo>\n{json.dumps(dados, ensure_ascii=False, default=str)}\n</dados_processo>"}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    valid_ids = {s["id"] for s in SINAIS_ALERTA}
    sinais = []
    for s in data.get("sinais", []):
        base = next((x for x in SINAIS_ALERTA if x["id"] == s.get("id")), None)
        sinais.append({
            "id": s.get("id"),
            "categoria": s.get("categoria") or (base or {}).get("categoria"),
            "severidade": s.get("severidade") or "baixo",
            "titulo": s.get("titulo"),
            "evidencia": s.get("evidencia"),
            "verificacao": s.get("verificacao") or "a_verificar_no_ficheiro",
            "base_manual": (base or {}).get("descricao"),
            "no_catalogo": s.get("id") in valid_ids,
        })
    # sinais fora do catálogo são descartados (regra absoluta)
    return [s for s in sinais if s["no_catalogo"]]


@router.get("/{referencia}")
def analisar(referencia: str, request: Request):
    referencia = referencia.strip()
    sb = supabase()
    scope = user_scope(request)
    q = apply_scope(
        sb.table("processos_real").select(
            "crm_id, reference, customer_name, manager_name, state_name, type_name, "
            "financing_amount, financing_amount_finished, created_on_crm, updated_on_crm, "
            "source_account, source_accounts"
        ),
        scope,
    ).eq("reference", referencia).limit(1)
    rows = q.execute().data or []
    if not rows:
        raise HTTPException(404, f"Processo {referencia} não encontrado nesta loja (ou fora do seu âmbito de acesso).")
    row = rows[0]
    pid = row["crm_id"]

    acct = _pick_account(row.get("source_accounts") or ([row["source_account"]] if row.get("source_account") else []))

    from integrations.ds_crm.client import CredidekClient
    try:
        client = CredidekClient(email=acct.crm_email, password=acct.crm_password)
        prop_raw = client.get_proponents(pid).get("creditprocessproponents") or []
        docs_raw = client.get_documents(pid).get("documentsProponents") or []
    except Exception as e:  # login CRM falhou / processo inacessível
        raise HTTPException(502, f"Não foi possível ler o processo no CRM: {type(e).__name__}")

    today = datetime.now(timezone.utc).date()
    proponentes = _proponentes_factos(prop_raw, today)
    docs = _documentos_factos(docs_raw)

    processo = {
        "referencia": row["reference"],
        "tipo": row.get("type_name"),
        "estado": row.get("state_name"),
        "cliente": row.get("customer_name"),
        "gestor": row.get("manager_name"),
        "valor_eur": row.get("financing_amount_finished") or row.get("financing_amount"),
        "criado_em": row.get("created_on_crm"),
        "atualizado_em": row.get("updated_on_crm"),
        "conta_crm": acct.username,
    }

    verificacoes = _verificacoes(proponentes, docs)
    sinais = _sinais_llm(processo, proponentes, docs)

    return {
        "referencia": row["reference"],
        "processo": processo,
        "ambito": scope_label(request),
        "proponentes": proponentes,
        "documentos": {
            "validados": docs["validados"],
            "total": docs["total"],
            "obrigatorios_pendentes": docs["obrigatorios_pendentes"],
            "por_proponente": docs["por_proponente"],
        },
        "verificacoes": verificacoes,
        "sinais_alerta": sinais,
        "nota_metodologia": (
            "Análise estrutural (Fase 1): cruzamento dos dados do CRM com o catálogo "
            "de sinais de alerta dos manuais internos. Os sinais marcados como 'a "
            "verificar no documento' exigem inspeção do conteúdo do ficheiro. " + METODO
        ),
        "fonte": FONTE,
        "as_of": today.isoformat(),
    }
