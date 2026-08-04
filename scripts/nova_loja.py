"""Instalador de uma nova loja DS Matrix — do schema vazio ao site a servir.

Pergunta o essencial (número da loja, nome, subdomínio, credenciais CrediDesk) e
monta tudo o resto: schema + migrações, checkout, venv, .env, serviços systemd,
site nginx, entradas de cron e o utilizador inicial. O que não pode fazer sozinho
— o registo DNS e o certificado — fica dito no fim, em duas linhas.

    sudo python3 scripts/nova_loja.py                 # pergunta o que precisa
    sudo python3 scripts/nova_loja.py --dry-run       # mostra o plano, não toca em nada
    sudo python3 scripts/nova_loja.py --numero 812 --nome "DS Crédito Faro" \\
         --dominio dsfaro.synertia-gw.ai --crm-email a@b.pt --crm-password ...

PORQUÊ ESTE FICHEIRO: a Ramada e Loulé foram montadas à mão, e a diferença entre
as duas já custou uma tarde de diagnóstico (as credenciais do CRM estão no `.env`
numa e em `platform_users` na outra). Montar por script é o que garante que a
terceira e a décima ficam iguais — e que o que se aprendeu fica aqui, não na
memória de quem esteve lá.

SEGURANÇA: não inventa segredos partilhados. `APP_SESSION_SECRET` e
`APP_CRYPTO_KEY` são NOVOS por instalação (uma chave partilhada faria a sessão de
uma loja valer noutra); as chaves de serviço comuns (Supabase, Anthropic, email)
são copiadas do checkout de referência, que é a fonte de verdade da frota.
"""
from __future__ import annotations

import argparse
import getpass
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # para importar dns_netlify

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = "https://github.com/Globalwatch-Lda/ds-intelligence.git"
BASE_UBUNTU = Path("/home/ubuntu")
REFERENCIA = BASE_UBUNTU / "ds-engine"          # instalação de onde se copiam as chaves comuns
CHAVES_PARTILHADAS = (
    "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY", "ANTHROPIC_API_KEY",
    "SES_FROM", "SES_REGION", "SCALEWAY_TEM_TOKEN", "SCALEWAY_TEM_PROJECT_ID",
    "SCALEWAY_TEM_FROM", "APP_BASE_URL_DOMINIO_IGNORAR",
)
PORTA_API_INICIAL, PORTA_FRONT_INICIAL = 8008, 3008


class Passo:
    """Uma acção com nome, para o modo --dry-run listar o plano sem a executar."""

    def __init__(self, seco: bool):
        self.seco = seco

    def correr(self, descricao: str, fn, *args, **kwargs):
        if self.seco:
            print(f"  [plano] {descricao}")
            return None
        print(f"  → {descricao}")
        return fn(*args, **kwargs)


def sh(cmd: list[str] | str, **kw) -> str:
    """Executa e devolve stdout; levanta com o stderr se falhar."""
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"falhou: {cmd}\n{r.stderr.strip()[:400]}")
    return r.stdout.strip()


def perguntar(rotulo: str, valor: str | None, validar=None, segredo: bool = False) -> str:
    while True:
        v = valor or (getpass.getpass(f"{rotulo}: ") if segredo else input(f"{rotulo}: ").strip())
        if not v:
            valor = None
            print("   (obrigatório)")
            continue
        if validar and not validar(v):
            valor = None
            print("   (formato inválido)")
            continue
        return v


def portas_livres() -> tuple[int, int]:
    """Primeiro par de portas livres a partir de 8008/3008."""
    try:
        em_uso = sh("ss -ltn 2>/dev/null || netstat -ltn")
    except RuntimeError:
        em_uso = ""
    api, front = PORTA_API_INICIAL, PORTA_FRONT_INICIAL
    while f":{api}" in em_uso:
        api += 1
    while f":{front}" in em_uso:
        front += 1
    return api, front


