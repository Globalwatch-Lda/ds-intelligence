-- 018_equipas.sql
-- NEW 2026-07-10. Named teams (Equipas). Each team has a name and a leader
-- (a Diretor Comercial); consultores are assigned to a team via
-- platform_users.equipa_id.
--
-- Relationship to the existing manager_id: equipa_id is the source of truth for
-- team membership + the team's name, and manager_id is kept in sync (set to the
-- team's leader) by the API so the existing user-management/permission logic keeps
-- working unchanged. Org structure (equipas) is separate from CRM data visibility
-- (source_accounts / manager_crm_id via data_scope) — they are complementary.

set search_path to ds, public;

create table if not exists equipas (
  id         bigint generated always as identity primary key,
  nome       text not null,
  lider_id   bigint references platform_users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table platform_users
  add column if not exists equipa_id bigint references equipas(id) on delete set null;

create index if not exists platform_users_equipa_idx on platform_users(equipa_id);
create index if not exists equipas_lider_idx on equipas(lider_id);

grant all on table equipas to anon, authenticated, service_role;
