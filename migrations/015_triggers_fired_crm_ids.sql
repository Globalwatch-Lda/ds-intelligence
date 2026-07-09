-- 015_triggers_fired_crm_ids.sql
-- NEW 2026-07-09. Close the mock→live schema gap on the audit tables.
--
-- triggers_fired + mensagens were created (001) with the mock-era uuid keys
-- (cliente_id/processo_id/apolice_id → mock tables). The routers since moved to
-- the live CRM path, which keys audit rows on the CrediDesk bigint ids
-- (cliente_crm_id / processo_crm_id). Those columns were never added, so:
--   * GET /api/triggers/list?trigger=doc_atraso 500s reading triggers_fired
--     .processo_crm_id (column does not exist) — the "carregar contactos" hang.
--   * POST /api/triggers/fire would 500 inserting cliente_crm_id/processo_crm_id.
--
-- Additive + nullable; the mock uuid columns stay for the mock/seed path.

set search_path to ds, public;

alter table triggers_fired add column if not exists cliente_crm_id   bigint;
alter table triggers_fired add column if not exists processo_crm_id  bigint;
alter table mensagens      add column if not exists cliente_crm_id   bigint;

-- doc_atraso reads by (trigger_type, processo_crm_id); index the ladder lookup.
create index if not exists triggers_fired_processo_crm_idx
  on triggers_fired(trigger_type, processo_crm_id);
