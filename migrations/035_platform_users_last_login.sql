-- 035_platform_users_last_login.sql
-- NEW 2026-11-11. Hora do último login bem-sucedido de cada utilizador.
-- Até aqui o login não deixava rasto na base — só o access log do nginx, que
-- não diz QUEM entrou e roda ao fim de ~14 dias.
--
-- Escrito por routers/auth.py no POST /login (best-effort: uma falha a gravar
-- nunca impede a entrada). As contas só de .env (sem linha aqui) não ficam
-- registadas na base, mas o login fica sempre no journal com o username.
--
-- Aplicar em TODOS os schemas de loja (ds, dsl, ...) — trocar o search_path.

set search_path to ds, public;

alter table platform_users add column if not exists last_login_at timestamptz;
