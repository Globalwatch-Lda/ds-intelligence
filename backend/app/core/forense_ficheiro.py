"""Forense do ficheiro — o documento foi ADULTERADO depois de emitido?

As Fases 1 e 2 olham para o que o documento DIZ (checklist do CRM, e depois o
conteúdo lido por visão). Nenhuma delas responde à pergunta que o cliente pôs:
*este PDF foi editado?* Um recibo de vencimento com o valor trocado no Sejda
continua a ler-se perfeitamente — a fraude não está no texto, está no ficheiro.

Esta camada lê os BYTES do ficheiro (que a Fase 2 já descarrega) e procura os
vestígios que a edição deixa:

  * **Ferramenta de edição** no `/Producer` ou `/Creator` — Sejda, iLovePDF,
    Smallpdf, PDFescape, pdfFiller, Photoshop, GIMP… Um recibo emitido por um
    software de contabilidade não sai do Sejda; se saiu, passou por lá.
  * **Guardas incrementais** — cada vez que um PDF é alterado e re-gravado sem
    linearizar, fica outro `%%EOF`/`startxref` no fim. Mais do que um bloco é
    prova estrutural de que o ficheiro foi modificado depois de criado.
  * **Datas** — `ModDate` posterior a `CreationDate`, ou metadados XMP com
    histórico de edição (`xmpMM:History`, que guarda o nome de cada ferramenta).
  * **Anotações de texto livre / campos de formulário achatados** — a forma mais
    comum de "escrever por cima" de um valor num scan.
  * **Imagens**: EXIF `Software` (Photoshop/GIMP/Snapseed), `DateTime` diferente
    do `DateTimeOriginal`, ou ausência total de EXIF numa suposta fotografia.

Sem dependências novas: o PDF é lido por varrimento dos bytes e o EXIF do JPEG
por leitura dos marcadores APP1. Uma biblioteca daria mais profundidade, mas
estes sinais são os de maior valor por byte lido e não podem falhar por causa de
um pacote em falta na box.

NADA aqui prova fraude — prova EDIÇÃO. Um extrato exportado de um banco pode ter
sido re-gravado por uma ferramenta online só para juntar páginas. O output diz o
que se observou e a que nível de suspeita corresponde; a decisão é humana.
"""
from __future__ import annotations

import re
from datetime import datetime

# Ferramentas de EDIÇÃO/manipulação. Distintas dos geradores legítimos (motores
# de relatório, drivers de impressão) — encontrar uma destas num documento que se
# apresenta como emitido por terceiros é o sinal forte.
EDITORES = {
    "sejda": "Sejda (editor de PDF online)",
    "ilovepdf": "iLovePDF (editor online)",
    "smallpdf": "Smallpdf (editor online)",
    "pdfescape": "PDFescape (editor online)",
    "pdffiller": "pdfFiller (editor online)",
    "dochub": "DocHub (editor online)",
    "xodo": "Xodo (editor de PDF)",
    "pdf24": "PDF24 (editor)",
    "foxit": "Foxit PhantomPDF/PDF Editor",
    "nitro": "Nitro Pro (editor)",
    "pdfelement": "Wondershare PDFelement (editor)",
    "pdf-xchange": "PDF-XChange Editor",
    "pdfsam": "PDFsam (divisão/junção)",
    "soda pdf": "Soda PDF (editor)",
    "photoshop": "Adobe Photoshop (edição de imagem)",
    "gimp": "GIMP (edição de imagem)",
    "canva": "Canva (design gráfico)",
    "inkscape": "Inkscape (edição vetorial)",
    "paint.net": "Paint.NET (edição de imagem)",
    "snapseed": "Snapseed (edição de fotografia)",
    "picsart": "PicsArt (edição de fotografia)",
    "acrobat": "Adobe Acrobat (edição de PDF)",
}

# Geradores comuns e inócuos — anotados para o relatório não os apresentar como
# achado quando são apenas o "como foi impresso".
GERADORES_COMUNS = (
    "microsoft", "word", "excel", "libreoffice", "openoffice", "chrome", "chromium",
    "safari", "firefox", "quartz", "skia", "wkhtmltopdf", "weasyprint", "itext",
    "jasper", "crystal", "reportlab", "fpdf", "tcpdf", "dompdf", "ghostscript",
    "pdflatex", "xelatex", "scanner", "canon", "epson", "hp ", "xerox", "ricoh",
)


