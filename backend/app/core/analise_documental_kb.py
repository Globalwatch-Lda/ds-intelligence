"""Base de conhecimento para a Análise Documental — catálogo de sinais de alerta
de falsificação de documentos.

FONTE (validada com o cliente): os dois manuais da DS Crédito na pasta `verifica/`:
  1. "Manual de Procedimentos de Deteção de Documentos Falsificados" (V1/Fevereiro 2024)
  2. "Formação — Falsificação de Documentos / DSIC" (DRG, 14-08-2024)

Este catálogo é a ÚNICA base de análise: o motor de Análise Documental só assinala
sinais de alerta previstos aqui. Cada sinal indica se é confirmável com os dados
estruturados do CRM (`estrutural`) ou se exige inspeção do conteúdo do ficheiro
(`conteudo`) — estes últimos são apresentados como "a verificar no documento",
nunca afirmados, porque a Fase 1 não descarrega os ficheiros.

Ao atualizar os manuais em verifica/, reveja este catálogo em conformidade.
"""
from __future__ import annotations

FONTE = (
    "Manual de Procedimentos de Deteção de Documentos Falsificados (V1/Fev-2024) "
    "e Formação Falsificação de Documentos DSIC (DRG, 14-08-2024) — pasta verifica/; "
    "complementado com casos reais registados pelas lojas (Loulé, jul-2026)"
)

ENQUADRAMENTO_JURIDICO = (
    "A falsificação de documentos é crime público (art.º 256.º do Código Penal), "
    "punível com pena de prisão até 3 anos ou multa; a tentativa é punível. "
    "Enquanto intermediário de crédito, a DS deve fazer o controlo de 1.º nível: "
    "análise cuidada dos documentos antes de os apresentar à instituição financeira, "
    "e verificação da veracidade em caso de suspeita. A presença de sinais de alerta "
    "NÃO significa fraude — significa que a situação deve ser verificada e monitorizada "
    "com diligência antes da submissão ao banco."
)

