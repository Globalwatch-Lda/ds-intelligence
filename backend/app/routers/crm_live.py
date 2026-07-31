"""Live CRM mirror — paginated + searchable view of ds.clientes_real."""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Query, Request

from ..core.names import fix_name
from ..core.scope import user_scope, apply_scope
from ..db import supabase

router = APIRouter()

# Columns read from clientes_real.
#  - manager_name is pulled out of the raw CrediDesk payload (raw->>managerName):
#    it is the loja-wide owning gestor and is NOT mirrored into a dedicated column.
#  - age is computed fresh from date_of_birth; the CRM's stored `age` field is
#    frozen at record creation and is wrong for ~2/3 of rows, so we never use it.
_SELECT = (
    "crm_id, name, email, telephone, tax_number, date_of_birth, "
    "created_on_crm, manager_name:raw->>managerName"
)


def _age_from_dob(dob: str | None) -> int | None:
    if not dob:
        return None
    try:
        d = date.fromisoformat(str(dob)[:10])
    except (ValueError, TypeError):
        return None
    today = date.today()
    return today.year - d.year - ((today.month, today.day) < (d.month, d.day))


def _process_info_map(sb, scope: dict | None = None) -> dict[int, dict]:
    """Latest process per customer (item 13 + tipo): state_name and type_name,
    keyed by customer_crm_id = clientes_real.crm_id, keeping the most recently
    updated process. Scoped to the logged-in user's profile (loja-wide for
    diretor_loja); clients with no visible process render as '—'."""
    q = apply_scope(
        sb.table("processos_real").select(
            "customer_crm_id, state_name, type_name, updated_on_crm, created_on_crm"
        ),
        scope,
    )
    rows = q.execute().data or []
    latest: dict[int, tuple[str, dict]] = {}  # cid -> (sort_key, {estado, tipo})
    for r in rows:
        cid = r.get("customer_crm_id")
        state = r.get("state_name")
        if cid is None or not state:
            continue
        key = r.get("updated_on_crm") or r.get("created_on_crm") or ""
        cur = latest.get(cid)
        if cur is None or key > cur[0]:
            latest[cid] = (key, {"estado": state, "tipo": r.get("type_name")})
    return {cid: v[1] for cid, v in latest.items()}


def _shape(row: dict, proc_map: dict[int, dict] | None = None) -> dict:
    info = (proc_map or {}).get(row.get("crm_id")) or {}
    return {
        "crm_id": row.get("crm_id"),
        "name": row.get("name"),
        "manager_name": fix_name(row.get("manager_name")),
        "email": row.get("email"),
        "telephone": row.get("telephone"),
        "tax_number": row.get("tax_number"),
        "age": _age_from_dob(row.get("date_of_birth")),
        "created_on_crm": row.get("created_on_crm"),
        "processo_estado": info.get("estado"),
        "processo_tipo": info.get("tipo"),
    }


def _select_all(sb, columns: str, page_size: int = 1000) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        chunk = (
            sb.table("clientes_real")
            .select(columns)
            .range(offset, offset + page_size - 1)
            .execute()
            .data
            or []
        )
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        offset += page_size
    return rows


@router.get("/estado")
def estado_sincronizacao(request: Request):
    """Saúde REAL do espelho do CRM, para o semáforo da interface.

    A página lê `clientes_real`, que é um espelho alimentado pelos workers noturnos
    — não é uma ligação viva ao CrediDesk. Logo, o que interessa mostrar não é
    "consigo falar com o CRM agora", é "os dados que estás a ver são recentes".

    O indicador estava pintado de verde no HTML, sempre. Teria dito "em direto"
    durante os dois dias de julho em que as três ingestões falharam todas as noites
    por falta do Chromium — que foi exatamente o período em que ninguém reparou.

      ok        última corrida de cada fonte sem erro e com menos de 26h
      atrasado  sem erros, mas os dados já têm mais de 26h (o cron é diário)
      falhou    a última corrida de alguma fonte registou erro
      sem_dados nunca correu / tabela de auditoria vazia
    """
    sb = supabase()
    fontes = ("credidesk_customers", "credidesk_processos", "credidesk_leads")
    agora = datetime.now(timezone.utc)
    ultimas: list[dict] = []
    for fonte in fontes:
        row = (
            sb.table("crm_sync_runs").select("source, started_at, error")
            .eq("source", fonte).order("started_at", desc=True).limit(1).execute().data or [None]
        )[0]
        if row:
            ultimas.append(row)

    if not ultimas:
        return {"estado": "sem_dados", "ok": False, "detalhe": "Nunca houve uma sincronização registada."}

    falhadas = [r for r in ultimas if r.get("error")]
    if falhadas:
        r = falhadas[0]
        return {
            "estado": "falhou", "ok": False,
            "ultima": r.get("started_at"),
            "fontes_com_erro": [x["source"] for x in falhadas],
            "detalhe": (r.get("error") or "")[:200],
        }

    def _idade(iso: str | None) -> float:
        if not iso:
            return 1e9
        try:
            t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
            return (agora - (t if t.tzinfo else t.replace(tzinfo=timezone.utc))).total_seconds() / 3600
        except ValueError:
            return 1e9

    mais_antiga = max(_idade(r.get("started_at")) for r in ultimas)
    atrasado = mais_antiga > 26  # o cron é diário; 26h dá folga ao horário de verão
    return {
        "estado": "atrasado" if atrasado else "ok",
        "ok": not atrasado,
        "ultima": min((r.get("started_at") for r in ultimas), key=lambda x: str(x)),
        "horas": round(mais_antiga, 1),
        "detalhe": f"Dados sincronizados há {mais_antiga:.0f}h." if atrasado else "Sincronizado nas últimas 24h.",
    }


