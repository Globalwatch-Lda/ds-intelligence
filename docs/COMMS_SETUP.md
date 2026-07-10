# Comunicação multicanal — configuração e operação

A plataforma DS Matrix tem uma **camada de comunicação genérica**: Email, SMS e WhatsApp
são canais reutilizáveis para **qualquer** comunicação (plataforma → colaboradores,
plataforma → clientes), não só a newsletter. Este guia explica (1) que serviços
configurar e (2) como funciona no dia-a-dia.

- **Email** e **SMS** → **AWS** (SES e SNS/End User Messaging), em nome da **DS Crédito**.
- **WhatsApp (utilizador → cliente)** → **Evolution API** (self-hosted).
- Todos os envios passam por uma **fila com limites de lote + intervalos** (anti-alarme).

> Enquanto um serviço não estiver configurado, o canal fica **inerte**: a plataforma
> enfileira as mensagens mas **não entrega nada** e nunca rebenta por falta de credencial.
> Nada é enviado (nem faturado) até um gestor **ativar** o canal na tab *Comunicação*.

---

## 1. Serviços a configurar

Todas as variáveis vão para o `.env` do backend na box (`~/ds-engine/backend/.env`).
Em EC2, preferir **IAM role** na instância a chaves estáticas (o `boto3` usa a role
automaticamente).

### 1.1 Email — AWS SES
1. Na consola AWS **SES** (região, ex. `eu-west-1`): verificar o **domínio**
   `dscredito.pt` (registos **DKIM** + **SPF** no DNS) e configurar o **MAIL FROM**.
2. Pedir **saída do sandbox** SES (por defeito só envia para endereços verificados) —
   necessário para envios em massa.
3. Dar à IAM role da box a permissão `ses:SendEmail`.
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
2. Dar à IAM role a permissão `sns:Publish` (e as de End User Messaging, se aplicável).
3. `.env`:
   ```
   AWS_SMS_REGION=eu-west-1
   SMS_SENDER=DSCredito
   ```

### 1.3 WhatsApp — Evolution API (self-hosted)
1. Alojar uma instância **Evolution API** (container Docker na box ou num VPS) e ligar um
   **número WhatsApp dedicado** (leitura do QR code no arranque da instância).
2. `.env`:
   ```
   EVOLUTION_API_URL=https://evolution.o-teu-host
   EVOLUTION_API_KEY=<api key da instância>
   EVOLUTION_INSTANCE=<nome da instância>
   ```
   Faltando qualquer uma das três, o canal fica inerte.

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

### 2.3 Mensagens utilizador → cliente (WhatsApp/Evolution)
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
| `EVOLUTION_API_URL/API_KEY/INSTANCE` | WhatsApp | as três obrigatórias |

Tabelas: `ds.messaging_config` (limites por canal), `ds.envios` (fila + histórico).
Worker: `backend/scripts/run_dispatcher.py`. Código: `app/core/channels.py` (adaptadores),
`app/core/dispatcher.py` (fila/throttle), `app/routers/messaging.py` (API).
