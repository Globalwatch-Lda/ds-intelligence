-- 032_loja_dados_fiscais.sql
-- NEW 2026-08-03. Dados fiscais da loja, tal como estão no CRM.
-- Aplicar nos DOIS schemas (ds e dsl) — trocar o search_path para cada um.
--
-- Fonte: CrediDesk `GET /agency/{agencyId}` (a loja) e `GET /company/{companyId}`
-- (a sociedade que a explora — é aqui que vivem NIF, capital social, gerência e o
-- registo de intermediário de crédito no Banco de Portugal). Descoberto a
-- 3 Ago 2026; nenhum destes dois endpoints estava a ser usado pela plataforma.
--
-- Guardamos uma CÓPIA e não lemos o CRM a cada visita: a tab Loja abre em
-- milissegundos, funciona com o CRM em baixo, e o botão "Actualizar do CRM" torna
-- explícito quando a cópia foi refrescada (`fiscais_atualizado_em`). São dados
-- que mudam uma vez por ano, não a cada minuto.
--
-- `fiscais_raw` guarda o par agência+empresa completo: o que hoje não mostramos
-- (seguro de responsabilidade civil, membros do órgão de administração, mutuantes)
-- fica disponível sem nova migração quando for preciso.

set search_path to ds, public;

alter table loja_config add column if not exists empresa_nome           text;    -- denominação social
alter table loja_config add column if not exists empresa_nome_comercial text;    -- businnessName
alter table loja_config add column if not exists nif                    text;    -- taxidNumber
alter table loja_config add column if not exists morada                 text;
alter table loja_config add column if not exists codigo_postal          text;
alter table loja_config add column if not exists localidade             text;
alter table loja_config add column if not exists concelho               text;
alter table loja_config add column if not exists distrito               text;
alter table loja_config add column if not exists telefone               text;
alter table loja_config add column if not exists email                  text;
alter table loja_config add column if not exists website                text;
alter table loja_config add column if not exists capital_social         numeric(14,2);
alter table loja_config add column if not exists gerencia               text;    -- managerName
alter table loja_config add column if not exists registo_bp             text;    -- nº de registo no Banco de Portugal
alter table loja_config add column if not exists categoria_bp           text;    -- ex.: "Vinculado"
alter table loja_config add column if not exists agencia_nome           text;    -- nome da agência no CRM
alter table loja_config add column if not exists agencia_crm_id         bigint;
alter table loja_config add column if not exists empresa_crm_id         bigint;
alter table loja_config add column if not exists fiscais_raw            jsonb;
alter table loja_config add column if not exists fiscais_atualizado_em  timestamptz;
