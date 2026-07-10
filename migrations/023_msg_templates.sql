-- 023_msg_templates.sql
-- NEW 2026-07-10. Loja-wide message templates by theme, used in the WhatsApp
-- composer (aniversário, aprovação de crédito, documentos, …). Placeholders
-- {{nome_cliente}} / {{nome_consultor}} are filled per send.

set search_path to ds, public;

create table if not exists msg_templates (
  id         bigint generated always as identity primary key,
  nome       text not null,
  categoria  text,
  corpo      text not null,
  ativo      boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

grant all on table msg_templates to anon, authenticated, service_role;

insert into msg_templates (nome, categoria, corpo) values
  ('Aniversário', 'aniversario',
   'Olá {{nome_cliente}}, é o {{nome_consultor}} da DS Crédito. Desejo-lhe um feliz aniversário! 🎉 Que tenha um dia excelente. Conte comigo para o que precisar.'),
  ('Aprovação de crédito', 'aprovacao_credito',
   'Boas notícias, {{nome_cliente}}! O seu processo de crédito foi aprovado. Sou o {{nome_consultor}} da DS Crédito e estou disponível para avançarmos com os próximos passos.'),
  ('Documentos em falta', 'documentos',
   'Olá {{nome_cliente}}, é o {{nome_consultor}} da DS Crédito. Para continuarmos com o seu processo faltam alguns documentos. Pode enviá-los quando puder? Obrigado.'),
  ('Acompanhamento', 'acompanhamento',
   'Olá {{nome_cliente}}, é o {{nome_consultor}} da DS Crédito. Só um contacto para saber se está tudo bem e se posso ajudar em alguma questão de crédito ou seguros.')
on conflict do nothing;
