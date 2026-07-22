"""Regras de valores monetários dos processos.

O CrediDesk tem dois montantes por processo: financingAmount (pedido) e
financingAmountFinished (final/aprovado pelo banco). O dashboard do CRM usa o
"finished" quando existe — a plataforma segue a mesma regra para os volumes
baterem com o CRM (verificado 2026-07-22, loja Loulé: 7 processos divergiam).
"""
from __future__ import annotations


def valor_financiamento(p: dict) -> float:
    """Valor efetivo do processo: aprovado quando existe, senão o pedido."""
    try:
        finished = float(p.get("financing_amount_finished") or 0)
    except (TypeError, ValueError):
        finished = 0.0
    if finished:
        return finished
    try:
        return float(p.get("financing_amount") or 0)
    except (TypeError, ValueError):
        return 0.0
