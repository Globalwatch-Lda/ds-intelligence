-- 019_password_resets.sql
-- NEW 2026-07-10. Password recovery tokens.
--
-- Only the SHA-256 HASH of the reset token is stored (the raw token lives only in
-- the emailed link). Tokens are single-use (used_at) and short-lived (expires_at).

set search_path to ds, public;

create table if not exists password_resets (
  id         bigint generated always as identity primary key,
  user_id    bigint not null references platform_users(id) on delete cascade,
  token_hash text not null,
  expires_at timestamptz not null,
  used_at    timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists password_resets_token_idx on password_resets(token_hash);
create index if not exists password_resets_user_idx on password_resets(user_id);

grant all on table password_resets to anon, authenticated, service_role;
