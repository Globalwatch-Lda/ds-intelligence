"""Extração best-effort do período de taxa fixa/mista a partir do resumo em
texto livre que o CrediDesk guarda em `contextPartners.html` (o "Resumo da
operação" escrito para os bancos parceiros — nem sempre preenchido, e sem
formato fixo). Não existe nenhum campo estruturado para isto na API do
CrediDesk (confirmado testando o detalhe de +10 processos reais, incluindo
finalizados de 4 bancos diferentes) — é só texto de preferência do cliente,
por vezes um intervalo de anos ("2 a 5 anos"), nunca uma data exata.

Ver worklog / conversa de 14 ago 2026 para o processo real que motivou isto
(P2026080615080422 — "Preferência de tipo de taxa: mista, com período fixo
entre 2 a 5 anos").
"""
from __future__ import annotations

import re
from html import unescape

_TAG_RE = re.compile(r"<[^>]+>")
# "taxa fixa" ou "taxa mista" (com ou sem outras palavras entre "taxa" e o
# tipo, ex. "tipo de taxa: mista"), seguido — na mesma zona de texto — de um
# intervalo de anos ("2 a 5 anos", "3-5 anos") ou um valor único ("5 anos").
_TIPO_RE = re.compile(r"taxa[^.<]{0,40}?\b(fixa|mista)\b", re.IGNORECASE)
_ANOS_RANGE_RE = re.compile(r"(\d{1,2})\s*(?:a|-|até)\s*(\d{1,2})\s*anos", re.IGNORECASE)
_ANOS_SINGLE_RE = re.compile(r"(\d{1,2})\s*anos", re.IGNORECASE)


def _strip_html(html: str) -> str:
    return unescape(_TAG_RE.sub(" ", html))


def extract_taxa_fixa(context_partners_html: str | None) -> dict | None:
    """Devolve {"tipo": "fixa"|"mista", "anos_min": int, "anos_max": int} ou
    None se não encontrar nada com confiança. Best-effort: procura "taxa fixa"
    ou "taxa mista" e, na mesma frase, um período em anos. `anos_min`==`anos_max`
    quando o texto só tem um valor único, não um intervalo.
    """
    if not context_partners_html:
        return None
    text = _strip_html(context_partners_html)

    tipo_match = _TIPO_RE.search(text)
    if not tipo_match:
        return None
    tipo = tipo_match.group(1).lower()

    # Procura o período de anos numa janela à volta da menção ao tipo de taxa
    # (não no texto inteiro — evita apanhar "prazo: 35 anos", que é a duração
    # TOTAL do crédito, não o período de taxa fixa).
    window_start = tipo_match.start()
    window = text[window_start:window_start + 200]

    range_match = _ANOS_RANGE_RE.search(window)
    if range_match:
        lo, hi = int(range_match.group(1)), int(range_match.group(2))
        lo, hi = min(lo, hi), max(lo, hi)
        if _plausivel(lo) and _plausivel(hi):
            return {"tipo": tipo, "anos_min": lo, "anos_max": hi}
        return None

    single_match = _ANOS_SINGLE_RE.search(window)
    if single_match:
        anos = int(single_match.group(1))
        if _plausivel(anos):
            return {"tipo": tipo, "anos_min": anos, "anos_max": anos}
        return None

    # Tipo mencionado mas sem período legível perto — não vale a pena adivinhar.
    return None


# Período de taxa fixa/mista realista: numa hipoteca a 30-40 anos, a perna
# fixa raramente passa dos 20 — valores fora disto são quase de certeza outro
# número apanhado por engano na janela de texto (idade, prazo total do
# crédito, etc.), não o período de taxa. Visto ao vivo: "31" e "80" anos, os
# dois claramente errados, no primeiro lote real testado (14 ago 2026).
MIN_ANOS_PLAUSIVEL = 1
MAX_ANOS_PLAUSIVEL = 20


def _plausivel(anos: int) -> bool:
    return MIN_ANOS_PLAUSIVEL <= anos <= MAX_ANOS_PLAUSIVEL
