-- 031_leads_novas_boas_vindas.sql
-- NEW 2026-08-03. Leads novas (por trabalhar) + registo do email de boas-vindas.
-- Aplicar nos DOIS schemas (ds e dsl) — trocar o search_path para cada um.
--
-- `interacoes_agente` conta os registos do histórico do CRM escritos por uma
-- pessoa (typeId 0). É o que distingue uma lead POR TRABALHAR de uma já contactada:
-- contar o histórico todo não servia, porque a criação da lead e o arquivo
-- automático também lá aparecem (typeId 1 e -1). Zero = ninguém lhe tocou → a
-- página mostra-a a negrito.
--
-- `lead_emails` regista o que a plataforma enviou a uma lead. Fica em tabela
-- própria (e não numa coluna de leads_real) porque o ingest nocturno faz upsert
-- por `crm_id` e este registo é NOSSO — não pode depender de o worker o preservar.

set search_path to ds, public;

alter table leads_real add column if not exists interacoes_agente integer;

create table if not exists lead_emails (
  id            bigint generated always as identity primary key,
  lead_crm_id   bigint not null,
  tipo          text not null default 'boas_vindas',
  destinatario  text not null,
  assunto       text,
  envio_id      bigint,          -- ds.envios.id (fila multicanal), quando enfileirado
  entregue      boolean,         -- resultado da entrega imediata, se houve
  erro          text,
  enviado_por   text,            -- platform_users.username
  enviado_em    timestamptz not null default now()
);

create index if not exists lead_emails_lead_idx on lead_emails(lead_crm_id, tipo);

grant all on table lead_emails to anon, authenticated, service_role;
