-- 028_setup_estado.sql
-- NEW 2026-07-31. Estado dos assistentes de configuração passo a passo.
-- Aplicar nos DOIS schemas (ds e dsl) — trocar o search_path para cada um.
--
-- PORQUÊ NO SERVIDOR e não no browser: a configuração de um canal leva dias
-- (verificação de negócio, aprovação de nome, templates) e passa por mais do que
-- uma pessoa. Guardado em localStorage, o progresso perdia-se ao mudar de máquina
-- e cada pessoa via um estado diferente do mesmo trabalho.
--
-- `chave` identifica o assistente (ex.: 'whatsapp_meta'), `dados` guarda que passos
-- estão dados. Genérico de propósito: os outros canais vão querer o mesmo.

set search_path to ds, public;

create table if not exists setup_estado (
  chave      text primary key,
  dados      jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

grant all on table setup_estado to anon, authenticated, service_role;
