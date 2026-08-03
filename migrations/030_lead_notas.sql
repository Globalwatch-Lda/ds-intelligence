-- 030_lead_notas.sql
-- NEW 2026-08-03. Notas com data + lembrete nas leads (funcionalidade da plataforma,
-- NÃO do CRM). Aplicar nos DOIS schemas (ds e dsl) — trocar o search_path para cada um.
--
-- Porquê aqui e não no CrediDesk: os workers de CRM são read-only por decisão
-- documentada (DEPLOY.md §3) — corremos com as credenciais pessoais do Bruno e
-- nunca escrevemos no CRM da empresa. Estas notas são da DS Matrix; a coluna
-- "Última acção" (migração 029) continua a espelhar o que o CRM regista.
--
-- Visibilidade (decisão do cliente, 2026-08-03): o LEMBRETE avisa quem o criou;
-- quem tem visão de loja (perfil com data_scope='loja', tipicamente o Diretor de
-- Loja) vê as notas todas. Isso é resolvido no router (core/scope.py), não por RLS —
-- a API fala com a base pela service_role, como todo o resto da plataforma.
--
-- lembrete_em nulo = nota sem lembrete (só registo). lembrete_canais diz por onde
-- avisar: 'app' (sino + aviso no ecrã) e/ou 'email' (ao criador, via SES).

set search_path to ds, public;

create table if not exists lead_notas (
  id               bigint generated always as identity primary key,
  lead_crm_id      bigint not null,                    -- ds.leads_real.crm_id
  lead_nome        text,                               -- denormalizado: o email do lembrete não volta ao CRM
  texto            text not null,
  data_nota        date,                               -- data a que a nota diz respeito
  lembrete_em      timestamptz,                        -- quando notificar (null = sem lembrete)
  lembrete_canais  text[] not null default '{app}',    -- app | email
  notificado_em    timestamptz,                        -- email do lembrete já enviado
  notificacao_erro text,                               -- último erro de envio (diagnóstico)
  visto_em         timestamptz,                        -- lembrete dispensado no sino
  concluida_em     timestamptz,                        -- nota marcada como tratada
  criado_por       text not null,                      -- platform_users.username
  criado_por_nome  text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create index if not exists lead_notas_lead_idx on lead_notas(lead_crm_id);
create index if not exists lead_notas_criado_por_idx on lead_notas(criado_por);
-- Fila do worker de lembretes: só interessam os que têm hora e ainda não avisaram.
create index if not exists lead_notas_lembrete_idx
  on lead_notas(lembrete_em)
  where lembrete_em is not null and notificado_em is null and concluida_em is null;

grant all on table lead_notas to anon, authenticated, service_role;
