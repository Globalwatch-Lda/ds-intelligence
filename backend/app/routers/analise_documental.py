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

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

import anthropic
from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..core.analise_documental_kb import (
    FONTE, METODO, SINAIS_ALERTA, catalogo_para_prompt, catalogo_conteudo_para_prompt,
)
from ..core.scope import user_scope, apply_scope, scope_label
from ..db import supabase

router = APIRouter()

_PROCESSO_COLS = (
    "crm_id, reference, customer_name, manager_name, state_name, type_name, "
    "financing_amount, financing_amount_finished, created_on_crm, updated_on_crm, "
    "source_account, source_accounts"
)


def _limites() -> tuple[int, float]:
    """Limites da Fase 2 (nº ficheiros, MB/ficheiro): loja_config > env default.
    Editáveis na tab Loja das Configurações."""
    n = settings.ANALISE_MAX_FICHEIROS
    mb = settings.ANALISE_MAX_FILE_MB
    try:
        row = (supabase().table("loja_config")
               .select("analise_max_ficheiros, analise_max_file_mb")
               .eq("id", 1).limit(1).execute().data or [{}])[0]
        n = int(row.get("analise_max_ficheiros") or n)
        mb = float(row.get("analise_max_file_mb") or mb)
    except Exception:
        pass
    return n, mb


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


def _resolve(referencia: str, request: Request) -> tuple[dict, object]:
    """Resolve a referência no mirror DESTA loja (com scope RBAC) e escolhe a
    conta CRM DESTA loja. 404 se a referência não existe/está fora do âmbito —
    é isto que garante o isolamento entre lojas."""
    sb = supabase()
    scope = user_scope(request)
    q = apply_scope(
        sb.table("processos_real").select(_PROCESSO_COLS), scope
    ).eq("reference", referencia.strip()).limit(1)
    rows = q.execute().data or []
    if not rows:
        raise HTTPException(404, f"Processo {referencia} não encontrado nesta loja (ou fora do seu âmbito de acesso).")
    row = rows[0]
    sa = row.get("source_accounts") or ([row["source_account"]] if row.get("source_account") else [])
    return row, _pick_account(sa)


@router.get("/{referencia}")
def analisar(referencia: str, request: Request):
    row, acct = _resolve(referencia, request)
    pid = row["crm_id"]

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


# ============================ FASE 2 — conteúdo dos ficheiros ============================

# Tipos de ficheiro que conseguimos enviar ao modelo com visão.
_MEDIA = {
    "pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "gif": "image/gif", "webp": "image/webp",
}


def _media_type(file_name: str | None) -> str | None:
    ext = (file_name or "").rsplit(".", 1)[-1].lower() if "." in (file_name or "") else ""
    return _MEDIA.get(ext)


