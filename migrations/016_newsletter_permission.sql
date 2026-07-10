-- 016_newsletter_permission.sql
-- NEW 2026-07-10. Per-user permission to GENERATE/SEND newsletters.
--
-- Newsletter authoring is a per-user grant, not a role: bs and jg are both
-- diretor_loja, yet only Bruno Sousa (bs) may author. Users without the grant
-- still SEE the latest newsletter + the sent-history (read-only) — the write
-- endpoints (generate/upload/reformat/edit/send) are gated in the API.
--
-- Env-only admin logins (ds/amin) have no platform_users row and keep access
-- (treated as allowed in the API), so nobody is locked out during a demo.

set search_path to ds, public;

alter table platform_users
  add column if not exists can_newsletter boolean not null default false;

-- Bruno Sousa authors; everyone else is read-only until granted.
update platform_users set can_newsletter = true where username = 'bs';
