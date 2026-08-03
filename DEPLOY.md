# DS Intelligence — Operations Runbook (handover)

Handover doc for Rui. The platform is **live and autonomous** as of 2 June 2026.
Everything below is the steady-state operation: what runs by itself, what is
manual, and how to fix it when something breaks.

> Scope reminder: this mirrors **Bruno Sousa's** CrediDesk account only (agency
> 839, DS Crédito Ramada – Jardim da Amoreira). Bruno's login sees his own
> ~187 processos + ~420 leads, but the full **1.1k loja clientes**. Cross-gestor
> pipeline needs a loja-coordinator login that DS has not yet provided (Bruno
> chases on his return, 8 June). Two dashboard cards (**apólices**, **taxa fixa**)
> are tagged "Aguarda integração" on purpose — see §7.

---

## 1. Infrastructure at a glance

> ⚠️ **A plataforma saiu da AWS.** Corre em **Hetzner** desde julho de 2026 (verificado
> 2026-07-31). A box EC2 `108.130.14.101` ainda existe com uma cópia da app, mas **o DNS
> já não lhe aponta** — mexer lá não produz efeito nenhum em produção.

| Thing | Value |
|---|---|
| Platform URL | https://dscredito.synertia-gw.ai (Loulé: https://dsloule.synertia-gw.ai) |
| Servidor | Hetzner **`app-dscredito`**, IP **2.28.6.0** (também IPv6). Três apps na mesma box. |
| SSH | `ssh -i <repo synertia-vox-v2>/ignore/synertia-provision root@2.28.6.0` — os serviços correm como `ubuntu` |
| Backend | FastAPI/uvicorn, venv em `<checkout>/backend/venv` |
| Frontend | Next.js (systemd) |
| DB | Supabase ref **`bsxnzxroxcjtgtvqozgo`** — schema `ds` (Ramada) e `dsl` (Loulé), via `DB_SCHEMA`. Ligação DDL em `cred/ddl.txt` (gitignored) |
| Web server | **nginx** + Let's Encrypt/Certbot, proxy para as portas locais (o Caddy está inativo nesta box) |
| LLM | chave Anthropic dedicada da DS (`ANTHROPIC_API_KEY` no `.env`) |
| WhatsApp Meta | app Meta dedicada da DS (System User token, sem expiração) — `META_WA_*` |
| WhatsApp Evolution | servidor **no assist** (Hetzner 2.28.1.254), alcançado por túnel SSH — ver §1.2 |

### 1.1 As três instalações na box

| App | Checkout | Branch | systemd (API / frontend) | Portas | Domínio |
|---|---|---|---|---|---|
| **Prod Ramada** | `~/ds-engine` | `main` | `ds-intelligence` / `ds-intelligence-frontend` | 8005 / 3005 | dscredito.synertia-gw.ai |
| **Staging** | `~/ds-engine-staging` | `staging` | `ds-intelligence-staging` / `ds-intelligence-frontend-staging` | 8006 / 3006 | sem domínio (`server_name _`, só por IP) |
| **Loulé** | `~/ds-engine-loule` | `main` | `ds-loule` / `ds-loule-frontend` | 8007 / 3007 | dsloule.synertia-gw.ai |

Prod e Loulé correm o **mesmo branch `main`** e separam-se por `.env` (`DB_SCHEMA`,
`LOJA_NAME`, `EVOLUTION_INSTANCE_PREFIX`). Uma alteração em `main` chega às duas.

### 1.2 Evolution (WhatsApp por consultor) — não vive nesta box
O Evolution API corre no servidor **assist** (`2.28.1.254`, `/opt/evolution`, docker
compose), a escutar **só em `127.0.0.1:8088`**. A box da app chega lá por
`evolution-tunnel.service` (systemd, `enabled`, `Restart=always`), que mantém
`127.0.0.1:8088 → assist:8088`; por isso `EVOLUTION_API_URL=http://127.0.0.1:8088`
nos `.env`. A chave SSH do túnel (`~ubuntu/.ssh/evolution-tunnel`) é **dedicada** e no
assist só pode abrir aquele porto (user `evotunnel`, `permitopen`) — a
`synertia-provision` não está nesta box de propósito.

Se o QR deixar de aparecer: `systemctl status evolution-tunnel` na box da app e
`docker ps` no assist, por esta ordem.

## 1.3 Deploy — é AUTOMÁTICO, a cada 2 minutos

