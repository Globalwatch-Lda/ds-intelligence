-- 029_leads_ultima_acao.sql
-- NEW 2026-08-03. Última acção/intervenção de cada lead, vinda do CRM.
-- Aplicar nos DOIS schemas (ds e dsl) — trocar o search_path para cada um.
--
-- A lista de leads do CrediDesk (/customerspotential/leads/list) só traz datas —
-- `updatedon` diz QUANDO alguém mexeu, nunca O QUÊ. O que a ficha da lead mostra
-- na aba "Atividade" vem de outro endpoint, POST /customerspotential/leads/historic/list,
-- que devolve a timeline: createdOn, observation (o texto da acção), stateName,
-- typeId e agentName. Espelhamos aqui só o registo MAIS RECENTE — é o que a
-- coluna "Última acção" da página de Leads precisa; a timeline completa continua
-- a viver no CRM, que é o sistema de registo.
--
-- last_action_at é timestamptz (o CRM manda ISO com offset +01:00), ao contrário
-- de created_on_crm/updated_on_crm que são text por herança da migração 006.

set search_path to ds, public;

alter table leads_real add column if not exists last_action_at    timestamptz;
alter table leads_real add column if not exists last_action_text  text;     -- observation
alter table leads_real add column if not exists last_action_type  integer;  -- typeId (0=nota, 1=sistema, ...)
alter table leads_real add column if not exists last_action_state text;     -- stateName no momento da acção
alter table leads_real add column if not exists last_action_agent text;     -- agentName
alter table leads_real add column if not exists last_action_count integer;  -- nº de registos no histórico
-- Quando é que fomos buscar o histórico desta lead (null = nunca).
alter table leads_real add column if not exists historic_synced_at timestamptz;

create index if not exists leads_real_last_action_idx on leads_real(last_action_at desc);