def ler_env(caminho: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not caminho.exists():
        return out
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.strip().startswith("#"):
            k, v = linha.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def env_novo(cfg: dict, base: dict[str, str]) -> str:
    """.env da loja nova: chaves comuns copiadas, segredos próprios gerados."""
    from cryptography.fernet import Fernet

    linhas = [
        f"# DS Matrix — {cfg['nome']} (loja {cfg['numero']}). Gerado por scripts/nova_loja.py.",
        f"ENVIRONMENT=production",
        f"LOJA_NAME={cfg['nome']}",
        f"DB_SCHEMA={cfg['schema']}",
        f"APP_BASE_URL=https://{cfg['dominio']}",
        "",
        "# Ligação DDL: é com ela que o deploy aplica as migrações novas a esta loja.",
        f"DB_URL={cfg.get('db_url', '')}",
        "",
        "# Segredos PRÓPRIOS desta instalação — nunca partilhar com outra loja.",
        f"APP_SESSION_SECRET={secrets.token_urlsafe(48)}",
        f"APP_CRYPTO_KEY={Fernet.generate_key().decode()}",
        f"APP_SERVICE_PIN={secrets.randbelow(9000) + 1000}",
        "",
        "# Credenciais CrediDesk: ficam cifradas em platform_users (ver seed abaixo).",
        "# Deixadas aqui vazias de propósito — a fonte é a tabela, não o ficheiro.",
        "DS_CRM_USERNAME=",
        "DS_CRM_PASSWORD=",
        f"DS_CRM_AGENCY_ID={cfg['numero']}",
        "",
        "# Chaves de serviço partilhadas pela frota (copiadas da instalação de referência).",
    ]
    for k in CHAVES_PARTILHADAS:
        if k in base:
            linhas.append(f"{k}={base[k]}")
    return "\n".join(linhas) + "\n"


UNIT_API = """[Unit]
Description=DS Matrix {nome} API (FastAPI / uvicorn)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory={dir}/backend
ExecStart={dir}/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port {porta} --workers 1
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
"""

UNIT_FRONT = """[Unit]
Description=DS Matrix {nome} frontend (Next.js)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory={dir}/frontend
Environment=PORT={porta}
ExecStart=/usr/bin/npm run start -- --port {porta}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
"""

NGINX = """server {{
    server_name {dominio};
    client_max_body_size 5M;

    location /api/ {{
        proxy_pass http://127.0.0.1:{porta_api};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
    }}

    location / {{
        proxy_pass http://127.0.0.1:{porta_front};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    listen 80;
}}
"""

# Ingests desfasados: três lojas a puxar o CRM à mesma hora dão 401 e lentidão.
CRON = """# DS Matrix {nome} — ingestão CrediDesk + dispatcher + auto-deploy
{m0} {h} * * *  cd {dir}/backend && {dir}/backend/venv/bin/python integrations/ds_crm/ingest_customers.py >> /home/ubuntu/{slug}-sync.log 2>&1
{m1} {h} * * *  cd {dir}/backend && {dir}/backend/venv/bin/python integrations/ds_crm/ingest_processos.py >> /home/ubuntu/{slug}-sync.log 2>&1
{m2} {h} * * *  cd {dir}/backend && {dir}/backend/venv/bin/python integrations/ds_crm/ingest_leads.py >> /home/ubuntu/{slug}-sync.log 2>&1
{m3} {h2} * * 1 cd {dir}/backend && {dir}/backend/venv/bin/python integrations/ds_crm/ingest_consent.py --stale-days 7 >> /home/ubuntu/{slug}-sync.log 2>&1
* * * * * cd {dir}/backend && {dir}/backend/venv/bin/python scripts/run_dispatcher.py >> /home/ubuntu/{slug}-dispatch.log 2>&1
*/2 * * * * {dir}/auto-deploy.sh
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Instala uma nova loja DS Matrix nesta box.")
    ap.add_argument("--numero", help="agencyId da loja no CrediDesk (ex.: 812)")
    ap.add_argument("--nome", help='nome da loja (ex.: "DS Crédito Faro")')
    ap.add_argument("--dominio", help="ex.: dsfaro.synertia-gw.ai")
    ap.add_argument("--schema", help="schema na base (por omissão, derivado do domínio)")
    ap.add_argument("--crm-email", help="email da conta CrediDesk da loja")
    ap.add_argument("--crm-password", help="password dessa conta (pedida se faltar)")
    ap.add_argument("--db-url", help="ligação DDL (ou env DB_URL / cred/ddl.txt)")
    ap.add_argument("--dry-run", action="store_true", help="mostra o plano sem executar")
    ap.add_argument("--sem-ingest", action="store_true", help="não corre a primeira sincronização")
    args = ap.parse_args()

    print("\n=== Nova loja DS Matrix ===\n")
    numero = perguntar("Número da loja (agencyId do CrediDesk)", args.numero, lambda v: v.isdigit())
    nome = perguntar("Nome da loja", args.nome)
    dominio = perguntar("Domínio (ex.: dsfaro.synertia-gw.ai)", args.dominio,
                        lambda v: re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", v) is not None)
    crm_email = perguntar("Email da conta CrediDesk da loja", args.crm_email, lambda v: "@" in v)
    crm_password = perguntar("Password dessa conta", args.crm_password, segredo=True)

    # Convenção da frota, a partir do subdomínio (dsfaro.synertia-gw.ai):
    #   slug=faro · pasta ~/ds-engine-faro · serviços ds-faro/ds-faro-frontend · schema dsf…
    # O "ds" do subdomínio é retirado para o nome do serviço não ficar "ds-dsfaro"
    # — e, mais importante, para bater certo com o que o deploy.sh deriva da pasta.
    subdominio = re.sub(r"[^a-z0-9]", "", dominio.split(".")[0])
    slug = subdominio[2:] if subdominio.startswith("ds") and len(subdominio) > 2 else subdominio
    schema = args.schema or f"ds{slug}"[:20]
    destino = BASE_UBUNTU / f"ds-engine-{slug}"
    porta_api, porta_front = portas_livres()

    raiz_repo = Path(__file__).resolve().parents[1]
    ddl = raiz_repo / "cred" / "ddl.txt"
    db_url = args.db_url or (ddl.read_text().strip() if ddl.exists() else "")

    cfg = {"numero": numero, "nome": nome, "dominio": dominio, "schema": schema,
           "slug": slug, "dir": str(destino), "porta_api": porta_api,
           "porta_front": porta_front, "db_url": db_url}

    print(f"""
Resumo do que vai ser feito
  Loja ............. {nome} (agência {numero})
  Domínio .......... https://{dominio}
  Schema ........... {schema}
  Pasta ............ {destino}
  Portas ........... API {porta_api} · frontend {porta_front}
  Conta CRM ........ {crm_email}
""")
    if not args.dry_run and input("Continuar? [s/N] ").strip().lower() not in ("s", "sim", "y"):
        sys.exit("Cancelado.")

    p = Passo(args.dry_run)
    raiz = Path(__file__).resolve().parents[1]

    # --- 1. base de dados -------------------------------------------------
    print("\n[1/7] Base de dados")
    db_url = args.db_url or (raiz / "cred" / "ddl.txt").read_text().strip() if (raiz / "cred" / "ddl.txt").exists() else args.db_url
    p.correr(f"aplicar as migrações ao schema {schema}", lambda: print(sh(
        [sys.executable, str(raiz / "scripts" / "apply_migrations.py"), "--schema", schema,
         "--db-url", db_url])))

    # --- 2. checkout ------------------------------------------------------
    print("\n[2/7] Checkout e dependências")
    if destino.exists() and not args.dry_run:
        sys.exit(f"{destino} já existe — apague-a ou escolha outro domínio.")
    p.correr(f"clonar o repositório para {destino}",
             lambda: sh(["sudo", "-u", "ubuntu", "git", "clone", REPO, str(destino)]))
    p.correr("criar o venv e instalar as dependências", lambda: sh(
        f"sudo -u ubuntu python3 -m venv {destino}/backend/venv && "
        f"sudo -u ubuntu {destino}/backend/venv/bin/pip install -q -r {destino}/backend/requirements.txt"))
    p.correr("instalar o Chromium do Playwright (mint do JWT do CRM)", lambda: sh(
        f"sudo -u ubuntu {destino}/backend/venv/bin/playwright install chromium"))

    # --- 3. .env ----------------------------------------------------------
    print("\n[3/7] Configuração (.env)")
    base = ler_env(REFERENCIA / "backend" / ".env")
    if not base and not args.dry_run:
        print("  ! aviso: não encontrei o .env de referência — as chaves comuns ficam por preencher")
    p.correr("escrever o .env com segredos próprios desta loja",
             lambda: (destino / "backend" / ".env").write_text(env_novo(cfg, base), encoding="utf-8"))

    # --- 4. seed ----------------------------------------------------------
    print("\n[4/7] Dados iniciais")
    p.correr("registar a loja e criar o utilizador inicial", lambda: print(sh(
        [f"{destino}/backend/venv/bin/python", str(raiz / "scripts" / "seed_loja.py"),
         "--numero", numero, "--nome", nome, "--crm-email", crm_email,
         "--crm-password", crm_password], cwd=f"{destino}/backend")))

    # --- 5. serviços ------------------------------------------------------
    print("\n[5/7] Serviços")
    p.correr("build do frontend", lambda: sh(
        f"cd {destino}/frontend && sudo -u ubuntu npm ci --silent && sudo -u ubuntu npm run build"))
    p.correr(f"criar os serviços systemd (ds-{slug}, ds-{slug}-frontend)", lambda: (
        Path(f"/etc/systemd/system/ds-{slug}.service").write_text(
            UNIT_API.format(nome=nome, dir=destino, porta=porta_api)),
        Path(f"/etc/systemd/system/ds-{slug}-frontend.service").write_text(
            UNIT_FRONT.format(nome=nome, dir=destino, porta=porta_front)),
        sh("systemctl daemon-reload"),
        sh(f"systemctl enable --now ds-{slug} ds-{slug}-frontend"),
    ))

    # --- 6. DNS + nginx + certificado -------------------------------------
    print("\n[6/7] Site")
    # DNS antes do nginx: o certificado só se emite depois de o nome resolver.
    from dns_netlify import garantir_registo, token_disponivel  # noqa: E402

    token_dns = token_disponivel()
    ip_box = ""
    try:
        ip_box = sh("curl -s -4 --max-time 10 https://ifconfig.me || hostname -I | awk '{print $1}'")
    except RuntimeError:
        pass
    if token_dns and ip_box:
        ok, msg = garantir_registo(dominio, ip_box, token=token_dns, seco=args.dry_run)
        print(("  ✓ DNS: " if ok else "  ✗ DNS: ") + msg)
    else:
        print("  ! DNS por criar — sem token Netlify (/etc/ds-matrix/netlify.token) "
              f"ou sem IP. Criar à mão: A {dominio} -> {ip_box or '<ip da box>'}")
    p.correr(f"configurar o nginx para {dominio}", lambda: (
        Path(f"/etc/nginx/sites-available/{slug}").write_text(
            NGINX.format(dominio=dominio, porta_api=porta_api, porta_front=porta_front)),
        Path(f"/etc/nginx/sites-enabled/{slug}").exists() or shutil.os.symlink(
            f"/etc/nginx/sites-available/{slug}", f"/etc/nginx/sites-enabled/{slug}"),
        sh("nginx -t"),
        sh("systemctl reload nginx"),
    ))
    # Certificado: só se o DNS já resolver para esta box, senão o Let's Encrypt
    # falha a validação e deixa o site em HTTP. Quando o registo acabou de ser
    # criado, a propagação costuma ser de segundos — mas não se garante.
    p.correr(f"certificado Let's Encrypt para {dominio}", lambda: print(
        sh(f"certbot --nginx -n --agree-tos --redirect -d {dominio} "
           f"--email suporte@globalwatch.pt 2>&1 | tail -3")
        if sh(f"getent hosts {dominio} | awk '{{print $1}}' || true").strip() == ip_box
        else f"  ! DNS ainda não resolve para {ip_box} — correr depois: certbot --nginx -d {dominio}"))

    # --- 7. cron ----------------------------------------------------------
    print("\n[7/7] Tarefas automáticas")
    # Desfasa os ingests desta loja das que já lá estão (cada loja +20 min).
    lojas_existentes = len(list(BASE_UBUNTU.glob("ds-engine-*"))) if BASE_UBUNTU.exists() else 1
    minuto = (10 + 20 * lojas_existentes) % 60
    hora = 3 + (10 + 20 * lojas_existentes) // 60
    cron = CRON.format(nome=nome, dir=destino, slug=slug, h=hora, h2=hora + 1,
                       m0=minuto, m1=(minuto + 5) % 60, m2=(minuto + 10) % 60, m3=(minuto + 15) % 60)
    p.correr("acrescentar as entradas de cron do utilizador ubuntu", lambda: sh(
        f'(crontab -u ubuntu -l 2>/dev/null; echo "{cron}") | crontab -u ubuntu -'))

    if not args.sem_ingest:
        p.correr("primeira sincronização com o CRM (alguns minutos)", lambda: print(sh(
            f"cd {destino}/backend && venv/bin/python integrations/ds_crm/ingest_customers.py && "
            f"venv/bin/python integrations/ds_crm/ingest_processos.py && "
            f"venv/bin/python integrations/ds_crm/ingest_leads.py")))

    print(f"""
=== Instalação {'planeada' if args.dry_run else 'concluída'} ===

Ainda por confirmar:
  1. Expor o schema `{schema}` em Supabase → Settings → API → Exposed schemas
     (ou correr:  scripts/apply_migrations.py --schema {schema} --expor)
  2. Se o DNS ou o certificado ficaram por fazer (ver acima), tratar deles:
       python3 scripts/dns_netlify.py --dominio {dominio} --ip <ip>
       certbot --nginx -d {dominio}

Depois entre em https://{dominio} com o utilizador inicial que o passo 4 imprimiu
e confirme, na página de Leads, que só aparecem leads da agência {numero}.
""")


if __name__ == "__main__":
    main()
