# Comunicação multicanal — configuração e operação

A plataforma DS Matrix tem uma **camada de comunicação genérica**: Email, SMS e WhatsApp
são canais reutilizáveis para **qualquer** comunicação (plataforma → colaboradores,
plataforma → clientes), não só a newsletter. Este guia explica (1) que serviços
configurar e (2) como funciona no dia-a-dia.

- **Email** e **SMS** → **AWS** (SES e SNS/End User Messaging), em nome da **DS Crédito**.
- **WhatsApp** → dois canais independentes, ativáveis em separado ou em simultâneo:
  **Meta Cloud API** (número oficial da loja) e **Evolution API** (número de cada consultor).
- Todos os envios passam por uma **fila com limites de lote + intervalos** (anti-alarme).

> Enquanto um serviço não estiver configurado, o canal fica **inerte**: a plataforma
> enfileira as mensagens mas **não entrega nada** e nunca rebenta por falta de credencial.
> Nada é enviado (nem faturado) até um gestor **ativar** o canal na tab *Comunicação*.

---

## 1. Serviços a configurar

Todas as variáveis vão para o `.env` do backend no checkout respetivo
(`~/ds-engine/backend/.env`, Loulé em `~/ds-engine-loule/backend/.env`).
⚠️ A plataforma saiu da AWS para a **Hetzner** — já **não há IAM role** a fornecer
credenciais ao `boto3`. Email e SMS precisam agora de `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` (utilizador IAM só com `ses:SendEmail` + `sns:Publish`).

### 1.1 Email — AWS SES
1. Na consola AWS **SES** (região, ex. `eu-west-1`): verificar o **domínio**
   `dscredito.pt` (registos **DKIM** + **SPF** no DNS) e configurar o **MAIL FROM**.
2. Pedir **saída do sandbox** SES (por defeito só envia para endereços verificados) —
   necessário para envios em massa.
3. Dar ao utilizador IAM a permissão `ses:SendEmail` (ver nota acima — já não há role).
4. `.env`:
   ```
   SES_REGION=eu-west-1
   SES_FROM=DS Crédito <noreply@dscredito.pt>
   APP_BASE_URL=https://dscredito.synertia-gw.ai
   ```
   `SES_FROM` vazio = email **desligado** (modo dev: a recuperação de password mostra o
   link em staging em vez de o enviar).
5. **Asset**: colocar um PNG do logo em `frontend/public/ds-logo-email.png` (o email
   usa-o no cabeçalho; sem ele mostra o texto "DS Crédito").

### 1.2 SMS — AWS (SNS / End User Messaging)
1. Registar um **sender ID alfanumérico** ("DSCredito") e a **origination** para
   Portugal em **AWS End User Messaging** (ex-Pinpoint SMS). Sair do **sandbox SMS**.
2. Dar ao utilizador IAM a permissão `sns:Publish` (e as de End User Messaging, se aplicável).
3. `.env`:
   ```
   AWS_SMS_REGION=eu-west-1
   SMS_SENDER=DSCredito
   ```

### 1.3 WhatsApp — dois canais independentes

Há **dois** canais WhatsApp e podem estar **ativos ao mesmo tempo** (cada um com o seu
registo em `messaging_config`, o seu `ativo` e os seus limites). Não se misturam: são
credenciais, código e filas separados.

**a) `whatsapp_meta` — número oficial da loja (Meta Cloud API).** Envia sempre do mesmo
número verificado, sem QR. Fora da janela de 24h só entrega **templates aprovados**.
```
META_WA_PHONE_NUMBER_ID=<phone number id da app Meta>
META_WA_ACCESS_TOKEN=<System User token, sem expiração>
META_WA_API_VERSION=v21.0        # opcional
```

**b) `whatsapp_evolution` — número próprio de cada consultor (Evolution API).** Cada
utilizador liga o seu telemóvel por QR na página *WhatsApp*; as mensagens saem em nome
dele. O servidor Evolution é partilhado e vive **no assist** (ver `DEPLOY.md` §1.2).
```
EVOLUTION_API_URL=http://127.0.0.1:8088   # via túnel SSH para o assist
EVOLUTION_API_KEY=<AUTHENTICATION_API_KEY do servidor Evolution>
EVOLUTION_INSTANCE_PREFIX=ds_             # ds_ Ramada, dsl_ Loulé — único por loja
EVOLUTION_INSTANCE=<instância da loja>     # fallback opcional
```
Sem URL **ou** key, o canal fica inerte.

