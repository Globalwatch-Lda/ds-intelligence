-- 020_messaging.sql
-- NEW 2026-07-10. Generic communication layer (Workstream D).
--
-- Email + SMS (AWS) and WhatsApp (Evolution) are reusable channels for ANY platform
-- communication (platform→colaboradores, platform→clientes), not only newsletters.
--
--  messaging_config : per-channel throttle + sender settings (one row per channel).
--                     batch_size messages are scheduled together, then spaced by
--                     intervalo_segundos, up to cap_diario per day — to avoid
--                     tripping anti-spam alarms.
--  envios           : the send queue AND history. Rows are enqueued with a spaced
--                     agendado_para; a dispatcher worker sends the due ones.
--                     Supersedes the old ds.mensagens table.

set search_path to ds, public;

create table if not exists messaging_config (
  canal              text primary key,     -- 'email' | 'sms' | 'whatsapp_evolution'
  ativo              boolean not null default false,
  batch_size         integer not null default 50,
  intervalo_segundos integer not null default 2,
  cap_diario         integer not null default 500,
  remetente          text,                 -- e.g. "DS Crédito"
  updated_at         timestamptz not null default now()
);

insert into messaging_config (canal, remetente, batch_size, intervalo_segundos, cap_diario) values
  ('email',              'DS Crédito', 50, 1,  1000),
  ('sms',                'DSCredito',  20, 3,  300),
  ('whatsapp_evolution', 'DS Crédito', 10, 8,  200)
on conflict (canal) do nothing;

create table if not exists envios (
  id            bigint generated always as identity primary key,
  canal         text not null,
  destinatario  text not null,            -- email / E.164 phone
  assunto       text,
  corpo         text not null,
  ref_tipo      text,                     -- newsletter | colaborador | cliente | sistema | ...
  ref_id        text,
  status        text not null default 'pendente',  -- pendente | enviado | falhou | cancelado
  agendado_para timestamptz not null default now(),
  enviado_em    timestamptz,
  erro          text,
  criado_por    text,                     -- platform username
  criado_em     timestamptz not null default now()
);

create index if not exists envios_due_idx on envios(canal, status, agendado_para);
create index if not exists envios_ref_idx on envios(ref_tipo, ref_id);

grant all on table messaging_config to anon, authenticated, service_role;
grant all on table envios to anon, authenticated, service_role;