# Cada sinal: id, categoria, descrição (do manual), tipo de verificação.
#   tipo = "estrutural"  -> confirmável com dados estruturados do CRM
#   tipo = "conteudo"    -> exige inspeção do conteúdo do ficheiro (Fase 2)
SINAIS_ALERTA: list[dict] = [
    # ---- Formato dos documentos (Manual, secção 1) ----
    {"id": "fmt_logotipo", "categoria": "Formato",
     "descricao": "Faturas, cartas ou documentos empresariais sem o logótipo da empresa.",
     "tipo": "conteudo"},
    {"id": "fmt_tipo_letra", "categoria": "Formato",
     "descricao": "Diferenças visíveis no tipo, dimensão, nitidez ou cor do tipo de letra dentro do mesmo documento (ex.: NIB com letra diferente do resto do recibo).",
     "tipo": "conteudo"},
    {"id": "fmt_numeros_manuscritos", "categoria": "Formato",
     "descricao": "Números apagados ou eliminados e montantes manuscritos.",
     "tipo": "conteudo"},
    {"id": "fmt_carimbos", "categoria": "Formato",
     "descricao": "Limites anormalmente bem definidos de carimbos oficiais ou cores não usuais (indício de impressora).",
     "tipo": "conteudo"},
    {"id": "fmt_assinaturas_identicas", "categoria": "Formato",
     "descricao": "Assinaturas totalmente idênticas (forma e dimensão) em vários documentos — possível falsificação gerada em computador.",
     "tipo": "conteudo"},
    {"id": "fmt_sem_assinatura", "categoria": "Formato",
     "descricao": "Documento que exige assinatura apresentado sem assinatura e/ou carimbo (ex.: declaração de efetividade da entidade patronal por assinar; contrato sem rubricas).",
     "tipo": "conteudo"},
    {"id": "fmt_nitidez_heterogenea", "categoria": "Formato",
     "descricao": "Nitidez heterogénea na mesma página: corpo do texto nítido sobre o resto esbatido ou de baixa resolução (logótipo, cabeçalho, rodapé, carimbo) — indício de texto sobreposto a uma digitalização.",
     "tipo": "conteudo"},

    # ---- Conteúdo dos documentos (Manual, secção 2) ----
    {"id": "cont_erro_calculo", "categoria": "Conteúdo",
     "descricao": "Erro(s) de cálculo numa fatura, recibo ou extrato: totais não coincidentes com a soma das transações (ex.: Start Balance + Money In − Money Out ≠ End Balance; Total Payments ≈ Net Pay ignorando Deductions).",
     "tipo": "conteudo"},
    {"id": "cont_elemento_obrigatorio", "categoria": "Conteúdo",
     "descricao": "Ausência de elemento obrigatório numa fatura/recibo: data, NIF, número da fatura, NIB, departamento.",
     "tipo": "conteudo"},
    {"id": "cont_nib_incoerente", "categoria": "Conteúdo",
     "descricao": "Incoerências no NIB/IBAN: menos dígitos do que o habitual, banco a pagar diferente do banco do NIB, transferência de vencimento a débito e não a crédito.",
     "tipo": "conteudo"},
    {"id": "cont_datas_nao_usuais", "categoria": "Conteúdo",
     "descricao": "Datas, montantes, observações, números de telefone ou cálculos não usuais; período do extrato incoerente com a data de emissão.",
     "tipo": "conteudo"},
    {"id": "cont_recibos_repetidos", "categoria": "Conteúdo",
     "descricao": "Recibos sempre iguais mudando apenas o mês; extratos com o mesmo número de movimentos em meses diferentes.",
     "tipo": "conteudo"},
    {"id": "cont_qr_nif", "categoria": "Conteúdo",
     "descricao": "QR code de fatura aponta para NIF diferente do apresentado no rosto da fatura.",
     "tipo": "conteudo"},

    # ---- Padrões PT residentes (Formação) ----
    {"id": "pt_vencimento_empolado", "categoria": "Padrão PT",
     "descricao": "Vencimentos empolados para o tipo de profissão, ou empolados via ajudas de custo/subsídios; aumento significativo do vencimento face ao IRS do ano anterior.",
     "tipo": "estrutural"},
    {"id": "pt_irs_fora_prazo", "categoria": "Padrão PT",
     "descricao": "Declaração de IRS entregue fora de prazo e normalmente sem IBAN carregado para reembolso.",
     "tipo": "conteudo"},
    {"id": "pt_sem_descontos_ss", "categoria": "Padrão PT",
     "descricao": "Recibo sem descontos para a Segurança Social, ou descontos apenas sobre o vencimento base; IRS sem contribuições para a SS quando declara rendimento mensal relevante.",
     "tipo": "conteudo"},
    {"id": "pt_idade_inicio_trabalho", "categoria": "Padrão PT",
     "descricao": "Início de atividade profissional em idade implausível (ex.: começou a trabalhar aos 14 anos): comparar data de nascimento com data de início na empresa/antiguidade.",
     "tipo": "estrutural"},
    {"id": "pt_cliente_recente", "categoria": "Padrão PT",
     "descricao": "Cliente recente no banco com movimentos que só demonstram o crédito do ordenado e poucos débitos, provocando saldos crescentes mês a mês.",
     "tipo": "conteudo"},
    {"id": "pt_recibo_sem_dados_trabalhador", "categoria": "Padrão PT",
     "descricao": "Recibo de vencimento sem os dados do trabalhador para além do nome: morada, NIF, número de funcionário, categoria profissional ou data de admissão/antiguidade em falta no campo dos dados do trabalhador.",
     "tipo": "conteudo"},
    {"id": "pt_iht_sem_incidencia", "categoria": "Padrão PT",
     "descricao": "IHT (subsídio de isenção de horário de trabalho) ou outro complemento remuneratório regular pago sem incidência de Segurança Social e de retenção de IRS. A incidência é obrigatória — o IHT é remuneração sujeita a SS e a IRS; a sua ausência é sinal forte.",
     "tipo": "conteudo"},
    {"id": "pt_irs_vs_recibos", "categoria": "Padrão PT",
     "descricao": "Rendimento bruto anual da declaração/nota de liquidação de IRS incompatível com o rendimento mensal dos recibos ou com o rendimento declarado no processo (regra prática: anual ≈ mensal ×14). Complementos regulares (ex.: IHT mensal) que não estejam refletidos no total anual do IRS.",
     "tipo": "conteudo"},

    # ---- Padrões UK emigrantes (Formação) ----
    {"id": "uk_profissao_rendimento", "categoria": "Padrão UK",
     "descricao": "Emigrante no Reino Unido (frequentemente com ascendência PALOP) com profissão 'de prestígio' (consultor, engenheiro, enfermeiro, IT) e rendimentos elevados, com extratos de bons saldos e poucos débitos.",
     "tipo": "estrutural"},
    {"id": "uk_credit_report", "categoria": "Padrão UK",
     "descricao": "Incoerências no Credit Report: saldos históricos a 0 ou campos em branco; conta aberta quando o cliente era menor; data de update posterior à data do relatório; saldos do report não coincidem com os extratos.",
     "tipo": "conteudo"},
    {"id": "uk_declaracao_patronal", "categoria": "Padrão UK",
     "descricao": "Declarações de entidade patronal idênticas entre clientes com empregadores diferentes; cartas com tipos de letra do MSWord e erros de escrita; pedidos com origem no mesmo parceiro.",
     "tipo": "conteudo"},
    {"id": "uk_payslip_p60", "categoria": "Padrão UK",
     "descricao": "Payslip com erro no somatório; deductions não refletidas no Net Pay; P60 com dados editados; recibo sem número de empregado; valor a crédito não corresponde à entidade patronal.",
     "tipo": "conteudo"},

    # ---- Outros sinais (Manual, secção 3) ----
    {"id": "outros_atraso_info", "categoria": "Outros",
     "descricao": "Atrasos não usuais no fornecimento de informação ou recusa em apresentar os documentos originais quando solicitados.",
     "tipo": "estrutural"},
    {"id": "outros_incoerencias", "categoria": "Outros",
     "descricao": "Incoerências entre as informações apresentadas nos vários documentos; dados que diferem visualmente de um documento semelhante do mesmo organismo.",
     "tipo": "conteudo"},
    {"id": "outros_documento_expirado", "categoria": "Outros",
     "descricao": "Documento de identificação ou certidão fora de validade.",
     "tipo": "estrutural"},
]