def _vision_sinais(doc_nome: str, proponente: str, file_name: str, media_type: str, b64: str,
                   contexto: str = "") -> tuple[list[dict], dict]:
    """Lê UM ficheiro com o modelo de visão e devolve (sinais, factos):
    - sinais: alertas de conteúdo fundamentados no catálogo (JSON estrito);
    - factos: resumo estruturado do ficheiro (entidade, período, valores, datas,
      NIB…) para a passagem final de cruzamento entre documentos."""
    if not settings.ANTHROPIC_API_KEY:
        return [], {}
    hoje = datetime.now(timezone.utc).date().isoformat()
    system = (
        "És um analista de prevenção de fraude documental de um intermediário de "
        "crédito português (DS Crédito). Analisas UM ficheiro carregado num "
        "processo de crédito e assinalas sinais de alerta de possível falsificação.\n\n"
        "REGRA ABSOLUTA: a tua ÚNICA base de análise é o catálogo de sinais de "
        "conteúdo a seguir (extraído dos manuais internos da DS). Não inventes "
        "critérios fora do catálogo.\n\n"
        + catalogo_conteudo_para_prompt() +
        "\n\nINSTRUÇÕES:\n"
        "- Analisa aritmética (somatórios de recibos/extratos), coerência de datas, "
        "tipos de letra, campos obrigatórios (NIF/NIB/data), carimbos e assinaturas, "
        "QR codes, descontos de Segurança Social, e incoerências internas.\n"
        f"- DATAS: a data de referência (hoje) é {hoje}. Em documentos portugueses o "
        "formato é dia-mês-ano (dd-mm-aaaa) — lê com cuidado antes de comparar. Só "
        "assinala incoerência de datas quando a comparação for inequívoca (ex.: data de "
        "emissão anterior ao período a que o documento respeita). Recibos, extratos e "
        "declarações de meses ou anos anteriores são NORMAIS num processo de crédito — "
        "a antiguidade do documento, por si só, NUNCA é sinal de alerta.\n"
        "- Verifica sempre: assinaturas/carimbos onde são exigidos (declarações de "
        "entidade patronal têm de estar assinadas); dados completos do trabalhador nos "
        "recibos (morada, NIF, n.º de funcionário, categoria, admissão); incidência de "
        "SS e IRS sobre complementos regulares como o IHT (é obrigatória); e nitidez "
        "homogénea da página (texto nítido sobre fundo esbatido = indício de montagem).\n"
        "- Só assinala o que EFETIVAMENTE observas no ficheiro. Se não há sinais, "
        "devolve lista vazia. Não gerar falsos positivos.\n"
        "- Extrai também os FACTOS-CHAVE do documento (para cruzamento posterior "
        "entre documentos): não é um alerta, é o que o documento diz. Preenche só o "
        "que existir; usa null quando não aplicável.\n"
        "- Responde APENAS com JSON válido, sem texto à volta:\n"
        '{"sinais": [{"id": "<id do catálogo>", "categoria": "...", '
        '"severidade": "alto|medio|baixo", "titulo": "...", "evidencia": "<o que viste, concreto>"}], '
        '"factos": {"tipo": "<recibo|extrato|irs|declaracao|contrato|id|outro>", '
        '"entidade": "<empregador/banco/emissor>", "titular": "<nome no documento>", '
        '"periodo": "<mês/ano ou intervalo a que respeita>", "data_emissao": "<dd-mm-aaaa ou null>", '
        '"bruto": <valor ou null>, "liquido": <valor ou null>, "iht": <valor ou null>, '
        '"desconto_ss": <valor ou null>, "retencao_irs": <valor ou null>, '
        '"nib": "<IBAN/NIB ou null>", "anual_bruto": <valor ou null>, '
        '"observacoes": "<uma frase com o que for relevante para cruzar com outros documentos>"}}'
    )
    block = ({"type": "document", "source": {"type": "base64", "media_type": media_type, "data": b64}}
             if media_type == "application/pdf"
             else {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}})
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=settings.ANALISE_VISION_MODEL,
        max_tokens=1500,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": [
            block,
            {"type": "text", "text":
                f"Ficheiro: {file_name}\nTipo de documento: {doc_nome}\nProponente/objeto: {proponente}\n"
                + (f"{contexto}\n" if contexto else "")
                + "Analisa este ficheiro e devolve os sinais de conteúdo em JSON."},
        ]}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [], {}
    valid_ids = {s["id"] for s in SINAIS_ALERTA}
    out = []
    for s in data.get("sinais", []):
        if s.get("id") not in valid_ids:
            continue  # regra absoluta: fora do catálogo, descarta
        base = next((x for x in SINAIS_ALERTA if x["id"] == s["id"]), {})
        out.append({
            "id": s["id"], "categoria": s.get("categoria") or base.get("categoria"),
            "severidade": s.get("severidade") or "baixo", "titulo": s.get("titulo"),
            "evidencia": s.get("evidencia"), "verificacao": "confirmado_ficheiro",
            "base_manual": base.get("descricao"),
            "ficheiro": file_name, "documento": doc_nome, "proponente": proponente,
        })
    factos = data.get("factos") or {}
    if isinstance(factos, dict):
        factos = {**factos, "ficheiro": file_name, "documento": doc_nome, "proponente": proponente}
    else:
        factos = {}
    return out, factos