⚠️ **Não há passo manual.** `auto-deploy.sh` corre no cron de 2 em 2 minutos em prod
**e** em Loulé: se `origin/main` mexeu, corre o `deploy.sh` (reset hard a origin/main,
pip install, build do Next, restart dos serviços). **`git push origin main` = live em
~2 min nas duas lojas.** Não empurrar para `main` trabalho por validar.

> 🐛 **Esteve partido até 2026-07-31 e ninguém deu por isso.** Os `*.sh` estavam
> commitados como `100644`, sem bit de execução; o cron invocava
> `/home/ubuntu/ds-engine/auto-deploy.sh` diretamente, batia em *permission denied* e
> morria **em silêncio** — o `~/ds-autodeploy.log` só é escrito de dentro do script,
> por isso nem log havia. Um `chmod +x` só na box não resolvia: o `git reset --hard`
> do deploy seguinte repunha o modo do índice. Corrigido no repo com
> `git update-index --chmod=+x`. **Sintoma a reconhecer:** `git push` feito, box parada
> num HEAD antigo, `~/ds-autodeploy.log` inexistente ou congelado →
> `ls -l ~/ds-engine/*.sh` e confirmar o `x`.

- Log: `~/ds-autodeploy.log` (Loulé: o `auto-deploy.sh` do próprio checkout).
- Staging: branch `staging`, `deploy-staging.sh`.
- Novas env vars → à mão em `<checkout>/backend/.env` (o deploy nunca lhes toca) + restart.
- Migrações: `DB_URL="$(cat cred/ddl.txt)" python scripts/apply_migrations.py` (local, idempotente).

⚠️ **O módulo `synertia-multicanal` NÃO entra no auto-deploy.** É um checkout git à parte
em `<checkout>/backend/multicanal` (repo `Globalwatch-Lda/synertia-multicanal`, gitignored
aqui) e o `deploy.sh` não lhe toca. Atualizar à mão, por instalação:
```
cd ~/ds-engine/backend/multicanal && git pull --ff-only origin main && cat VERSION
sudo systemctl restart ds-intelligence      # e ds-loule para o checkout de Loulé
```
A versão a correr aparece na tab *Módulos* (available_version).

Todos os segredos vivem no `.env` de cada checkout (gitignored). O mesmo `.env` serve
a API e os workers de sincronização.

---

## 2. What runs automatically (cron na box Hetzner, user `ubuntu`)

`crontab -u ubuntu -l` para ver. Horas em **UTC** (02:00 UTC = 03:00 Europe/Lisbon no
verão). Logs: `~/ds-sync.log` (Ramada) e `~/dsl-sync.log` (Loulé).

| When (UTC) | Job |
|---|---|
| 02:00 daily | `ingest_customers.py` — refresh `ds.clientes_real` (~1.1k, ~30s) |
| 02:20 daily | `ingest_processos.py` — refresh `ds.processos_real` (~187) |
| 02:40 daily | `ingest_leads.py` — refresh `ds.leads_real` (~420) + última acção de cada lead (histórico do CRM, uma chamada por lead: +~2 min) |
| 03:00 Monday | `ingest_consent.py --stale-days 7` — refresh marketing-consent on `clientes_real` |
| 03:10 / 03:30 / 03:50 / 04:10 Mon | os mesmos quatro para **Loulé** (`~/ds-engine-loule`, schema `dsl`) |
| cada minuto | `run_dispatcher.py` — fila de envios multicanal **+ lembretes de notas de leads por email** (um por loja; logs `~/ds-dispatch.log`, `~/dsl-dispatch.log`) |
| cada 2 min | `auto-deploy.sh` — ver §1.3 |

Each worker self-mints a fresh CrediDesk JWT via **headless Chromium**
(`integrations/ds_crm/auth.py` drives the login form), so there is no manual
token rotation. Chromium is installed in `~/.cache/ms-playwright`.

**Everything else is operator-triggered** (a human clicks in the UI): trigger
sends, newsletter sends, broadcasts, the weekly recap. Nothing fires WhatsApp on
a schedule. If DS later wants the recap auto-emailed Fri/Mon, that's a v1.1
decision — don't wire it without their sign-off.

---

## 3. Manual re-sync (run any time, e.g. before a demo)