# ---- Integridade do ficheiro (Fase 3, forense) ---------------------------
# Estes sinais NÃO vêm dos manuais da DS: os manuais tratam do documento impresso
# (logótipos, carimbos, aritmética) e são anteriores à facilidade com que hoje se
# edita um PDF no browser. São detetados de forma DETERMINÍSTICA nos bytes do
# ficheiro (app/core/forense_ficheiro.py), não por um modelo, e por isso não
# entram no catálogo enviado ao modelo de visão — entram no relatório final.
#
# Nenhum destes sinais prova falsificação: provam EDIÇÃO. Um extrato pode ter
# passado por uma ferramenta online só para juntar páginas. O que mudam é o ónus:
# perante um recibo saído de um editor de PDF, pede-se o original ao emitente.
FONTE_FORENSE = (
    "Análise forense do ficheiro (metadados PDF/XMP, guardas incrementais, EXIF) — "
    "complemento técnico aos manuais da DS, que cobrem o documento impresso"
)

SINAIS_FICHEIRO: list[dict] = [
    {"id": "fich_editor", "categoria": "Integridade do ficheiro",
     "descricao": "O ficheiro declara ter sido produzido ou alterado por uma ferramenta de edição "
                  "(Sejda, iLovePDF, Smallpdf, pdfFiller, Photoshop, GIMP…). Documentos emitidos "
                  "por bancos, entidades patronais ou pela AT saem do software dessas entidades."},
    {"id": "fich_xmp_historico", "categoria": "Integridade do ficheiro",
     "descricao": "O histórico XMP do ficheiro regista a passagem por um editor, mesmo que o campo "
                  "de produtor tenha sido reescrito."},
    {"id": "fich_guardas_incrementais", "categoria": "Integridade do ficheiro",
     "descricao": "O PDF tem várias marcas de fim de ficheiro: foi aberto, alterado e re-gravado "
                  "depois da emissão original. Normal em assinatura digital ou preenchimento de "
                  "formulário; suspeito num recibo ou extrato."},
    {"id": "fich_modificado_depois", "categoria": "Integridade do ficheiro",
     "descricao": "A data de modificação é posterior à de criação (PDF), ou a data de gravação "
                  "difere da data da fotografia (EXIF)."},
    {"id": "fich_anotacoes", "categoria": "Integridade do ficheiro",
     "descricao": "O ficheiro contém anotações de texto livre ou campos de formulário — a forma "
                  "mais comum de escrever por cima de valores num documento digitalizado."},
    {"id": "fich_sem_metadados", "categoria": "Integridade do ficheiro",
     "descricao": "Ficheiro sem metadados de origem (produtor/criador no PDF, EXIF na fotografia). "
                  "Típico de ficheiros passados por ferramentas online, que os limpam."},
]

