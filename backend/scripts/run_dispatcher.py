"""Dispatcher worker — sends due messages from ds.envios once and exits.

Run by cron on the box (e.g. every minute):
    * * * * * cd ~/ds-engine/backend && /usr/bin/python scripts/run_dispatcher.py >> ~/ds-dispatch.log 2>&1

Single-shot on purpose: cron owns the cadence, the process never lingers, and the
per-channel throttle (batch/intervalo/cap_diario) is enforced by process_due via the
`agendado_para` schedule set at enqueue time. Safe to run concurrently-ish — each row
is flipped from 'pendente' as it is sent.
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# backend/ on sys.path so `app` imports resolve when run from anywhere.
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
load_dotenv(BACKEND / ".env")

from app.core.dispatcher import process_due  # noqa: E402


def main() -> None:
    result = process_due()
    print(f"[dispatcher] {result}")


if __name__ == "__main__":
    main()
