-- 024_multicanal_module.sql
-- NEW 2026-07-11. Wire do módulo empacotado `synertia-multicanal` no dscredito.
--
-- As tabelas da fila (messaging_config, envios, msg_templates) já existem (020/023).
-- Esta migração acrescenta só as DUAS tabelas próprias do pacote:
--   multicanal_config : credenciais + branding por canal, editáveis na tab
--                       "Comunicação Multicanal" (Configurações). É o que torna a
--                       instalação "preencher e trabalhar" — o .env é só fallback.
--   multicanal_meta   : versão + estado de instalação do módulo (para o "Sobre" e
--                       para a checkbox dos Módulos, que é one-way).

set search_path to ds, public;

create table if not exists multicanal_config (
  id         integer primary key default 1,
  config     jsonb       not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  constraint multicanal_config_singleton check (id = 1)
);
insert into multicanal_config (id, config) values (1, '{}'::jsonb) on conflict (id) do nothing;

create table if not exists multicanal_meta (
  id           integer primary key default 1,
  version      text,
  channels     text[]      not null default '{}',
  installed    boolean     not null default false,   -- one-way: nunca volta a false
  installed_at timestamptz,
  updated_at   timestamptz not null default now(),
  constraint multicanal_meta_singleton check (id = 1)
);
insert into multicanal_meta (id) values (1) on conflict (id) do nothing;

grant all on table multicanal_config to anon, authenticated, service_role;
grant all on table multicanal_meta to anon, authenticated, service_role;
