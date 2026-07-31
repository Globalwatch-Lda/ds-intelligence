-- 027_lojas_superadmin.sql
-- NEW 2026-07-31. Catálogo de lojas + sentinela superadmin. Aplicar nos DOIS
-- schemas (ds e dsl) — trocar o search_path abaixo para cada um.
--
-- PORQUÊ UMA TABELA E NÃO O CRM: a conta CrediDesk de cada loja só alcança a
-- SUA agência. Verificado a 31 jul 2026: /agency/839 devolve code 1 com a conta
-- da Ramada, e 824/838/840/1/100 devolvem code -1; não há endpoint de listagem
-- (/agencies e /companies dão 404). Logo o catálogo é mantido à mão — não há
-- como o descobrir a partir do CRM.
--
-- lojas          catálogo (numero = agencyId do CrediDesk, chave natural)
-- loja_config.numero  qual destas lojas É esta instalação (escolhido no combobox)
-- platform_users.is_superadmin  sentinela: existe em todas as instalações DS e é
--                 o único que edita o catálogo. Flag ORTOGONAL ao perfil — o
--                 utilizador mantém o seu perfil funcional e ganha isto por cima,
--                 para não haver que rever quem pode atribuir perfis.

set search_path to ds, public;

create table if not exists lojas (
  numero     text primary key,          -- agencyId do CrediDesk (ex.: '839')
  nome       text not null,
  updated_at timestamptz not null default now()
);

-- As duas lojas conhecidas, ambas confirmadas pelo agencyId do JWT da respetiva
-- conta CRM (839 brunosousa@, 824 pedroduraes@) — não por documentação.
insert into lojas (numero, nome) values
  ('839', 'DS Crédito Jardim da Amoreira'),
  ('824', 'DS Crédito Loulé')
on conflict (numero) do nothing;

alter table platform_users
  add column if not exists is_superadmin boolean not null default false;

comment on column platform_users.is_superadmin is
  'Sentinela GlobalWatch: edita o catálogo de lojas e escolhe a loja da instalação. Ortogonal ao perfil.';

grant all on table lojas to anon, authenticated, service_role;
