-- 014_clientes_manager.sql
-- NEW 2026-07-09. Surface the customer's own responsible manager (consultor).
--
-- CrediDesk returns `managerName`/`managerId` ON THE CUSTOMER record itself and
-- it is populated for 100% of customers — but migration 003 never mapped it, so
-- it lived only inside clientes_real.raw. The aniversário trigger (which reads
-- clientes_real, a table with no manager column) fell back to an indirect lookup
-- via the customer's most-recent processo, which shows "—" for customers that
-- have no processo in our mirror (~534/1182 birthday clients). The manager was in
-- the data all along.
--
-- This adds the typed columns and backfills them from raw. Going forward,
-- ingest_customers.py maps them on every sync.

set search_path to ds, public;

alter table clientes_real add column if not exists manager_name   text;
alter table clientes_real add column if not exists manager_crm_id bigint;

-- Backfill existing rows from the raw CRM payload (idempotent — only fills nulls).
update clientes_real
   set manager_name   = nullif(raw->>'managerName', ''),
       manager_crm_id = nullif(raw->>'managerId', '')::bigint
 where manager_name is null;

create index if not exists clientes_real_manager_idx on clientes_real(manager_crm_id);