def _cruzamento_sinais(factos: list[dict], contexto: str) -> list[dict]:
    """Passagem final: recebe os FACTOS extraídos de TODOS os ficheiros e procura
    incoerências ENTRE documentos que uma leitura ficheiro-a-ficheiro não apanha
    (ex.: recibo com IHT que não consta no total anual do IRS; declarações patronais
    idênticas; NIB de vencimento diferente entre recibo e extrato; bruto mensal ×14
    incompatível com o anual do IRS). Só devolve sinais do catálogo de conteúdo."""
    if not settings.ANTHROPIC_API_KEY or len(factos) < 2:
        return []
    hoje = datetime.now(timezone.utc).date().isoformat()
    system = (
        "És um analista de prevenção de fraude documental da DS Crédito. Recebes os "
        "FACTOS já extraídos de VÁRIOS documentos do MESMO processo de crédito e a tua "
        "tarefa é encontrar INCOERÊNCIAS ENTRE documentos (não dentro de um só).\n\n"
        "REGRA ABSOLUTA: a tua única base é o catálogo de sinais a seguir. Usa "
        "sobretudo: outros_incoerencias (dados que diferem entre documentos), "
        "pt_irs_vs_recibos (anual do IRS ≈ mensal ×14; complementos regulares como o "
        "IHT têm de constar no anual), pt_iht_sem_incidencia, cont_nib_incoerente "
        "(NIB de vencimento diferente entre documentos), cont_datas_nao_usuais, "
        "uk_declaracao_patronal (declarações idênticas entre clientes/empregadores).\n\n"
        + catalogo_conteudo_para_prompt() +
        f"\n\nINSTRUÇÕES:\n- Data de hoje: {hoje}. Datas PT em dd-mm-aaaa. Documentos de "
        "meses/anos anteriores são normais — antiguidade não é alerta.\n"
        "- Compara valores com tolerância razoável (arredondamentos, 14 vs 12 meses, "
        "subsídios). Só assinala quando a incoerência for material e sustentável.\n"
        "- Cada sinal tem de citar concretamente os documentos e valores em conflito.\n"
        "- Se os documentos forem coerentes entre si, devolve lista vazia.\n"
        "- Responde APENAS com JSON válido:\n"
        '{"sinais": [{"id": "<id do catálogo>", "categoria": "...", '
        '"severidade": "alto|medio|baixo", "titulo": "...", '
        '"evidencia": "<documentos e valores em conflito, concreto>"}]}'
    )
    payload = {"contexto_crm": contexto, "documentos": factos}
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=settings.ANALISE_VISION_MODEL,
        max_tokens=1500,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content":
            "FACTOS extraídos dos documentos deste processo (JSON):\n"
            + json.dumps(payload, ensure_ascii=False, default=str)
            + "\n\nDevolve os sinais de incoerência entre documentos em JSON."}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    valid_ids = {s["id"] for s in SINAIS_ALERTA}
    out = []
    for s in data.get("sinais", []):
        if s.get("id") not in valid_ids:
            continue
        base = next((x for x in SINAIS_ALERTA if x["id"] == s["id"]), {})
        out.append({
            "id": s["id"], "categoria": s.get("categoria") or base.get("categoria"),
            "severidade": s.get("severidade") or "medio", "titulo": s.get("titulo"),
            "evidencia": s.get("evidencia"), "verificacao": "cruzamento_documentos",
            "base_manual": base.get("descricao"),
            "ficheiro": "(cruzamento entre documentos)", "documento": "vários", "proponente": "—",
        })
    return out


