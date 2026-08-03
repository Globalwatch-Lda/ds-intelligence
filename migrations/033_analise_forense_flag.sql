-- 033_analise_forense_flag.sql
-- NEW 2026-08-03. Interruptor da Fase 3 da Análise Documental (integridade do
-- ficheiro: Sejda, iLovePDF, Photoshop, guardas incrementais…).
-- Aplicar nos DOIS schemas (ds e dsl) — trocar o search_path para cada um.
--
-- Fica ligada por omissão: é a análise que o cliente pediu e não tem custo
-- (leitura de bytes, sem chamada ao modelo). O interruptor existe para a loja a
-- poder desligar se decidir que os sinais de edição lhe dão ruído a mais —
-- documentos re-gravados por ferramentas online são banais em certos circuitos.

set search_path to ds, public;

alter table loja_config add column if not exists analise_forense_ativa boolean not null default true;
