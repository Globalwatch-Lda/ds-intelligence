"""Fetch all customers from CrediDesk and upsert into ds.clientes_real.

Idempotent — re-runs overwrite the row keyed on crm_id. Each run is logged in
ds.crm_sync_runs so the UI can show "last sync at HH:MM, N rows."

Prereq: migration 003_crm_real_mirror.sql applied in Supabase.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # add backend/ to path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.db import supabase  # noqa: E402
from integrations.ds_crm.accounts import list_crm_accounts  # noqa: E402
from integrations.ds_crm.client import CredidekClient  # noqa: E402


def normalise(row: dict) -> dict:
    return {
        "crm_id": row["id"],
        "name": row.get("name"),
        "email": row.get("email"),
        "telephone": row.get("telephone"),
        "tax_number": row.get("taxNumber"),
        "age": row.get("age"),
        "date_of_birth": row.get("dateofbirth"),
        "country_id": row.get("countryId"),
        "identity_card": row.get("identityCard"),
        "manager_name": row.get("managerName"),
        "manager_crm_id": row.get("managerId"),
        "created_on_crm": row.get("createdon"),
        "raw": row,
    }


def main():
    sb = supabase()
    run = sb.table("crm_sync_runs").insert({
        "source": "credidesk_customers",
        "rows_fetched": 0,
        "rows_upserted": 0,
    }).execute()
    run_id = run.data[0]["id"]

    accounts = list_crm_accounts()
    print(f"[ingest] {len(accounts)} conta(s) CRM: {[a.username for a in accounts]}")
    total_fetched = 0
    total_upserted = 0
    BATCH_SIZE = 100

    # clientes_real has no source_accounts scoping — merge by crm_id across
    # accounts (latest wins) and upsert each customer once.
    merged: dict[int, dict] = {}

    try:
        for acct in accounts:
            print(f"[ingest] --- conta {acct.username} ({acct.crm_email}) ---")
            client = CredidekClient(email=acct.crm_email, password=acct.crm_password)
            for row in client.iter_customers(page_size=50):
                total_fetched += 1
                norm = normalise(row)
                merged[norm["crm_id"]] = norm

        batch: list[dict] = []
        for norm in merged.values():
            batch.append(norm)
            if len(batch) >= BATCH_SIZE:
                sb.table("clientes_real").upsert(batch, on_conflict="crm_id").execute()
                total_upserted += len(batch)
                print(f"[ingest] upserted batch — total {total_upserted}")
                batch.clear()
        if batch:
            sb.table("clientes_real").upsert(batch, on_conflict="crm_id").execute()
            total_upserted += len(batch)
            print(f"[ingest] upserted final batch — total {total_upserted}")

        sb.table("crm_sync_runs").update({
            "rows_fetched": total_fetched,
            "rows_upserted": total_upserted,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()
        print(f"\n[done] fetched {total_fetched} customers, {len(merged)} distintos, upserted {total_upserted}")
    except Exception as e:
        sb.table("crm_sync_runs").update({
            "rows_fetched": total_fetched,
            "rows_upserted": total_upserted,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "error": f"{type(e).__name__}: {e}"[:1000],
        }).eq("id", run_id).execute()
        raise


if __name__ == "__main__":
    main()