@router.post("/{referencia}/conteudo")
def analisar_conteudo(referencia: str, request: Request):
    """Fase 2 (a pedido): descarrega os ficheiros do processo e lê o conteúdo com
    o modelo de visão, aplicando as regras de conteúdo do catálogo. Tem custo por
    ficheiro — limitado por ANALISE_MAX_FICHEIROS e ANALISE_MAX_FILE_MB."""
    row, acct = _resolve(referencia, request)
    pid = row["crm_id"]

    from integrations.ds_crm.client import CredidekClient
    try:
        client = CredidekClient(email=acct.crm_email, password=acct.crm_password)
        lst = client.get_documents(pid)
    except Exception as e:
        raise HTTPException(502, f"Não foi possível ler o processo no CRM: {type(e).__name__}")

    # Contexto do CRM para o modelo de visão (best-effort): rendimento mensal
    # declarado por proponente — permite cruzar recibos/IRS com o processo
    # (ex.: total anual do IRS ≈ mensal ×14; IHT mensal refletido no anual).
    try:
        prop_raw = client.get_proponents(pid).get("creditprocessproponents") or []
    except Exception:
        prop_raw = []
    rendimentos = [
        f"{p.get('name') or p.get('customerName')}: {p.get('monthlyIncomeAmount')}€/mês"
        for p in prop_raw if p.get("monthlyIncomeAmount")
    ]
    contexto = ("Rendimento mensal declarado no processo (CRM) — cruza com os valores "
                "do documento: " + "; ".join(rendimentos)) if rendimentos else ""

    # nome legível do tipo de documento (do checklist) + proponente
    checklist = (lst.get("documentsProponents") or []) + (lst.get("documentsRelated") or [])
    tipo_nome = {c.get("documentId"): c.get("name") for c in checklist}
    prop_nome = {}
    for c in checklist:
        pid_prop = c.get("creditProcessProponentId")
        if pid_prop and c.get("groupName"):
            prop_nome[pid_prop] = c["groupName"]

    ficheiros = lst.get("documents") or []
    limite, max_mb = _limites()
    max_bytes = int(max_mb * 1024 * 1024)

    # 1) pré-filtro rápido (metadados) — decide o que se analisa vs ignora
    candidatos, ignorados = [], []
    for f in ficheiros:
        fname = f.get("fileName") or f"ficheiro-{f.get('id')}"
        mt = _media_type(fname)
        if not mt:
            ignorados.append({"ficheiro": fname, "motivo": "formato não legível por visão (ex.: Office/zip)"})
            continue
        if (f.get("fileSize") or 0) > max_bytes:
            ignorados.append({"ficheiro": fname, "motivo": f"ficheiro > {max_mb:g} MB"})
            continue
        if len(candidatos) >= limite:
            ignorados.append({"ficheiro": fname, "motivo": f"limite de {limite} ficheiros atingido"})
            continue
        candidatos.append((f, fname, mt))

    # 2) descarrega + lê cada ficheiro EM PARALELO (I/O-bound: download + visão).
    # Sem paralelismo, N ficheiros em série estouram o timeout do nginx.
    def _processar(item):
        f, fname, mt = item
        doc_nome = tipo_nome.get(f.get("documentId")) or "Documento"
        proponente = prop_nome.get(f.get("creditProcessProponentId")) or (row.get("customer_name") or "—")
        try:
            file_obj = client.get_file(f["id"])
            b64 = (file_obj or {}).get("filebase64")
            if not b64:
                return None, {"ficheiro": fname, "motivo": "sem conteúdo devolvido pelo CRM"}, [], {}
            if len(b64) * 3 // 4 > max_bytes:
                return None, {"ficheiro": fname, "motivo": f"ficheiro > {max_mb:g} MB"}, [], {}
            fsinais, ffactos = _vision_sinais(doc_nome, proponente, fname, mt, b64, contexto)
        except Exception as e:
            return None, {"ficheiro": fname, "motivo": f"erro na análise ({type(e).__name__})"}, [], {}
        return ({"ficheiro": fname, "documento": doc_nome, "proponente": proponente,
                 "n_sinais": len(fsinais)}, None, fsinais, ffactos)

    analisados, sinais, factos_todos = [], [], []
    if candidatos:
        with ThreadPoolExecutor(max_workers=min(5, len(candidatos))) as ex:
            for ok, ign, fsinais, ffactos in ex.map(_processar, candidatos):
                if ok:
                    analisados.append(ok)
                    sinais.extend(fsinais)
                    if ffactos:
                        factos_todos.append(ffactos)
                if ign:
                    ignorados.append(ign)

    # 3) passagem final de cruzamento entre documentos (só se houver ≥2 ficheiros lidos)
    try:
        sinais.extend(_cruzamento_sinais(factos_todos, contexto))
    except Exception:
        pass  # o cruzamento é um extra: nunca deve derrubar a Fase 2

    ordem = {"alto": 0, "medio": 1, "baixo": 2}
    sinais.sort(key=lambda s: ordem.get(s.get("severidade"), 3))

    return {
        "referencia": row["reference"],
        "ambito": scope_label(request),
        "conta_crm": acct.username,
        "total_ficheiros": len(ficheiros),
        "ficheiros_analisados": analisados,
        "ficheiros_ignorados": ignorados,
        "sinais_alerta": sinais,
        "nota_metodologia": (
            "Análise de conteúdo (Fase 2): cada ficheiro legível foi descarregado do "
            "CRM e lido com um modelo de visão, aplicando as regras de conteúdo do "
            "catálogo dos manuais internos. Sinais confirmados na leitura do ficheiro. "
            "Uma passagem final cruza os factos extraídos de todos os documentos para "
            "apanhar incoerências entre eles (ex.: IHT nos recibos que não consta no "
            "total anual do IRS) — sinais marcados como 'cruzamento entre documentos'."
        ),
        "fonte": FONTE,
        "as_of": datetime.now(timezone.utc).date().isoformat(),
    }