```bash
ssh -i <repo synertia-vox-v2>/ignore/synertia-provision root@2.28.6.0
sudo -iu ubuntu           # os workers correm como ubuntu
cd ~/ds-engine/backend    # (ou ~/ds-engine-loule/backend para Loulé)
venv/bin/python integrations/ds_crm/ingest_customers.py
venv/bin/python integrations/ds_crm/ingest_processos.py
venv/bin/python integrations/ds_crm/ingest_leads.py
venv/bin/python integrations/ds_crm/ingest_consent.py            # missing rows only
venv/bin/python integrations/ds_crm/ingest_consent.py --all      # full re-pull (~4 min)
```

Safe to run repeatedly — all upserts are idempotent (keyed on `crm_id`).
**Read-only against CrediDesk.** Never add POST/PUT to these workers — we hold
Bruno's personal credentials as a service-account equivalent; a destructive call
would hit the live business CRM. Rate is already gentle (0.2s between detail
calls). On a CrediDesk auth failure, do **not** retry in a loop — account lockout
behaviour is unknown. Investigate the creds instead.

---

## 4. Weekly coordinator recap

Operator-triggered HTML page, defaults to the **last completed calendar week**.

- UI: open `https://dscredito.synertia-gw.ai/recap` (week navigator ← / atual / →)
- It reads `ds.processos_real` live — no separate generation step.
- Review the 4 KPI cards + Ganhos/Anulados tables, then share manually.
- Auto-email is **not** enabled (see §2).

---

## 5. Newsletter & the consent gate

The composer (`/newsletter`) generates/edits a post, then sends as a WhatsApp
link. Sends can target the **opted-in audience only**:

- `GET /api/newsletter/audience` returns the honest split:
  `total_clientes / consent_synced / opted_in / opted_in_with_phone / deliverable_now`.
- Opt-in source is **structured CrediDesk data**, not OCR: `clientes_real.authorized_contact`
  (populated by `ingest_consent.py`). `consent_active` is a secondary CRM toggle
  and is NOT the gate — do not filter on it.
- A send with `audience="opted_in"` only goes to `authorized_contact = true`.
- During the demo phase only **Meta-verified numbers** actually deliver
  (`deliverable_now`); the rest are reported as the addressable target. With a
  production Meta number all opted-in-with-phone become reachable.

---

## 6. Adding a Meta-verified recipient (demo)

Until DS has a production WhatsApp number, real sends only reach numbers verified
in the DS Meta app. To add one for a demo:

1. Meta WhatsApp Manager → DS app → add + verify the E.164 number (one-time code).
2. Add it to `DEMO_RECIPIENTS` (comma-separated) in `~/ds-engine/backend/.env`.
3. `sudo systemctl restart ds-intelligence`.

Unverified numbers are auto-redirected in the UI so an operator never sees a
silent send failure during a demo.

---

## 7. The two "Aguarda integração" cards — what they are