# Verificação em fontes externas (Manual/Formação — "Em caso de dúvida").
FONTES_EXTERNAS: list[str] = [
    "Certificados de contribuições fiscais/sociais: confirmar autenticidade junto da AT ou da Segurança Social (Segurança Social Direta).",
    "Extratos bancários: verificar coerência entre saldo, vencimento mensal e volume de negócios/capital declarados.",
    "Balanços: controlo cruzado com bases de dados de fonte aberta sobre volume de negócios e capital.",
    "IRS: solicitar comprovativos de entrega de anos anteriores; confirmar no Portal das Finanças.",
    "Situação laboral: confirmar junto da entidade empregadora.",
    "UK: Home Office share code (immigration status), HMRC personal account, Full Credit Report (Experian/checkmyfile). O P60 é facilmente editável.",
]

METODO = (
    "O melhor método é comparar a suspeita com a realidade: prestar atenção a "
    "logótipos, assinaturas, datas e carimbos, e cruzar a informação entre "
    "documentos. Confirmado o risco, o contacto imediato com as autoridades "
    "policiais é pertinente, recolhendo o máximo de informação sobre o infrator."
)


def catalogo_conteudo_para_prompt() -> str:
    """Só os sinais de CONTEÚDO (Fase 2), para aplicar à leitura do ficheiro."""
    linhas = ["CATÁLOGO DE SINAIS DE ALERTA DE CONTEÚDO (única base de análise permitida):"]
    for s in SINAIS_ALERTA:
        if s["tipo"] == "conteudo":
            linhas.append(f"- ({s['id']}, {s['categoria']}) {s['descricao']}")
    linhas.append(f"\nFONTES EXTERNAS DE VERIFICAÇÃO (para recomendação):")
    linhas += [f"- {f}" for f in FONTES_EXTERNAS]
    return "\n".join(linhas)


def catalogo_para_prompt() -> str:
    """Serializa o catálogo para injetar no prompt do modelo."""
    linhas = [f"ENQUADRAMENTO JURÍDICO:\n{ENQUADRAMENTO_JURIDICO}\n",
              "CATÁLOGO DE SINAIS DE ALERTA (única base de análise permitida):"]
    for s in SINAIS_ALERTA:
        marca = "[estrutural]" if s["tipo"] == "estrutural" else "[conteúdo — a verificar no ficheiro]"
        linhas.append(f"- ({s['id']}, {s['categoria']}) {marca} {s['descricao']}")
    linhas.append("\nFONTES EXTERNAS DE VERIFICAÇÃO:")
    linhas += [f"- {f}" for f in FONTES_EXTERNAS]
    linhas.append(f"\nMÉTODO DE DETEÇÃO:\n{METODO}")
    return "\n".join(linhas)
