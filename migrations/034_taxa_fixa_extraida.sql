-- 034_taxa_fixa_extraida.sql
-- NEW 2026-08-14. Extração best-effort do período de taxa fixa/mista a partir
-- do resumo em texto livre `contextPartners.html` do CrediDesk (não existe
-- campo estruturado na API — confirmado testando +10 processos reais, ver
-- backend/integrations/ds_crm/taxa_fixa.py para o porquê e o extrator).
--
-- `concluded_on_crm` é bónus: closingValues.concludedOn é a data de conclusão
-- REAL (existe só no detalhe do processo), mais precisa do que a aproximação
-- via updated_on_crm já usada nas escrituras — fica pronta a usar quando se
-- quiser trocar essa aproximação.
--
-- Aplicar nos DOIS schemas (ds e dsl) — trocar o search_path para cada um.

set search_path to ds, public;

alter table processos_real add column if not exists taxa_tipo text;
alter table processos_real add column if not exists taxa_fixa_anos_min smallint;
alter table processos_real add column if not exists taxa_fixa_anos_max smallint;
alter table processos_real add column if not exists concluded_on_crm timestamptz;
alter table processos_real add column if not exists taxa_fixa_synced_at timestamptz;