def _texto_bytes(b: bytes, limite: int = 4_000_000) -> str:
    """Bytes → texto latin-1 para varrer com regex. Cortado: os metadados vivem
    no início e no fim, e um PDF de 30 MB não precisa de ser todo convertido."""
    if len(b) <= limite:
        return b.decode("latin-1", errors="replace")
    return (b[: limite // 2] + b[-limite // 2:]).decode("latin-1", errors="replace")


def _data_pdf(valor: str | None) -> datetime | None:
    """`D:20260731143000+01'00'` → datetime (sem fuso; só se compara entre si)."""
    if not valor:
        return None
    m = re.match(r"D?:?(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?", valor.strip())
    if not m:
        return None
    p = [int(x) if x else 0 for x in m.groups()]
    try:
        return datetime(p[0], p[1] or 1, p[2] or 1, p[3], p[4], p[5])
    except ValueError:
        return None


def _sinal(sid: str, titulo: str, detalhe: str, severidade: str) -> dict:
    return {
        "id": sid,
        "categoria": "Integridade do ficheiro",
        "titulo": titulo,
        "detalhe": detalhe,
        "severidade": severidade,
        "origem": "forense",
    }


def _ferramenta(valor: str) -> tuple[str, str] | None:
    """(chave, rótulo) do editor reconhecido no texto, se houver."""
    baixo = (valor or "").lower()
    for chave, rotulo in EDITORES.items():
        if chave in baixo:
            return chave, rotulo
    return None


def analisar_pdf(dados: bytes, nome: str) -> tuple[list[dict], dict]:
    """(sinais, factos) sobre a integridade de um PDF."""
    sinais: list[dict] = []
    txt = _texto_bytes(dados)
    factos: dict = {"tipo": "pdf"}

    def _literal_balanceado(inicio: int) -> str | None:
        """Lê `(…)` a partir de `inicio` respeitando parênteses aninhados e escapes.

        Ingénuo, um `[^()]*` falha logo no caso mais importante que há: o produtor
        do Sejda é literalmente «Sejda 5.2 (www.sejda.com)» — com parênteses lá
        dentro — e a leitura devolvia nada, deixando passar o sinal mais forte.
        """
        nivel, i, out = 0, inicio, []
        while i < len(txt) and i - inicio < 2000:
            ch = txt[i]
            if ch == "\\":
                out.append(txt[i + 1: i + 2])
                i += 2
                continue
            if ch == "(":
                nivel += 1
                if nivel == 1:
                    i += 1
                    continue
            elif ch == ")":
                nivel -= 1
                if nivel == 0:
                    return "".join(out).strip()
            out.append(ch)
            i += 1
        return None

    def _meta(campo: str) -> str | None:
        m = re.search(rf"/{campo}\s*\(", txt)
        if m:
            return _literal_balanceado(m.end() - 1)
        # Também aparece em hexadecimal (<FEFF…>) em ficheiros com Unicode.
        m = re.search(rf"/{campo}\s*<([0-9A-Fa-f]+)>", txt)
        if m:
            try:
                bruto = bytes.fromhex(m.group(1))
                return bruto.decode("utf-16-be" if bruto[:2] == b"\xfe\xff" else "latin-1", "replace").strip("\x00")
            except ValueError:
                return None
        return None

    producer, creator = _meta("Producer"), _meta("Creator")
    factos["producer"], factos["creator"] = producer, creator

    for rotulo_campo, valor in (("Producer", producer), ("Creator", creator)):
        achado = _ferramenta(valor or "")
        if achado:
            sinais.append(_sinal(
                "fich_editor",
                f"Ficheiro produzido/alterado por {achado[1]}",
                f"O campo /{rotulo_campo} do PDF diz «{valor}». Documentos emitidos por bancos, "
                "entidades patronais ou pela AT saem do software dessas entidades — a passagem "
                "por um editor indica que o ficheiro foi manipulado depois de emitido. "
                "Confirmar com o emitente ou pedir o original.",
                "alto",
            ))
            break

    # Software de edição referido no histórico XMP, mesmo que o /Producer esteja limpo.
    for agente in set(re.findall(r"stEvt:softwareAgent=\"([^\"]+)\"", txt)) | set(
        re.findall(r"<stEvt:softwareAgent>([^<]+)</stEvt:softwareAgent>", txt)
    ):
        achado = _ferramenta(agente)
        if achado:
            sinais.append(_sinal(
                "fich_xmp_historico",
                f"Histórico do ficheiro regista edição em {achado[1]}",
                f"Os metadados XMP guardam a cadeia de edição do documento e incluem «{agente}». "
                "Este histórico sobrevive mesmo quando o produtor é reescrito.",
                "alto",
            ))
            break

    # Guardas incrementais: cada alteração re-gravada deixa outro %%EOF/startxref.
    eofs = txt.count("%%EOF")
    startxrefs = txt.count("startxref")
    factos["guardas"] = eofs
    # Uma assinatura digital é gravada SEMPRE como guarda incremental — é assim que
    # o formato preserva o que foi assinado. Sem esta distinção, todo o contrato
    # assinado aparecia como "alterado depois de criado" (visto num contrato real
    # do CRM no primeiro teste desta camada).
    assinado = "/ByteRange" in txt or "adbe.pkcs7" in txt or "/Type/Sig" in txt or "/Type /Sig" in txt
    factos["assinado_digitalmente"] = assinado
    if eofs > 1 and startxrefs > 1:
        if assinado:
            sinais.append(_sinal(
                "fich_guardas_incrementais",
                f"Ficheiro com {eofs} gravações — tem assinatura digital",
                f"O PDF foi gravado {eofs} vezes, o que é o comportamento NORMAL de um documento "
                "assinado digitalmente (a assinatura é acrescentada sem reescrever o original). "
                "Só é preocupante se houver gravações a mais do que assinaturas — nesse caso o "
                "documento foi alterado depois de assinado e a assinatura fica inválida. "
                "Confirmar a validade da assinatura no leitor de PDF.",
                "baixo",
            ))
        else:
            sinais.append(_sinal(
                "fich_guardas_incrementais",
                f"Ficheiro guardado {eofs} vezes (alterado depois de criado)",
                f"O PDF tem {eofs} marcas de fim de ficheiro e {startxrefs} tabelas de referências: "
                "sinal estrutural de que foi aberto, alterado e re-gravado pelo menos "
                f"{eofs - 1} vez(es) após a emissão original, sem assinatura digital que o "
                "justifique. Suspeito num recibo, extrato ou declaração.",
                "medio" if eofs == 2 else "alto",
            ))

    criacao, modificacao = _data_pdf(_meta("CreationDate")), _data_pdf(_meta("ModDate"))
    factos["criado_em"] = criacao.isoformat() if criacao else None
    factos["modificado_em"] = modificacao.isoformat() if modificacao else None
    if criacao and modificacao and modificacao > criacao:
        delta = modificacao - criacao
        # Limiar de um dia: minutos ou horas de diferença são a própria gravação
        # (impressão, junção de páginas) e enchiam o relatório de ruído.
        if delta.total_seconds() > 86400:
            sinais.append(_sinal(
                "fich_modificado_depois",
                "Modificado depois de criado",
                f"Criado em {criacao:%d/%m/%Y %H:%M} e modificado em {modificacao:%d/%m/%Y %H:%M} "
                f"({delta.days} dia(s) depois). Num documento emitido por terceiros, a data de "
                "modificação devia coincidir com a de emissão.",
                "medio",
            ))

    # Texto escrito por cima: anotações de texto livre ou campos de formulário.
    if "/FreeText" in txt or "/Widget" in txt:
        sinais.append(_sinal(
            "fich_anotacoes",
            "Tem texto sobreposto (anotações ou campos de formulário)",
            "O ficheiro contém anotações de texto livre ou campos de formulário — a forma mais "
            "comum de escrever por cima de valores num documento digitalizado. Verificar se os "
            "montantes visíveis fazem parte do documento original ou foram acrescentados.",
            "medio",
        ))

    if not producer and not creator:
        sinais.append(_sinal(
            "fich_sem_metadados",
            "Ficheiro sem metadados de origem",
            "O PDF não declara produtor nem criador. Documentos emitidos por sistemas "
            "profissionais identificam-se; a ausência total é típica de ficheiros passados por "
            "ferramentas online que limpam os metadados.",
            "baixo",
        ))
    elif producer or creator:
        gerador = f"{producer or ''} {creator or ''}".lower()
        if not any(g in gerador for g in GERADORES_COMUNS) and not any(
            s["id"] in ("fich_editor", "fich_xmp_historico") for s in sinais
        ):
            factos["produtor_desconhecido"] = True

    return sinais, factos


# Marcadores EXIF relevantes (JPEG): Software, DateTime, DateTimeOriginal.
_EXIF_TAGS = {0x0131: "software", 0x0132: "data_ficheiro", 0x9003: "data_original"}


def _exif_jpeg(dados: bytes) -> dict:
    """EXIF mínimo por leitura do segmento APP1. Devolve {} se não houver."""
    idx = dados.find(b"Exif\x00\x00")
    if idx < 0:
        return {}
    base = idx + 6
    corpo = dados[base: base + 65536]
    if len(corpo) < 8:
        return {}
    little = corpo[:2] == b"II"
    ordem = "little" if little else "big"

    def _int(pos: int, tam: int) -> int:
        return int.from_bytes(corpo[pos: pos + tam], ordem)

    try:
        ifd = _int(4, 4)
        n = _int(ifd, 2)
        out: dict = {}
        for i in range(min(n, 200)):
            e = ifd + 2 + i * 12
            tag, tipo, cont = _int(e, 2), _int(e + 2, 2), _int(e + 4, 4)
            if tag not in _EXIF_TAGS or tipo != 2:  # 2 = ASCII
                continue
            off = _int(e + 8, 4) if cont > 4 else e + 8
            valor = corpo[off: off + cont].split(b"\x00")[0].decode("latin-1", "replace").strip()
            if valor:
                out[_EXIF_TAGS[tag]] = valor
        return out
    except Exception:
        return {}


def analisar_imagem(dados: bytes, nome: str) -> tuple[list[dict], dict]:
    """(sinais, factos) sobre a integridade de uma imagem."""
    sinais: list[dict] = []
    exif = _exif_jpeg(dados) if dados[:2] == b"\xff\xd8" else {}
    factos: dict = {"tipo": "imagem", **exif}

    software = exif.get("software")
    achado = _ferramenta(software or "")
    if achado:
        sinais.append(_sinal(
            "fich_editor",
            f"Imagem editada em {achado[1]}",
            f"Os metadados EXIF registam «{software}» como último software a gravar o ficheiro. "
            "Uma fotografia ou digitalização de um documento não passa por um editor de imagem "
            "sem intenção — verificar valores, datas e assinaturas com o emitente.",
            "alto",
        ))

    d_orig, d_fich = exif.get("data_original"), exif.get("data_ficheiro")
    if d_orig and d_fich and d_orig != d_fich:
        sinais.append(_sinal(
            "fich_modificado_depois",
            "Data de gravação diferente da data da fotografia",
            f"EXIF: fotografada a {d_orig}, gravada a {d_fich}. A diferença indica que o "
            "ficheiro foi reprocessado depois de captado.",
            "medio",
        ))

    if dados[:2] == b"\xff\xd8" and not exif:
        sinais.append(_sinal(
            "fich_sem_metadados",
            "Fotografia sem metadados EXIF",
            "A imagem não tem EXIF nenhum. Fotografias de telemóvel e digitalizações trazem-no; "
            "a ausência é normal em capturas de ecrã e em imagens exportadas de editores ou "
            "reenviadas por aplicações de mensagens.",
            "baixo",
        ))

    return sinais, factos


def analisar(dados: bytes, nome: str, media_type: str | None) -> tuple[list[dict], dict]:
    """Ponto de entrada: escolhe o analisador pelo tipo. Nunca levanta — um erro
    aqui não pode derrubar a Fase 2, que é a análise principal."""
    try:
        if (media_type or "").startswith("application/pdf") or dados[:5] == b"%PDF-":
            return analisar_pdf(dados, nome)
        if (media_type or "").startswith("image/"):
            return analisar_imagem(dados, nome)
    except Exception as e:  # pragma: no cover - defesa
        return [], {"erro": f"{type(e).__name__}: {e}"[:200]}
    return [], {}
