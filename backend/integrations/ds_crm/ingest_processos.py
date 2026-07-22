"""Fetch all credit processes from CrediDesk and upsert into ds.processos_real.

Idempotent — re-runs overwrite by crm_id. Each run logged in ds.crm_sync_runs.

Prereq: migration 004_processos_real.sql applied in Supabase.
"""
from __future__ import annotations

import sys
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
        "reference": row.get("reference"),
        "customer_crm_id": row.get("customerId"),
        "customer_name": row.get("customerName"),
        "customer_tax_number": row.get("customerTaxNumber"),
        "customer_email": row.get("customerEmail"),
        "customer_telephone": row.get("customerTelephone"),
        "manager_crm_id": row.get("managerId"),
        "manager_name": row.get("managerName"),
        "state_id": row.get("stateId"),
        "state_name": row.get("stateName"),
        "type_name": row.get("typeName"),
        "property_mortgage": row.get("propertyMortgage"),
        "archived": bool(row.get("archived")),
        "financing_amount": row.get("financingAmount"),
        "financing_amount_finished": row.get("financingAmountFinished"),
        "commission_amount": row.get("commissionAmount"),
        "docs_mandatory": row.get("docsMandatory"),
        "docs_uploaded": row.get("docsUploaded"),
        "docs_validated": row.get("docsValidated"),
        "notifications_not_treated": row.get("notificationsNotTreated"),
        "created_on_crm": row.get("createdon"),
        "updated_on_crm": row.get("updatedon"),
        "raw": row,
    }


def main():
    sb = supabase()
    run = sb.table("crm_sync_runs").insert({
        "source": "credidesk_processos",
        "rows_fetched": 0,
        "rows_upserted": 0,
    }).execute()
    run_id = run.data[0]["id"]

    accounts = list_crm_accounts()
    print(f"[ingest] {len(accounts)} conta(s) CRM: {[a.username for a in accounts]}")
    total_fetched = 0
    total_upserted = 0
    BATCH_SIZE = 100

    # Two-pass merge: a processo can be visible to MORE THAN ONE account, so we
    # collect the row data plus the SET of accounts that saw it, then upsert each
    # crm_id once with source_accounts = that set. This avoids the last-writer
    # overwrite that a per-account upsert would cause on overlapping rows.
    merged: dict[int, dict] = {}        # crm_id -> normalised row (latest wins)
    seen_by: dict[int, set[str]] = {}   # crm_id -> {usernames that can see it}

    try:
        for acct in accounts:
            print(f"[ingest] --- conta {acct.username} ({acct.crm_email}) ---")
            client = CredidekClient(email=acct.crm_email, password=acct.crm_password)
            for row in client.iter_processos(page_size=50, archived=True):
                total_fetched += 1
                norm = normalise(row)
                cid = norm["crm_id"]
                merged[cid] = norm
                seen_by.setdefault(cid, set()).add(acct.username)

        batch: list[dict] = []
        total_upserted = 0
        for cid, norm in merged.items():
            norm["source_accounts"] = sorted(seen_by[cid])
            batch.append(norm)
            if len(batch) >= BATCH_SIZE:
                sb.table("processos_real").upsert(batch, on_conflict="crm_id").execute()
                total_upserted += len(batch)
                print(f"[ingest] upserted batch — total {total_upserted}")
                batch.clear()
        if batch:
            sb.table("processos_real").upsert(batch, on_conflict="crm_id").execute()
            total_upserted += len(batch)
            print(f"[ingest] upserted final batch — total {total_upserted}")

        sb.table("crm_sync_runs").update({
            "rows_fetched": total_fetched,
            "rows_upserted": total_upserted,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()
        print(f"\n[done] fetched {total_fetched} processos, {len(merged)} distintos, upserted {total_upserted}")
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
