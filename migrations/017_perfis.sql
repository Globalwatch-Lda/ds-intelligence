-- 017_perfis.sql
-- NEW 2026-07-10. Data-driven, EDITABLE profiles (RBAC) replacing the hard-coded
-- role checks scattered across the backend.
--
-- A profile carries:
--   * chave       — stable slug; platform_users.role continues to store this
--   * nome        — PT display label
--   * is_system   — seeded default; cannot be deleted (may be edited)
--   * data_scope  — CRM data visibility: loja | equipa | propria | nenhuma
--   * permissoes  — jsonb array of capability keys (catalog lives in code,
--                   backend/app/core/capabilities.py)
--
-- The five seeded profiles reproduce today's behaviour so nothing breaks while
-- the checks migrate from role-literals to capability lookups.

set search_path to ds, public;

create table if not exists perfis (
  id          bigint generated always as identity primary key,
  chave       text not null unique,
  nome        text not null,
  is_system   boolean not null default false,
  data_scope  text not null default 'propria',
  permissoes  jsonb not null default '[]'::jsonb,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint perfis_data_scope_chk check (data_scope in ('loja','equipa','propria','nenhuma'))
);

grant all on table perfis to anon, authenticated, service_role;

-- ---- seed the five system profiles (idempotent) --------------------------
-- All pages: contactos, dashboard, leads, newsletter, recap, crm_live, configuracoes
-- Actions: users.manage, teams.manage, profiles.manage, crm.sync, loja.edit,
--          messaging.send, messaging.config
insert into perfis (chave, nome, is_system, data_scope, permissoes) values
  ('administrador', 'Administrador', true, 'loja',
    '["page.contactos","page.dashboard","page.leads","page.newsletter","page.recap","page.crm_live","page.configuracoes","users.manage","teams.manage","profiles.manage","crm.sync","loja.edit","messaging.send","messaging.config"]'::jsonb),
  ('diretor_loja', 'Diretor de Loja', true, 'loja',
    '["page.contactos","page.dashboard","page.leads","page.newsletter","page.recap","page.crm_live","page.configuracoes","users.manage","teams.manage","profiles.manage","crm.sync","loja.edit","messaging.send","messaging.config"]'::jsonb),
  ('diretor_comercial', 'Diretor Comercial', true, 'equipa',
    '["page.contactos","page.dashboard","page.leads","page.recap","page.crm_live","page.configuracoes","users.manage","teams.manage","messaging.send"]'::jsonb),
  ('consultor', 'Consultor', true, 'propria',
    '["page.contactos","page.dashboard","page.leads","page.recap","messaging.send"]'::jsonb),
  ('administrativo', 'Administrativo', true, 'loja',
    '["page.contactos","page.dashboard","page.leads","page.newsletter"]'::jsonb)
on conflict (chave) do nothing;

-- ---- migrate existing role values ----------------------------------------
-- The old 'comercial' role becomes 'consultor'. bs/jg stay diretor_loja.
update platform_users set role = 'consultor' where role = 'comercial';
-- Any leftover/unknown role → consultor (safe least-privilege baseline).
update platform_users pu
  set role = 'consultor'
  where pu.role is null
     or not exists (select 1 from perfis p where p.chave = pu.role);
