-- 026_analise_limites.sql
-- NEW 2026-07-22. Limites da Análise Documental (Fase 2) editáveis na tab Loja,
-- em vez de só por env (ANALISE_MAX_FICHEIROS / ANALISE_MAX_FILE_MB). Guardados
-- no loja_config (config single-row por loja). Aplicar também no schema dsl.

set search_path to ds, public;

alter table loja_config add column if not exists analise_max_ficheiros integer;
alter table loja_config add column if not exists analise_max_file_mb numeric;
