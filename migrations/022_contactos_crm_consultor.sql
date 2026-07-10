-- 022_contactos_crm_consultor.sql
-- NEW 2026-07-10. Point the Contactos/broadcasts feature at the REAL CRM consultores
-- instead of the (deleted) mock ds.gestores table.
--
-- consultor_id stops being a uuid FK to ds.gestores and becomes free text holding
-- the CRM manager_crm_id (as text). Both tables are empty, so the type change is safe.

set search_path to ds, public;

alter table contactos_consultor drop constraint if exists contactos_consultor_consultor_id_fkey;
alter table broadcasts          drop constraint if exists broadcasts_consultor_id_fkey;

alter table contactos_consultor alter column consultor_id type text using consultor_id::text;
alter table broadcasts          alter column consultor_id type text using consultor_id::text;
