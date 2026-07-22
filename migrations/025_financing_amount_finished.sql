-- 025_financing_amount_finished.sql
-- NEW 2026-07-22. Valor final/aprovado do processo (financingAmountFinished do
-- CrediDesk). O dashboard do CRM mostra este valor quando existe (senão o
-- financingAmount pedido); os nossos volumes passam a usar a mesma regra.
-- Aplicar também no schema dsl (Loulé): repetir com search_path dsl.

set search_path to ds, public;

alter table processos_real add column if not exists financing_amount_finished numeric;