### 1.4 Worker de envio (cron)
A entrega faseada é feita por um worker que corre periodicamente. Adicionar ao cron da box:
```
* * * * * cd ~/ds-engine/backend && /usr/bin/python scripts/run_dispatcher.py >> ~/ds-dispatch.log 2>&1
```
O worker é *single-shot* (o cron define a cadência). Também há um botão **"Processar fila
agora"** na tab *Comunicação* para forçar um ciclo manualmente.

---

## 2. Como funciona (operação)

### 2.1 Limites por canal (tab Configurações → Comunicação)
Só quem tem a permissão **`messaging.config`** (Administrador / Diretor de Loja) vê esta tab.
Por cada canal define-se:
- **Ativo** — liga/desliga o canal. Inativo = enfileira mas não entrega.
- **Lote (nº/envio)** — quantas mensagens saem juntas.
- **Intervalo (s)** — segundos de espera entre lotes.
- **Limite diário** — teto de envios entregues por dia (por canal).
- **Remetente** — nome apresentado (ex. "DS Crédito" / "DSCredito").

**Exemplo:** lote 20, intervalo 3s → 20 mensagens, espera 3s, mais 20, etc. Com limite
diário 300, ao 300.º envio entregue o canal pára até ao dia seguinte. Isto espaça os
envios para **não disparar alarmes anti-spam**.

A fila mostra em tempo real os totais **pendentes / enviados / falhados**.

### 2.2 Newsletter
Na página *Newsletter*, quem pode gerar (permissão por utilizador) escolhe os **canais**
(Email / SMS) e carrega em **Enviar**. A newsletter é **colocada em fila** para a audiência
com consentimento de marketing (`clientes_real.authorized_contact = true`): Email para quem
tem email, SMS para quem tem telefone. A entrega é faseada pelos limites do canal.

### 2.3 Mensagens utilizador → cliente (WhatsApp)
Endpoint `POST /api/messaging/send` (permissão **`messaging.send`**): enfileira uma
mensagem para um ou mais destinatários num canal. Reutilizável para lembretes, campanhas,
avisos, etc. — o `ref_tipo` identifica o tipo (`newsletter`, `cliente`, `colaborador`,
`sistema`, …).

### 2.4 Recuperação de password
Usa o **canal Email** (SES). Assim que o SES estiver configurado, o link de reposição é
enviado por email com a imagem DS Crédito. Sem SES, em staging o link aparece no ecrã para
testar; em produção não é entregue (sem enumeração de contas).

---

## 3. Referência rápida — variáveis .env

| Variável | Serviço | Notas |
|---|---|---|
| `APP_BASE_URL` | (geral) | base dos links nos emails |
| `SES_REGION`, `SES_FROM` | Email | `SES_FROM` vazio = email desligado |
| `AWS_SMS_REGION`, `SMS_SENDER` | SMS | sender ID alfanumérico |
| `META_WA_PHONE_NUMBER_ID`, `META_WA_ACCESS_TOKEN` | WhatsApp Meta | número oficial da loja |
| `EVOLUTION_API_URL`, `EVOLUTION_API_KEY` | WhatsApp Evolution | ambas obrigatórias; `_INSTANCE_PREFIX` único por loja |

Tabelas: `ds.messaging_config` (limites por canal), `ds.envios` (fila + histórico).
Worker: `backend/scripts/run_dispatcher.py`. Código: o módulo empacotado
**`synertia-multicanal`** (checkout em `backend/multicanal/`, montado em
`app/main.py` via `app/multicanal_ctx.py`) — `channels.py` (adaptadores),
`meta_wa.py`/`evolution.py` (os dois WhatsApp), `dispatcher.py` (fila/throttle),
`router.py` (API). Os antigos `app/core/channels.py`, `app/core/evolution.py` e
`app/routers/messaging.py` do host ficaram **órfãos** — nenhum está montado.