- **Apólices (60d)** — DS Seguros runs on a **separate system** (not CrediDesk;
  CrediDesk's SPA has no apólices surface). This is a commercial scope
  conversation between Karim and DS, not a tech task. Card stays tagged.
- **Taxa fixa (90d)** — `/creditprocesses/{id}` exposes spread/euribor/effort
  rate but **no fixed-rate-period END date**, so the card can't be closed from
  the known endpoint. Open investigation: find another field/endpoint or confirm
  it's absent. Do not promise this card as done.

---

## 8. When a sync fails — triage

1. **Check the audit table** — every worker logs a row to `ds.crm_sync_runs`
   (`source` = `credidesk_customers` / `_processos` / `_leads` / `_consent`).
   A failed run has a non-null `error` column with the exception text.
   ```bash
   curl -s "$SUPABASE_URL/rest/v1/crm_sync_runs?select=*&order=started_at.desc&limit=5" \
     -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
     -H "Accept-Profile: ds"
   ```
2. **Check the cron log:** `tail -50 ~/ds-sync.log`.
3. **Service health:** `systemctl status ds-intelligence` / `journalctl -u ds-intelligence --since "10 min ago"`.
4. **CrediDesk JWT mint broke** (the most likely failure — they change the login
   form / Vue re-render): run `venv/bin/python integrations/ds_crm/ingest_customers.py`
   by hand and read the traceback. Auth logic is in `integrations/ds_crm/auth.py`
   (`mint_jwt`); it fills the form and Enter-submits, then scrapes the first
   `Authorization: Bearer` request to `appapi.credidesk.com`.
5. **Chromium missing after a box rebuild:** `venv/bin/python -m playwright install --with-deps chromium`.

---

## 9. Code map

```
backend/integrations/ds_crm/
  auth.py            headless-Chromium JWT mint (self-refresh, 401-retry)
  client.py          CredidekClient — _get/_post, iter_customers/processos/leads
  ingest_customers.py   → ds.clientes_real
  ingest_processos.py   → ds.processos_real
  ingest_leads.py       → ds.leads_real
  ingest_consent.py     → consent columns on ds.clientes_real  (needs migration 007)
backend/app/routers/   dashboard.py triggers.py chat.py recap.py newsletter.py broadcasts.py ...
migrations/            top-level at ~/ds-engine/migrations (NOT backend/migrations, which does
                       not exist). Files present: 001_schema, 002_contactos_consultor, 007_consent
                       (003–006 referenced historically but not on disk). 007 = consent columns;
                       applied in Clara_Production SQL editor.
```

DDL note: there are no Clara_Production management creds on the laptop, only the
service_role key (data-plane, no DDL). Migrations are applied by pasting the SQL
into the Supabase SQL editor for project `gpjcgkyvezgdunytkueu`.

---

## 10. API surface reference (CrediDesk)

Base `https://appapi.credidesk.com/api/v1`, auth `https://authapi.credidesk.com/api/v1`.
`/customers/list` (POST, paginated) is loja-wide; `/creditprocesses/list` and the
leads endpoint are scoped to the logged-in manager. `/customers/{id}` carries the
consent fields. Full table in `reference_ds_crm_credidesk` (Karim's notes).

---

## 11. In-app login (item 1) — deploy steps

> 📌 **Histórico** — já executado há muito. Os caminhos nginx aqui citados são os da
> antiga box AWS (`sites-available/ds-intelligence`); na Hetzner os sites são
> `sites-enabled/dscredito`, `dscredito-staging` e `dsloule`. Ler pelas variáveis e
> pela ordem das operações, não pelos caminhos.

The platform now authenticates itself with an in-app login screen instead of the
nginx HTTP basic-auth popup. This needs THREE production actions — do them in
this order, **only on an explicit "deploy" OK** (nginx + `.env` touch prod).

**a) Set the secrets in `.env`** (`~/ds-engine/backend/.env`):

```
APP_USER=ds
APP_PASSWORD=<APP_PASSWORD>                # the shared credential the team types
APP_USERS={"amin":"<senha-de-teste-do-amin>"}   # extra accounts (JSON); test logins
APP_SESSION_SECRET=<random 32+ bytes>   # e.g.  python3 -c "import secrets;print(secrets.token_urlsafe(48))"
```

`APP_USERS` is a JSON object of `username: password` merged with the primary
credential — use it for test logins (e.g. **amin**) without sharing the main one.
Add more later, e.g. `{"amin":"...","baptiste":"..."}`. Empty `APP_PASSWORD`+`APP_USERS`
or empty `APP_SESSION_SECRET` ⇒ login fails closed (nobody can log in) — so these
MUST be set before the nginx step, or the platform locks everyone out.

**Per-user accounts (migration 009).** Login now reads `ds.platform_users` first
and only falls back to `APP_USERS`/`APP_PASSWORD` for the `ds`/`amin` admin logins.
Bootstrap the per-user accounts (Bruno `bs`, Jorge `jg`) on deploy:

```
# 1) add to .env: a Fernet key (encrypts CRM passwords) + the service PIN
APP_CRYPTO_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
APP_SERVICE_PIN=28021904
# 2) apply migration 009 then seed (reads APP_USERS for platform pw, DS_CRM_* for Bruno's CRM creds)
python3 scripts/apply_migrations.py <host> <port> <user> <password>
python3 scripts/seed_platform_users.py
```

The seed is idempotent and never overwrites a password/CRM credential already set
via the **Configurações → Utilizadores** UI. The CRM-credentials tab ("Definições")
is gated by `APP_SERVICE_PIN`; CRM passwords are stored Fernet-encrypted and never
returned to the client in clear text.

**Per-user CRM scoping (migrations 010 + 011, phase 2).** Each processo/lead row is
tagged with `source_accounts text[]` = the set of platform accounts whose CrediDesk
login can see it (a row can be visible to several — e.g. shared leads). The read
routers filter `source_accounts @> {<username>}` so each gestor sees exactly their
CRM scope; `ds`/`amin` (not in platform_users) and role `admin`/`coordenador` see
loja-wide. `clientes_real` stays loja-wide (not scoped). The ingest scripts
(`ingest_processos.py`, `ingest_leads.py`) now loop over every active CRM account in
`platform_users` (two-pass merge) and mint each account's JWT in memory — they never
touch the shared `DS_CRM_JWT`.

IMPORTANT: `APP_CRYPTO_KEY` MUST be identical on every host that runs ingestion
(box + anywhere else), otherwise the stored CRM passwords can't be decrypted. Set it
once and copy the same value. After deploy, run `apply_migrations.py` (010+011) then
the two ingest scripts so `source_accounts` is populated.

**b) Deploy code + restart services** (scp the changed files, then):

