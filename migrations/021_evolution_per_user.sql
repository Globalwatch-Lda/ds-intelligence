-- 021_evolution_per_user.sql
-- NEW 2026-07-10. Per-user WhatsApp (Evolution) sending.
--
-- Each user connects their OWN WhatsApp number as a dedicated Evolution instance
-- (scanning a QR once). platform_users.evolution_instance stores that instance name;
-- outbound WhatsApp then goes through the SENDER's instance so the message comes from
-- their number. envios.canal_conta freezes the instance used for each queued message
-- (resolved from criado_por at enqueue time), independent of later profile changes.

set search_path to ds, public;

alter table platform_users add column if not exists evolution_instance text;
alter table envios add column if not exists canal_conta text;
