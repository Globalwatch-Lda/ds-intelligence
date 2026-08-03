"""Documentos necessários por tipo de crédito — para o email de boas-vindas.

FONTE: as checklists reais do CrediDesk. Cada processo traz em
`documentsProponents` (GET /creditprocesses/documents/list/{id}) a lista de
documentos que a DS pede àquele proponente, com `ismandatory` e o
`creditProcessTypeId` do produto. Este catálogo foi derivado a 3 Ago 2026 de
4 processos por tipo (10 tipos, agência 839) e usa a redacção do próprio CRM —
o cliente recebe os mesmos nomes que depois vê na plataforma.

Só entram os **obrigatórios** (decisão do cliente, 3 Ago 2026): a lista tem de ser
curta e accionável. A obrigatoriedade é configurável processo a processo no CRM,
por isso o que está aqui é o denominador comum observado, não uma regra do banco.

Uma lead ainda não é um processo — não há checklist no CRM para ela. Casamos pelo
tipo de crédito da lead (`type_full_name`, com `type_name` como recurso), e quando
o produto não é reconhecido usamos o conjunto BASE, que é a intersecção dos tipos
de crédito a particulares.

Ao mudar a checklist no CRM, voltar a derivar este ficheiro (scripts ad-hoc em
integrations/ds_crm) em vez de o editar à mão a partir da memória de alguém.
"""
from __future__ import annotations

# Conjunto comum aos créditos a particulares — usado quando o produto da lead não
# corresponde a nenhuma chave conhecida.
BASE: list[str] = [
    "Documento de Identificação",
    "Mapa de Responsabilidades",
    "Recibos de Vencimento (últimos 3 meses)",
    "Extratos bancários (últimos 3 meses)",
    "Nota de Liquidação de IRS do ano anterior",
    "Declaração de IRS",
]

# type_full_name (CRM) -> documentos obrigatórios
POR_TIPO: dict[str, list[str]] = {
    "Crédito Habitação - Aquisição": [
        "Documento de Identificação",
        "Extratos bancários (últimos 3 meses)",
        "Mapa de Responsabilidades",
        "Recibos de Vencimento (últimos 3 meses)",
        "Nota de Liquidação de IRS do ano anterior",
        "Declaração de IRS",
    ],
    "Crédito Habitação - Construção": [
        "Documento de Identificação",
        "Mapa de Responsabilidades",
        "Recibos de Vencimento (últimos 3 meses)",
        "Nota de Liquidação de IRS do ano anterior",
        "Declaração de IRS",
    ],
    "Transferência de Crédito": [
        "Documento de Identificação",
        "Mapa de Responsabilidades",
        "Recibos de Vencimento (últimos 3 meses)",
        "Nota de Liquidação de IRS do ano anterior",
        "Declaração de IRS",
    ],
    "Crédito Hipotecário": [
        "Documento de Identificação",
        "Mapa de Responsabilidades",
        "Recibos de Vencimento (últimos 3 meses)",
        "Nota de Liquidação de IRS do ano anterior",
        "Declaração de IRS",
    ],
    "Crédito Obras": [
        "Documento de Identificação",
        "Mapa de Responsabilidades",
        "Recibos de Vencimento (últimos 3 meses)",
        "Nota de Liquidação de IRS do ano anterior",
        "Declaração de IRS",
        "Número de Contribuinte",
    ],
    "Crédito Consumo": [
        "Documento de Identificação",
        "Extratos bancários (últimos 3 meses)",
        "Mapa de Responsabilidades",
        "Recibos de Vencimento (últimos 3 meses)",
        "Nota de Liquidação de IRS do ano anterior",
        "Declaração de IRS",
    ],
    "Crédito Consolidado": [
        # No CRM só estes dois vêm marcados como obrigatórios neste produto; os
        # restantes (mapa de responsabilidades, recibos, extratos) aparecem como
        # opcionais e são pedidos caso a caso.
        "Documento de Identificação",
        "Declaração de IRS",
    ],
    "Crédito Auto": [
        "Documento de Identificação",
        "Recibos de Vencimento (últimos 3 meses)",
        "Extratos bancários (últimos 3 meses)",
    ],
    # Produtos a empresas — checklist completamente diferente (contabilidade).
    "Leasing Imobiliário - Aquisição": [
        "Último Balancete",
        "Última Declaração de IRC",
        "Demonstração de resultados (I.E.S.)",
        "Código da Certidão Permanente",
        "Certidão do Registo Comercial",
    ],
    "Leasing - Outros": [
        "Último Balancete",
        "Última Declaração de IRC",
        "Demonstração de resultados (I.E.S.)",
        "Extratos bancários da empresa (últimos 3 meses)",
        "Código da Certidão Permanente",
        "Certidão do Registo Comercial",
    ],
}

# Recurso quando a lead só tem o nome curto do produto (type_name).
POR_NOME_CURTO: dict[str, str] = {
    "Aquisição": "Crédito Habitação - Aquisição",
    "Construção": "Crédito Habitação - Construção",
    "Transferência de Crédito": "Transferência de Crédito",
    "Hipotecário": "Crédito Hipotecário",
    "Obras": "Crédito Obras",
    "Consumo": "Crédito Consumo",
    "Consolidado": "Crédito Consolidado",
    "Crédito Auto": "Crédito Auto",
    "Leasing - Outros": "Leasing - Outros",
}


def documentos_para(type_full_name: str | None, type_name: str | None = None) -> tuple[str, list[str]]:
    """(rótulo do produto, documentos obrigatórios). Nunca devolve lista vazia."""
    if type_full_name and type_full_name in POR_TIPO:
        return type_full_name, list(POR_TIPO[type_full_name])
    chave = POR_NOME_CURTO.get((type_name or "").strip())
    if chave:
        return chave, list(POR_TIPO[chave])
    rotulo = type_full_name or type_name or "Crédito"
    return rotulo, list(BASE)