@router.get("/filters")
def list_filter_options(request: Request):
    """Distinct gestores and process states, for the column filters in the
    CRM-live view (items 10 + 13). Process states/types reflect the logged-in
    gestor's scope; the gestor (manager) list stays loja-wide."""
    sb = supabase()
    scope = user_scope(request)
    clientes = _select_all(sb, "manager_name:raw->>managerName")
    managers = sorted({fix_name(c.get("manager_name")) for c in clientes if c.get("manager_name")})
    pq = apply_scope(sb.table("processos_real").select("state_name, type_name"), scope)
    proc = pq.execute().data or []
    estados = sorted({p.get("state_name") for p in proc if p.get("state_name")})
    tipos = sorted({p.get("type_name") for p in proc if p.get("type_name")})
    return {"managers": managers, "estados": estados, "tipos": tipos}


@router.get("/customers")
def list_customers(
    request: Request,
    q: str | None = Query(None, description="Search by name, email, NIF or telephone"),
    manager: str | None = Query(None, description="Filter by owning gestor (manager_name)"),
    estado: str | None = Query(None, description="Filter by latest process state"),
    tipo: str | None = Query(None, description="Filter by latest process type"),
    com_processo: bool = Query(False, description="Only clients that have a synced process"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    sb = supabase()
    proc_map = _process_info_map(sb, user_scope(request))

    q = (q or "").strip()
    manager = (manager or "").strip()
    estado = (estado or "").strip()
    tipo = (tipo or "").strip()

    # Any active filter → load the (small ~1.1k row) mirror and filter in Python
    # so search + gestor + estado compose cleanly. NIF/telephone match on
    # normalised digits (tax_number is numeric, telephone is mixed-format:
    # "+351 939 421 455" vs "967800337"), which a plain DB ilike would miss.
    if q or manager or estado or tipo or com_processo:
        ql = q.lower()
        q_digits = "".join(ch for ch in q if ch.isdigit())
        rows = _select_all(sb, _SELECT)

        def matches(r: dict) -> bool:
            if q:
                hit = (
                    ql in (r.get("name") or "").lower()
                    or ql in (r.get("email") or "").lower()
                )
                if not hit and q_digits:
                    nif = str(r.get("tax_number") or "")
                    tel = "".join(ch for ch in (r.get("telephone") or "") if ch.isdigit())
                    hit = q_digits in nif or q_digits in tel
                if not hit:
                    return False
            if manager and (fix_name(r.get("manager_name")) or "") != manager:
                return False
            info = proc_map.get(r.get("crm_id")) or {}
            estado_cliente = info.get("estado")
            if estado and estado_cliente != estado:
                return False
            if tipo and info.get("tipo") != tipo:
                return False
            if com_processo and not estado_cliente:
                return False
            return True

        filtered = [r for r in rows if matches(r)]
        filtered.sort(key=lambda r: r.get("created_on_crm") or "", reverse=True)
        page = filtered[offset : offset + limit]
        return {
            "total": len(filtered),
            "limit": limit,
            "offset": offset,
            "items": [_shape(r, proc_map) for r in page],
        }

    res = (
        sb.table("clientes_real")
        .select(_SELECT, count="exact")
        .order("created_on_crm", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return {
        "total": res.count or 0,
        "limit": limit,
        "offset": offset,
        "items": [_shape(r, proc_map) for r in (res.data or [])],
    }


@router.get("/customers/{crm_id}")
def customer_detail(crm_id: int):
    sb = supabase()
    res = (
        sb.table("clientes_real")
        .select("*")
        .eq("crm_id", crm_id)
        .limit(1)
        .execute()
    )
    row = (res.data or [None])[0]
    if row:
        row["age"] = _age_from_dob(row.get("date_of_birth"))
    return row