```
sudo systemctl restart ds-intelligence            # backend: auth router + session middleware
cd ~/ds-engine/frontend && npm run build && sudo systemctl restart ds-intelligence-frontend
```

Smoke-test while basic-auth is still up (so it's safe):
`curl -u ds:<APP_PASSWORD> https://dscredito.synertia-gw.ai/api/dashboard/kpis` → 401 (no session cookie yet → middleware works).

**c) Remove the nginx basic-auth** (the popup), so the in-app screen is reached.
Edit `/etc/nginx/sites-available/ds-intelligence` and comment OUT the two
server-level lines:

```
#   auth_basic           "DS Intelligence";
#   auth_basic_user_file /etc/nginx/.htpasswd-ds;
```

Then `sudo nginx -t && sudo systemctl reload nginx`.

Verify: open https://dscredito.synertia-gw.ai → redirected to `/login` (no browser popup);
log in with `ds` / `<APP_PASSWORD>` → lands on the welcome page; "Sair" returns to login.

**Rollback:** un-comment the two nginx lines + `reload nginx` (the popup is back,
`.htpasswd-ds` was never removed). The app middleware is harmless behind basic-auth.

Notes:
- `/api/whatsapp` stays session-gated (it was already behind basic-auth; enabling
  inbound Meta callbacks publicly is a separate task with signature checks).
- Cookie `ds_session` is httpOnly + Secure + SameSite=Lax, signed (HMAC over the
  issued-at timestamp), 7-day max age; the Next middleware gates pages on its
  presence, the FastAPI middleware validates its signature on every `/api/*`.
- Per-user accounts / Coordenador-vs-Gestor roles are a later step (need the
  loja-coordinator login).

---

## 13. Última acção das leads + notas com lembrete (Ago 2026)

**a) Última acção (coluna na página de Leads).** A lista de leads do CrediDesk só
traz datas — `updatedon` diz *quando* alguém mexeu, nunca *o quê*. O teor da
intervenção vem de `POST /customerspotential/leads/historic/list`
(`{stateId:0, observation:"", customersPotentialLeadsId:<id>, typeId:0}`), o mesmo
que a ficha da lead mostra na aba "Atividade": `createdOn`, `observation`,
`stateName`, `typeId`, `agentName`. `ingest_leads.py` faz uma chamada por lead
depois do upsert da lista e guarda só o registo mais recente em
`leads_real.last_action_*` (migração **029**). `--sem-historico` salta essa fase.
`typeId`: 0 = nota do consultor, 1 = evento de sistema ("criou a lead", "arquivou
a Lead com o motivo: …"), -1 = arquivo automático, 3 = evento sem texto.

**b) Notas com data + lembrete.** Tabela `ds.lead_notas` (migração **030**),
router `/api/lead-notas`, painel no ícone de sino de cada linha da tabela de Leads.
Escreve **só na plataforma** — os workers CrediDesk continuam read-only (§3).
Visibilidade decidida com o cliente (3 Ago 2026): o lembrete avisa **quem o criou**;
quem tem perfil com `data_scope='loja'` (Diretor de Loja, admins) vê as notas todas.

O aviso tem dois canais: o sino da plataforma (componente `LembretesDock`, polling
de 60s, abre-se sozinho quando um lembrete vence com a app aberta) e email ao
próprio, enviado por `app/core/lembretes.py` a partir do `run_dispatcher.py` — vive
lá porque precisa da mesma cadência de minuto a minuto e assim não há mais uma
entrada de crontab para manter em cada loja. O email usa o mailer SES directo
(como a recuperação de password), **não** a fila `ds.envios`, que existe para
respeitar limites e opt-outs de destinatários externos.

**Aplicar (as duas lojas):** correr `migrations/029_leads_ultima_acao.sql` e
`030_lead_notas.sql` com `set search_path to ds` e depois `to dsl`. Feito a
3 Ago 2026 nos dois schemas.
