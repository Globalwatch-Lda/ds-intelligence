'use client';
import { useEffect, useMemo, useState } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { api } from '../../lib/api';
import { useMe } from '../../lib/useMe';

type UserRow = { id: number; username: string; nome: string | null; role: string; manager_id: number | null; is_active: boolean };
type Acting = { id: number | null; role: string; loja_manager: boolean; can_manage: boolean };
type UsersResp = { users: UserRow[]; acting: Acting };
type Manager = { crm_id: number; nome: string | null };
type RoleOpt = { chave: string; nome: string; assignable: boolean };
type UserFull = {
  id: number; username: string; nome: string | null; telefone: string | null; email: string | null;
  role: string; manager_id: number | null; equipa_id: number | null; manager_crm_id: number | null;
  crm_username: string | null; crm_password_set: boolean; can_newsletter: boolean;
};
type Equipa = { id: number; nome: string; lider_id: number | null; lider_nome: string | null; membros: { id: number; nome: string | null; username: string; role: string }[] };

// `api()` lança "API <path> → <status>: <body>"; mostra-se o `detail` do FastAPI
// em vez do envelope inteiro.
function errDetail(e: any): string {
  const raw = String(e?.message ?? e ?? '');
  const body = raw.slice(raw.indexOf(': ') + 2);
  try { return JSON.parse(body)?.detail || raw; } catch { return raw; }
}

function Field({ label, ...props }: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink-500">{label}</span>
      <input
        {...props}
        className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm text-ink-900 focus:border-[color:var(--accent)] focus:outline-none focus:ring-1 focus:ring-[color:var(--accent)]"
      />
    </label>
  );
}

function Select({ label, children, ...props }: { label: string; children: React.ReactNode } & React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink-500">{label}</span>
      <select
        {...props}
        className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm text-ink-900 focus:border-[color:var(--accent)] focus:outline-none focus:ring-1 focus:ring-[color:var(--accent)]"
      >
        {children}
      </select>
    </label>
  );
}

// ---- User create/edit form ----------------------------------------------
function UserForm({
  mode, userId, acting, managers, roles, onSaved, onCancel,
}: {
  mode: 'create' | 'edit';
  userId: number | null;
  acting: Acting;
  managers: Manager[];
  roles: RoleOpt[];
  onSaved: () => void;
  onCancel: () => void;
}) {
  const { data: full } = useSWR<UserFull>(mode === 'edit' && userId ? `/api/settings/users/${userId}` : null, api);
  const lojaDir = acting.loja_manager;
  const roleLabel = useMemo(() => Object.fromEntries(roles.map((r) => [r.chave, r.nome])), [roles]);
  const assignable = roles.filter((r) => r.assignable);
  const [f, setF] = useState({
    username: '', password: '', nome: '', telefone: '', email: '',
    role: 'consultor',
    equipa_id: '' as string, manager_crm_id: '' as string,
    crm_username: '', crm_password: '', can_newsletter: false,
  });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Teams for the assignment dropdown (only loja managers assign teams here).
  const { data: teamsResp } = useSWR<{ equipas: Equipa[] }>(lojaDir ? '/api/equipas' : null, api);
  const equipas = teamsResp?.equipas ?? [];

  useEffect(() => {
    if (mode === 'edit' && full) {
      setF({
        username: full.username ?? '', password: '', nome: full.nome ?? '', telefone: full.telefone ?? '', email: full.email ?? '',
        role: full.role, equipa_id: full.equipa_id?.toString() ?? '', manager_crm_id: full.manager_crm_id?.toString() ?? '',
        crm_username: full.crm_username ?? '', crm_password: '', can_newsletter: !!full.can_newsletter,
      });
    }
  }, [mode, full]);
  // A system administrator account can't be restructured by a loja manager.
  const lockedRole = mode === 'edit' && full?.role === 'administrador' && acting.role !== 'administrador';
  const isConsultor = f.role === 'consultor';
  const isDiretorComercial = f.role === 'diretor_comercial';

  async function save() {
    setBusy(true); setMsg(null);
    const body: any = {
      username: f.username, nome: f.nome, telefone: f.telefone, email: f.email,
      role: f.role,
      manager_crm_id: isConsultor && f.manager_crm_id ? Number(f.manager_crm_id) : null,
      crm_username: f.crm_username || null,
    };
    if (lojaDir) {
      body.can_newsletter = f.can_newsletter;
      body.equipa_id = f.equipa_id ? Number(f.equipa_id) : null;
    }
    if (f.password) body.password = f.password;
    if (f.crm_password) body.crm_password = f.crm_password;
    try {
      if (mode === 'create') {
        if (!f.password) { setMsg('Palavra-passe obrigatória.'); setBusy(false); return; }
        await api('/api/settings/users', { method: 'POST', body: JSON.stringify(body) });
      } else {
        await api(`/api/settings/users/${userId}`, { method: 'PUT', body: JSON.stringify(body) });
      }
      setMsg('✓ Guardado.');
      onSaved();
    } catch (e: any) {
      setMsg(`Erro: ${e.message}`);
    } finally { setBusy(false); }
  }

  if (mode === 'edit' && !full) return <p className="text-sm text-ink-400">A carregar …</p>;

  return (
    <div className="max-w-md space-y-4">
      <h3 className="text-sm font-semibold text-ink-900">{mode === 'create' ? 'Novo utilizador' : 'Editar utilizador'}</h3>
      <Field label="Utilizador (username de acesso)" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} autoComplete="off" />
      <Field label={mode === 'create' ? 'Palavra-passe' : 'Palavra-passe (vazio = manter)'} type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
      <Field label="Nome" value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} />
      <Field label="Telemóvel" value={f.telefone} onChange={(e) => setF({ ...f, telefone: e.target.value })} />
      <Field label="Email" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />

      {assignable.length > 0 && !lockedRole ? (
        <Select label="Perfil" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
          {/* keep the current role selectable even if not in the assignable set */}
          {!assignable.some((r) => r.chave === f.role) && (
            <option value={f.role}>{roleLabel[f.role] ?? f.role}</option>
          )}
          {assignable.map((r) => <option key={r.chave} value={r.chave}>{r.nome}</option>)}
        </Select>
      ) : (
        <p className="text-xs text-ink-500">Perfil: <span className="font-medium">{roleLabel[f.role] ?? f.role}</span></p>
      )}

      {isConsultor && (
        <>
          <Select label="Gestor no CRM (define os processos que vê)" value={f.manager_crm_id} onChange={(e) => setF({ ...f, manager_crm_id: e.target.value })}>
            <option value="">— selecionar —</option>
            {managers.map((m) => <option key={m.crm_id} value={m.crm_id}>{m.nome ?? m.crm_id}</option>)}
          </Select>
          {lojaDir && (
            <Select label="Equipa" value={f.equipa_id} onChange={(e) => setF({ ...f, equipa_id: e.target.value })}>
              <option value="">— sem equipa —</option>
              {equipas.map((eq) => <option key={eq.id} value={eq.id}>{eq.nome}{eq.lider_nome ? ` (${eq.lider_nome})` : ''}</option>)}
            </Select>
          )}
        </>
      )}

      <div className="space-y-3 rounded-lg border border-ink-200 bg-ink-50/50 p-3">
        <p className="text-xs font-medium text-ink-600">
          Credenciais CRM (CrediDesk)
          {isConsultor && <span className="font-normal text-ink-400"> — opcional; o âmbito do Consultor vem do gestor acima</span>}
          {isDiretorComercial && <span className="font-normal text-ink-400"> — necessárias para ingerir os dados da equipa deste diretor</span>}
        </p>
        <Field label="Utilizador CRM (email)" value={f.crm_username} onChange={(e) => setF({ ...f, crm_username: e.target.value })} autoComplete="off" />
        <Field label={full?.crm_password_set ? 'Palavra-passe CRM (definida — vazio = manter)' : 'Palavra-passe CRM'} type="password" autoComplete="new-password" value={f.crm_password} onChange={(e) => setF({ ...f, crm_password: e.target.value })} />
      </div>

      {lojaDir && (
        <label className="flex items-start gap-3 rounded-lg border border-ink-200 bg-white p-3">
          <input
            type="checkbox"
            checked={f.can_newsletter}
            onChange={(e) => setF({ ...f, can_newsletter: e.target.checked })}
            className="mt-0.5 h-4 w-4 accent-[color:var(--accent)]"
          />
          <span className="text-sm">
            <span className="font-medium text-ink-900">Pode gerar newsletters</span>
            <span className="mt-0.5 block text-xs text-ink-400">
              Se desligado, este utilizador só consulta a última newsletter e o histórico de envios.
            </span>
          </span>
        </label>
      )}

      <div className="flex items-center gap-3">
        <button onClick={save} disabled={busy} className="btn-primary">{busy ? 'A guardar …' : 'Guardar'}</button>
        <button onClick={onCancel} className="btn-ghost">Cancelar</button>
        {msg && <span className="text-sm text-ink-500">{msg}</span>}
      </div>
    </div>
  );
}

// ---- Sincronizar CRM ------------------------------------------------------
type SyncRun = { finished_at: string | null; rows_upserted: number | null; error: string | null } | null;
function SyncBar() {
  const { data, mutate } = useSWR<{ processos: SyncRun; leads: SyncRun; running: boolean }>(
    '/api/settings/sync/status', api, { refreshInterval: (d) => (d?.running ? 4000 : 0) },
  );
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const running = !!data?.running;

  async function run() {
    setBusy(true); setMsg(null);
    try {
      await api('/api/settings/sync', { method: 'POST' });
      setMsg('Sincronização iniciada — pode demorar 1–2 min.');
      setTimeout(mutate, 1500);
    } catch (e: any) {
      setMsg(/409/.test(e.message) ? 'Já existe uma sincronização em curso.' : `Erro: ${e.message}`);
    } finally { setBusy(false); }
  }

  const p = data?.processos, l = data?.leads;
  const last = !running && p?.finished_at
    ? `Última sincronização: ${p?.rows_upserted ?? '—'} processos / ${l?.rows_upserted ?? '—'} leads`
    : null;
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-ink-200 bg-ink-50/50 px-3 py-2">
      <button onClick={run} disabled={busy || running} className="btn-primary">
        {running ? 'A sincronizar …' : 'Sincronizar CRM'}
      </button>
      <span className="text-xs text-ink-500">
        {running ? 'Em curso …' : last ?? 'Corre a ingestão para etiquetar os dados de um novo Diretor Comercial.'}
        {p?.error && <span className="text-ds-700"> · último erro registado</span>}
      </span>
      {msg && <span className="text-xs text-ink-400">{msg}</span>}
    </div>
  );
}

// ---- Utilizadores tab ----------------------------------------------------
function UtilizadoresTab({ canSync }: { canSync: boolean }) {
  const { data, mutate } = useSWR<UsersResp>('/api/settings/users', api);
  const { data: mgrs } = useSWR<{ managers: Manager[] }>('/api/settings/managers', api);
  const { data: rolesResp } = useSWR<{ roles: RoleOpt[] }>('/api/settings/roles', api);
  const [sel, setSel] = useState<number | 'new' | null>(null);
  const users = data?.users ?? [];
  const acting = data?.acting;
  const managers = mgrs?.managers ?? [];
  const roles = rolesResp?.roles ?? [];
  const roleLabel = useMemo(() => Object.fromEntries(roles.map((r) => [r.chave, r.nome])), [roles]);

  const canCreate = !!acting?.can_manage;
  const selUser = typeof sel === 'number' ? users.find((u) => u.id === sel) : undefined;
  const canDelete = !!(acting && selUser && selUser.id !== acting.id &&
    (acting.loja_manager ? selUser.role !== 'administrador' : selUser.manager_id === acting.id));

  async function del() {
    if (!selUser) return;
    if (!confirm(`Apagar o utilizador "${selUser.nome ?? selUser.username}"?`)) return;
    try {
      await api(`/api/settings/users/${selUser.id}`, { method: 'DELETE' });
      setSel(null); mutate();
    } catch (e: any) { alert(e.message); }
  }

  return (
    <div>
      {canSync && <SyncBar />}
      <div className="grid gap-6 md:grid-cols-[240px_1fr]">
      <nav className="space-y-1">
        <div className="flex items-center justify-between px-1 pb-1">
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-400">Utilizadores</span>
          {canCreate && (
            <button onClick={() => setSel('new')} className="rounded-md bg-[color:var(--accent)] px-2 py-0.5 text-xs font-medium text-white">+ Adicionar</button>
          )}
        </div>
        {users.map((u) => (
          <button
            key={u.id}
            onClick={() => setSel(u.id)}
            className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm ${sel === u.id ? 'bg-ink-100 font-medium text-ink-900' : 'text-ink-600 hover:bg-ink-50'}`}
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink-200 text-xs font-semibold text-ink-700">
              {(u.nome ?? u.username).split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase()}
            </span>
            <span className="min-w-0">
              <span className="block truncate">{u.nome ?? u.username}</span>
              <span className="block truncate text-[11px] text-ink-400">{roleLabel[u.role] ?? u.role}</span>
            </span>
          </button>
        ))}
        {!users.length && <p className="px-3 text-sm text-ink-400">Sem utilizadores.</p>}
      </nav>

      <section className="card">
        {sel === null && <p className="text-sm text-ink-400">Selecione um utilizador ou adicione um novo.</p>}
        {sel === 'new' && acting && (
          <UserForm mode="create" userId={null} acting={acting} managers={managers} roles={roles}
            onSaved={() => { setSel(null); mutate(); }} onCancel={() => setSel(null)} />
        )}
        {typeof sel === 'number' && acting && (
          <div className="space-y-4">
            <UserForm mode="edit" userId={sel} acting={acting} managers={managers} roles={roles}
              onSaved={() => mutate()} onCancel={() => setSel(null)} />
            {canDelete && (
              <div className="border-t border-ink-100 pt-4">
                <button onClick={del} className="rounded-lg border border-ds-200 px-3 py-1.5 text-sm text-ds-700 hover:bg-ds-50">Apagar utilizador</button>
              </div>
            )}
          </div>
        )}
      </section>
      </div>
    </div>
  );
}

// ---- Perfis tab ----------------------------------------------------------
type Perfil = { id: number; chave: string; nome: string; is_system: boolean; data_scope: string; permissoes: string[] };
type CapItem = { key: string; grupo: string; rotulo: string };
type ScopeItem = { key: string; rotulo: string };

function PerfisTab() {
  const { data: list, mutate } = useSWR<{ perfis: Perfil[] }>('/api/perfis', api);
  const { data: cat } = useSWR<{ capabilities: CapItem[]; data_scopes: ScopeItem[] }>('/api/perfis/catalog', api);
  const [sel, setSel] = useState<number | 'new' | null>(null);
  const perfis = list?.perfis ?? [];
  const caps = cat?.capabilities ?? [];
  const scopes = cat?.data_scopes ?? [];
  const grupos = useMemo(() => {
    const g: Record<string, CapItem[]> = {};
    caps.forEach((c) => { (g[c.grupo] ??= []).push(c); });
    return g;
  }, [caps]);

  const selPerfil = typeof sel === 'number' ? perfis.find((p) => p.id === sel) : undefined;

  const [f, setF] = useState<{ nome: string; data_scope: string; permissoes: Set<string> }>({ nome: '', data_scope: 'propria', permissoes: new Set() });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (sel === 'new') setF({ nome: '', data_scope: 'propria', permissoes: new Set() });
    else if (selPerfil) setF({ nome: selPerfil.nome, data_scope: selPerfil.data_scope, permissoes: new Set(selPerfil.permissoes) });
  }, [sel, selPerfil]);

  function toggle(key: string) {
    setF((prev) => {
      const next = new Set(prev.permissoes);
      next.has(key) ? next.delete(key) : next.add(key);
      return { ...prev, permissoes: next };
    });
  }

  async function save() {
    setBusy(true); setMsg(null);
    const body = { nome: f.nome, data_scope: f.data_scope, permissoes: [...f.permissoes] };
    try {
      if (sel === 'new') {
        const r = await api<{ id: number }>('/api/perfis', { method: 'POST', body: JSON.stringify(body) });
        setMsg('✓ Perfil criado.'); await mutate(); setSel(r.id);
      } else if (selPerfil) {
        await api(`/api/perfis/${selPerfil.id}`, { method: 'PUT', body: JSON.stringify(body) });
        setMsg('✓ Guardado.'); mutate();
      }
    } catch (e: any) { setMsg(`Erro: ${e.message}`); } finally { setBusy(false); }
  }

  async function del() {
    if (!selPerfil) return;
    if (!confirm(`Apagar o perfil "${selPerfil.nome}"?`)) return;
    try {
      await api(`/api/perfis/${selPerfil.id}`, { method: 'DELETE' });
      setSel(null); mutate();
    } catch (e: any) { alert(e.message); }
  }

  const editing = sel === 'new' || !!selPerfil;

  return (
    <div className="grid gap-6 md:grid-cols-[240px_1fr]">
      <nav className="space-y-1">
        <div className="flex items-center justify-between px-1 pb-1">
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-400">Perfis</span>
          <button onClick={() => setSel('new')} className="rounded-md bg-[color:var(--accent)] px-2 py-0.5 text-xs font-medium text-white">+ Novo</button>
        </div>
        {perfis.map((p) => (
          <button
            key={p.id}
            onClick={() => setSel(p.id)}
            className={`flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm ${sel === p.id ? 'bg-ink-100 font-medium text-ink-900' : 'text-ink-600 hover:bg-ink-50'}`}
          >
            <span className="truncate">{p.nome}</span>
            {p.is_system && <span className="shrink-0 rounded bg-ink-100 px-1.5 py-0.5 text-[10px] text-ink-400">sistema</span>}
          </button>
        ))}
      </nav>

      <section className="card">
        {!editing && <p className="text-sm text-ink-400">Selecione um perfil ou crie um novo.</p>}
        {editing && (
          <div className="max-w-lg space-y-4">
            <h3 className="text-sm font-semibold text-ink-900">{sel === 'new' ? 'Novo perfil' : `Editar — ${selPerfil?.nome}`}</h3>
            <Field label="Nome do perfil" value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} />
            <Select label="Âmbito de dados CRM" value={f.data_scope} onChange={(e) => setF({ ...f, data_scope: e.target.value })}>
              {scopes.map((s) => <option key={s.key} value={s.key}>{s.rotulo}</option>)}
            </Select>

            <div className="space-y-4">
              {Object.entries(grupos).map(([grupo, items]) => (
                <div key={grupo}>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-400">{grupo}</p>
                  <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                    {items.map((c) => (
                      <label key={c.key} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-ink-50">
                        <input
                          type="checkbox"
                          checked={f.permissoes.has(c.key)}
                          onChange={() => toggle(c.key)}
                          className="h-4 w-4 accent-[color:var(--accent)]"
                        />
                        <span className="text-ink-800">{c.rotulo}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="flex items-center gap-3">
              <button onClick={save} disabled={busy} className="btn-primary">{busy ? 'A guardar …' : 'Guardar'}</button>
              {selPerfil && !selPerfil.is_system && (
                <button onClick={del} className="rounded-lg border border-ds-200 px-3 py-1.5 text-sm text-ds-700 hover:bg-ds-50">Apagar</button>
              )}
              {msg && <span className="text-sm text-ink-500">{msg}</span>}
            </div>
            {selPerfil?.is_system && (
              <p className="text-xs text-ink-400">Perfil de sistema — pode editar permissões e âmbito, mas não apagar.</p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

// ---- Equipas tab ---------------------------------------------------------
type EquipasResp = {
  equipas: Equipa[];
  loja_admin: boolean;
  acting: { id: number | null };
  liders: { id: number; nome: string | null; username: string }[];
  consultores: { id: number; nome: string | null; username: string; equipa_id: number | null }[];
};

function EquipasTab() {
  const { data, mutate } = useSWR<EquipasResp>('/api/equipas', api);
  const [sel, setSel] = useState<number | 'new' | null>(null);
  const equipas = data?.equipas ?? [];
  const lojaAdmin = !!data?.loja_admin;
  const liders = data?.liders ?? [];
  const consultores = data?.consultores ?? [];
  const selTeam = typeof sel === 'number' ? equipas.find((e) => e.id === sel) : undefined;

  const [f, setF] = useState({ nome: '', lider_id: '' as string });
  const [addUser, setAddUser] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (sel === 'new') setF({ nome: '', lider_id: '' });
    else if (selTeam) setF({ nome: selTeam.nome, lider_id: selTeam.lider_id?.toString() ?? '' });
  }, [sel, selTeam]);

  async function save() {
    setBusy(true); setMsg(null);
    const body: any = { nome: f.nome };
    if (lojaAdmin) body.lider_id = f.lider_id ? Number(f.lider_id) : null;
    try {
      if (sel === 'new') {
        const r = await api<{ id: number }>('/api/equipas', { method: 'POST', body: JSON.stringify(body) });
        setMsg('✓ Equipa criada.'); await mutate(); setSel(r.id);
      } else if (selTeam) {
        await api(`/api/equipas/${selTeam.id}`, { method: 'PUT', body: JSON.stringify(body) });
        setMsg('✓ Guardado.'); mutate();
      }
    } catch (e: any) { setMsg(`Erro: ${e.message}`); } finally { setBusy(false); }
  }

  async function del() {
    if (!selTeam) return;
    if (!confirm(`Apagar a equipa "${selTeam.nome}"? Os membros ficam sem equipa.`)) return;
    try { await api(`/api/equipas/${selTeam.id}`, { method: 'DELETE' }); setSel(null); mutate(); }
    catch (e: any) { alert(e.message); }
  }

  async function addMembro() {
    if (!selTeam || !addUser) return;
    try {
      await api(`/api/equipas/${selTeam.id}/membros`, { method: 'POST', body: JSON.stringify({ user_id: Number(addUser) }) });
      setAddUser(''); mutate();
    } catch (e: any) { alert(e.message); }
  }

  async function removeMembro(uid: number) {
    if (!selTeam) return;
    try { await api(`/api/equipas/${selTeam.id}/membros/${uid}`, { method: 'DELETE' }); mutate(); }
    catch (e: any) { alert(e.message); }
  }

  const editing = sel === 'new' || !!selTeam;
  const podeAdicionar = consultores.filter((c) => c.equipa_id !== selTeam?.id);

  return (
    <div className="grid gap-6 md:grid-cols-[240px_1fr]">
      <nav className="space-y-1">
        <div className="flex items-center justify-between px-1 pb-1">
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-400">Equipas</span>
          {lojaAdmin && (
            <button onClick={() => setSel('new')} className="rounded-md bg-[color:var(--accent)] px-2 py-0.5 text-xs font-medium text-white">+ Nova</button>
          )}
        </div>
        {equipas.map((e) => (
          <button
            key={e.id}
            onClick={() => setSel(e.id)}
            className={`flex w-full flex-col rounded-lg px-3 py-2 text-left text-sm ${sel === e.id ? 'bg-ink-100 font-medium text-ink-900' : 'text-ink-600 hover:bg-ink-50'}`}
          >
            <span className="truncate">{e.nome}</span>
            <span className="truncate text-[11px] text-ink-400">
              {e.lider_nome ? `Líder: ${e.lider_nome}` : 'Sem líder'} · {e.membros.length} membro(s)
            </span>
          </button>
        ))}
        {!equipas.length && <p className="px-3 text-sm text-ink-400">Sem equipas.</p>}
      </nav>

      <section className="card">
        {!editing && <p className="text-sm text-ink-400">Selecione uma equipa ou crie uma nova.</p>}
        {editing && (
          <div className="max-w-lg space-y-4">
            <h3 className="text-sm font-semibold text-ink-900">{sel === 'new' ? 'Nova equipa' : `Editar — ${selTeam?.nome}`}</h3>
            <Field label="Nome da equipa" value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} />
            {lojaAdmin ? (
              <Select label="Líder (Diretor Comercial)" value={f.lider_id} onChange={(e) => setF({ ...f, lider_id: e.target.value })}>
                <option value="">— sem líder —</option>
                {liders.map((l) => <option key={l.id} value={l.id}>{l.nome ?? l.username}</option>)}
              </Select>
            ) : (
              <p className="text-xs text-ink-500">Líder: <span className="font-medium">{selTeam?.lider_nome ?? '—'}</span></p>
            )}

            <div className="flex items-center gap-3">
              <button onClick={save} disabled={busy} className="btn-primary">{busy ? 'A guardar …' : 'Guardar'}</button>
              {lojaAdmin && selTeam && (
                <button onClick={del} className="rounded-lg border border-ds-200 px-3 py-1.5 text-sm text-ds-700 hover:bg-ds-50">Apagar</button>
              )}
              {msg && <span className="text-sm text-ink-500">{msg}</span>}
            </div>

            {selTeam && (
              <div className="border-t border-ink-100 pt-4">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-400">Membros</p>
                {selTeam.membros.length === 0 ? (
                  <p className="text-sm text-ink-400">Sem membros.</p>
                ) : (
                  <ul className="divide-y divide-ink-100 text-sm">
                    {selTeam.membros.map((m) => (
                      <li key={m.id} className="flex items-center justify-between py-2">
                        <span>{m.nome ?? m.username}</span>
                        <button onClick={() => removeMembro(m.id)} className="text-xs text-ds-700 hover:underline">remover</button>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="mt-3 flex items-end gap-2">
                  <div className="flex-1">
                    <Select label="Adicionar consultor" value={addUser} onChange={(e) => setAddUser(e.target.value)}>
                      <option value="">— selecionar —</option>
                      {podeAdicionar.map((c) => <option key={c.id} value={c.id}>{c.nome ?? c.username}{c.equipa_id ? ' (noutra equipa)' : ''}</option>)}
                    </Select>
                  </div>
                  <button onClick={addMembro} disabled={!addUser} className="btn-ghost mb-0.5">Adicionar</button>
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

// ---- Comunicação tab -----------------------------------------------------
type CanalCfg = { canal: string; ativo: boolean; batch_size: number; intervalo_segundos: number; cap_diario: number; remetente: string | null };
type QueueResp = { pendentes: number; enviados: number; falhados: number; recent: { id: number; canal: string; destinatario: string; status: string; ref_tipo: string | null }[] };

const CANAL_LABEL: Record<string, string> = {
  email: 'Email', sms: 'SMS',
  whatsapp_meta: 'WhatsApp (Meta)', whatsapp_evolution: 'WhatsApp (Evolution)',
};
// Os dois canais WhatsApp são independentes e podem estar ativos ao mesmo tempo.
const CANAL_NOTA: Record<string, string> = {
  whatsapp_meta: 'Número oficial da loja, via Meta Cloud API. Fora da janela de 24h só entrega templates aprovados.',
  whatsapp_evolution: 'Número próprio de cada consultor, ligado por QR code na página WhatsApp.',
};

function CanalCard({ cfg, onSaved }: { cfg: CanalCfg; onSaved: () => void }) {
  const [f, setF] = useState<CanalCfg>(cfg);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => setF(cfg), [cfg]);

  async function save() {
    setBusy(true); setMsg(null);
    try {
      await api(`/api/messaging/config/${f.canal}`, {
        method: 'PUT',
        body: JSON.stringify({
          ativo: f.ativo, batch_size: Number(f.batch_size), intervalo_segundos: Number(f.intervalo_segundos),
          cap_diario: Number(f.cap_diario), remetente: f.remetente,
        }),
      });
      setMsg('✓ Guardado.'); onSaved();
    } catch (e: any) { setMsg(`Erro: ${e.message}`); } finally { setBusy(false); }
  }

  return (
    <div className="card space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-ink-900">{CANAL_LABEL[f.canal] ?? f.canal}</h3>
          {CANAL_NOTA[f.canal] && <p className="mt-0.5 text-xs text-ink-400">{CANAL_NOTA[f.canal]}</p>}
        </div>
        <label className="flex shrink-0 items-center gap-2 text-sm">
          <input type="checkbox" checked={f.ativo} onChange={(e) => setF({ ...f, ativo: e.target.checked })} className="h-4 w-4 accent-[color:var(--accent)]" />
          {f.ativo ? 'Ativo' : 'Inativo'}
        </label>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="Lote (nº/envio)" type="number" value={f.batch_size} onChange={(e) => setF({ ...f, batch_size: Number(e.target.value) })} />
        <Field label="Intervalo (s)" type="number" value={f.intervalo_segundos} onChange={(e) => setF({ ...f, intervalo_segundos: Number(e.target.value) })} />
        <Field label="Limite diário" type="number" value={f.cap_diario} onChange={(e) => setF({ ...f, cap_diario: Number(e.target.value) })} />
        <Field label="Remetente" value={f.remetente ?? ''} onChange={(e) => setF({ ...f, remetente: e.target.value })} />
      </div>
      <div className="flex items-center gap-3">
        <button onClick={save} disabled={busy} className="btn-primary">{busy ? 'A guardar …' : 'Guardar'}</button>
        {msg && <span className="text-sm text-ink-500">{msg}</span>}
      </div>
    </div>
  );
}

function ComunicacaoTab() {
  const { data, mutate } = useSWR<{ config: CanalCfg[] }>('/api/messaging/config', api);
  const { data: q, mutate: mutateQ } = useSWR<QueueResp>('/api/messaging/queue', api, { refreshInterval: 8000 });
  const [busy, setBusy] = useState(false);
  const canais = data?.config ?? [];

  async function dispatch() {
    setBusy(true);
    try { await api('/api/messaging/dispatch', { method: 'POST' }); await mutateQ(); }
    catch (e: any) { alert(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-ink-400">
        Canais de comunicação da plataforma (Email, SMS e os dois WhatsApp — Meta e Evolution,
        independentes um do outro). Os limites de lote e o intervalo
        entre lotes espaçam os envios para não disparar alarmes anti-spam. Um canal inativo (ou sem
        serviço configurado no servidor) enfileira mas não entrega.
      </p>

      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-ink-200 bg-ink-50/50 px-4 py-3 text-sm">
        <span><b className="text-ink-900">{q?.pendentes ?? '—'}</b> <span className="text-ink-500">pendentes</span></span>
        <span><b className="text-ink-900">{q?.enviados ?? '—'}</b> <span className="text-ink-500">enviados</span></span>
        <span><b className="text-ink-900">{q?.falhados ?? '—'}</b> <span className="text-ink-500">falhados</span></span>
        <button onClick={dispatch} disabled={busy} className="btn-ghost ml-auto">{busy ? 'A processar …' : 'Processar fila agora'}</button>
      </div>

      {canais.map((c) => <CanalCard key={c.canal} cfg={c} onSaved={() => mutate()} />)}
      {!canais.length && <p className="text-sm text-ink-400">A carregar …</p>}
    </div>
  );
}

// ---- Credenciais dos canais ----------------------------------------------
// Antes desta tab as credenciais só entravam pelo `.env` da box, à mão e com
// restart — o que obrigava a mexer no servidor por cada loja nova. O backend do
// módulo já as guardava em `multicanal_config` (sobrepõe-se ao env); faltava o ecrã.
// Segredos: o GET devolve booleano (definido/por definir), nunca o valor. Um campo
// deixado em branco PRESERVA o que lá está; para apagar há o "limpar" explícito.
type MCSettings = {
  ses_region: string; ses_from: string;
  scw_tem_secret_key: boolean; scw_tem_project_id: string; scw_tem_region: string;
  scw_tem_from: string; scw_tem_from_name: string;
  aws_sms_region: string; sms_sender: string;
  meta_wa_phone_number_id: string; meta_wa_access_token: boolean; meta_wa_api_version: string;
  evolution_api_url: string; evolution_api_key: boolean; evolution_instance: string;
  evolution_instance_prefix: string;
  _channels: Record<string, boolean>;
};

function Estado({ ok, ativo }: { ok: boolean; ativo?: boolean }) {
  // Três estados, não dois. Um canal com credenciais mas DESLIGADO não entrega
  // nada — mostrar só "configurado" fazia parecer que estava operacional.
  const [texto, cor] =
    !ok ? ['por configurar', 'bg-ink-100 text-ink-500']
    : ativo ? ['configurado · ativo', 'bg-green-100 text-green-700']
    : ['configurado · desligado', 'bg-amber-100 text-amber-700'];
  return <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${cor}`}>{texto}</span>;
}

function Segredo({
  label, definido, valor, onChange, onLimpar,
}: { label: string; definido: boolean; valor: string; onChange: (v: string) => void; onLimpar: () => void }) {
  return (
    <label className="block">
      <span className="mb-1 flex items-center gap-2 text-xs font-medium text-ink-500">
        {label}
        <span className={definido ? 'text-green-700' : 'text-ink-400'}>{definido ? '· definido' : '· por definir'}</span>
        {definido && <button type="button" onClick={onLimpar} className="text-ds-700 hover:underline">limpar</button>}
      </span>
      <input
        type="password" autoComplete="new-password" value={valor} onChange={(e) => onChange(e.target.value)}
        placeholder={definido ? '•••••••• (deixe vazio para manter)' : ''}
        className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm text-ink-900 focus:border-[color:var(--accent)] focus:outline-none focus:ring-1 focus:ring-[color:var(--accent)]"
      />
    </label>
  );
}

// Envio real de prova. O rótulo "configurado" só verifica que os campos estão
// preenchidos — não que o token é válido nem que a mensagem chega. Isto verifica.
function TesteCanal({ canal, placeholder, onSucesso }: { canal: string; placeholder: string; onSucesso?: () => void }) {
  const [dest, setDest] = useState('');
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<{ ok: boolean; texto: string } | null>(null);

  async function testar() {
    setBusy(true); setRes(null);
    try {
      const r = await api<{ entregue: boolean; erro: string | null }>('/api/messaging/settings/test', {
        method: 'POST', body: JSON.stringify({ canal, destinatario: dest.trim() }),
      });
      setRes(r.entregue
        ? { ok: true, texto: '✓ Entregue. O canal está operacional.' }
        : { ok: false, texto: r.erro || 'Não entregou, sem erro devolvido.' });
      if (r.entregue) onSucesso?.();
    } catch (e: any) { setRes({ ok: false, texto: errDetail(e) }); } finally { setBusy(false); }
  }

  return (
    <div className="border-t border-ink-100 pt-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-0 flex-1"><Field label="Enviar teste para" value={dest} onChange={(e) => setDest(e.target.value)} placeholder={placeholder} /></div>
        <button onClick={testar} disabled={busy || !dest.trim()} className="btn-ghost shrink-0">{busy ? 'A enviar …' : 'Testar'}</button>
      </div>
      {res && <p className={`mt-2 break-words text-xs ${res.ok ? 'text-green-700' : 'text-ds-700'}`}>{res.texto}</p>}
      <p className="mt-1 text-xs text-ink-400">Envia uma mensagem a sério, sem passar pela fila e mesmo com o canal desligado.</p>
    </div>
  );
}

// ---- Assistente de configuração do WhatsApp Meta -------------------------
// Os passos que a plataforma CONSEGUE verificar (credenciais preenchidas, teste
// entregue, canal ligado) são derivados dos endpoints que já existem — nunca de um
// visto do utilizador, senão o assistente diz "feito" sobre coisas que não estão.
// Os restantes acontecem todos dentro da Meta e ninguém daqui os pode confirmar,
// por isso são vistos manuais, guardados no servidor: isto leva dias e passa por
// mais do que uma pessoa.
type Passo = { id: string; titulo: string; fazer: React.ReactNode; produz?: string; auto?: boolean };

const PASSOS_META: Passo[] = [
  { id: 'numero', titulo: 'Arranjar um número dedicado',
    fazer: <>O número <b>não pode estar em uso no WhatsApp normal</b> — se estiver, tem de ser apagado dessa conta primeiro (perde-se o histórico). Tem de conseguir receber <b>SMS ou chamada</b>. Não use o telemóvel de um consultor: esses são para o WhatsApp Evolution.</>,
    produz: 'Um número livre, capaz de receber o código' },
  { id: 'app', titulo: 'Criar a app na Meta',
    fazer: <>Em <code>developers.facebook.com/apps</code> → <b>Create App</b> → nome e email → caso de uso <b>&quot;Connect with customers through WhatsApp&quot;</b> → escolher ou criar o <i>business portfolio</i> da empresa.</>,
    produz: 'A app, ligada ao portfolio da empresa' },
  { id: 'waba', titulo: 'Ligar a WhatsApp Business Account',
    fazer: <>Na app, <b>Start using the API</b>. No painel <b>API Setup</b>, ligar a uma WABA existente ou criar uma nova.</>,
    produz: 'A WABA — o contentor dos números e dos templates' },
  { id: 'verificar_numero', titulo: 'Adicionar e verificar o número',
    fazer: <>Adicionar o número, introduzir o código recebido por SMS/chamada e definir o <b>PIN de dois passos</b>. Guarde esse PIN: é pedido em operações futuras.</>,
    produz: 'Número verificado + Phone Number ID visível no API Setup' },
  { id: 'nome', titulo: 'Definir o nome de apresentação',
    fazer: <>É o nome que o cliente vê. Passa por revisão da Meta e tem de corresponder ao negócio real — um nome inventado é recusado.</>,
    produz: 'Nome aprovado' },
  { id: 'credenciais', titulo: 'Preencher as credenciais aqui em baixo', auto: true,
    fazer: <>Copiar o <b>Phone Number ID</b> e um <b>access token</b> do painel API Setup para a secção <i>WhatsApp Meta</i> desta página, e Guardar. Para começar serve o token temporário (24 h).</>,
    produz: 'Este passo fica ✓ sozinho quando os dois campos estiverem preenchidos' },
  { id: 'teste', titulo: 'Provar que entrega', auto: true,
    fazer: <>Usar o botão <b>Testar</b> da secção WhatsApp Meta com o seu próprio número. É o único passo que confirma que o token é válido e que a mensagem chega — o rótulo &quot;configurado&quot; só diz que os campos estão preenchidos.</>,
    produz: 'Fica ✓ sozinho após um teste entregue' },
  { id: 'token_permanente', titulo: 'Gerar o token permanente',
    fazer: <>O token temporário expira em 24 h. Em <b>Business Settings</b> → criar um <b>System User</b> → atribuir-lhe a app <b>e</b> a WABA com controlo total → gerar token com <code>business_management</code>, <code>whatsapp_business_messaging</code> e <code>whatsapp_business_management</code>. Substituir o temporário aqui em baixo.</>,
    produz: 'Token que não expira' },
  { id: 'pagamento', titulo: 'Adicionar método de pagamento',
    fazer: <>Sem ele não há envios reais além dos de teste. A Meta cobra por conversa <b>ao dono da WABA</b> — confirme que é a empresa certa a pagar.</>,
    produz: 'Conta apta a enviar' },
  { id: 'verificacao', titulo: 'Submeter a verificação do negócio',
    fazer: <>Documentos legais da empresa. Enquanto não estiver feita, os limites de envio são baixos. É a etapa mais demorada — submeta cedo.</>,
    produz: 'Limites de produção' },
  { id: 'templates', titulo: 'Aprovar templates',
    fazer: <>Só se pode enviar <b>texto livre nas 24 h seguintes a uma mensagem do cliente</b>. Fora dessa janela, apenas templates aprovados — necessários para campanhas e primeiros contactos. Envie-nos os textos e nós submetemo-los por API.</>,
    produz: 'Capacidade de iniciar conversa' },
  { id: 'ativar', titulo: 'Ativar o canal', auto: true,
    fazer: <>Na tab <b>Comunicação</b>, ligar o interruptor do cartão <i>WhatsApp (Meta)</i>. Até lá a plataforma enfileira mas não entrega.</>,
    produz: 'Fica ✓ sozinho quando o canal estiver ativo' },
];

function AssistenteMeta({ credenciaisOk, canalAtivo }: { credenciaisOk: boolean; canalAtivo: boolean }) {
  const { data, mutate } = useSWR<{ dados: Record<string, boolean> }>('/api/settings/setup/whatsapp_meta', api);
  const [aberto, setAberto] = useState<string | null>(null);
  const guardados = data?.dados ?? {};

  // Verdade derivada > visto manual: um passo verificável nunca depende de alguém
  // se lembrar de o marcar, nem pode ser marcado à mão quando não está feito.
  const feito = (p: Passo): boolean => {
    if (p.id === 'credenciais') return credenciaisOk;
    if (p.id === 'ativar') return canalAtivo;
    return !!guardados[p.id];
  };
  const concluidos = PASSOS_META.filter(feito).length;
  const pct = Math.round((concluidos / PASSOS_META.length) * 100);

  async function alternar(p: Passo) {
    if (p.auto) return;
    const novos = { ...guardados, [p.id]: !guardados[p.id] };
    mutate({ dados: novos }, false);
    try { await api('/api/settings/setup/whatsapp_meta', { method: 'PUT', body: JSON.stringify({ dados: novos }) }); }
    finally { mutate(); }
  }

  return (
    <div className="card space-y-4">
      <div>
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-sm font-semibold text-ink-900">Assistente de configuração — WhatsApp Meta</h3>
          <span className="shrink-0 text-sm font-semibold text-ink-700">{pct}%</span>
        </div>
        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-ink-100" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full rounded-full bg-[color:var(--accent)] transition-all duration-500" style={{ width: `${pct}%` }} />
        </div>
        <p className="mt-1.5 text-xs text-ink-400">{concluidos} de {PASSOS_META.length} passos · os assinalados com ✓ automático são verificados pela plataforma</p>
      </div>

      <ol className="divide-y divide-ink-100 rounded-lg border border-ink-100">
        {PASSOS_META.map((p, i) => {
          const ok = feito(p);
          const expandido = aberto === p.id;
          return (
            <li key={p.id}>
              <div className="flex items-start gap-3 px-3 py-2.5">
                <button
                  type="button" onClick={() => alternar(p)} disabled={p.auto}
                  title={p.auto ? 'Verificado automaticamente pela plataforma' : ok ? 'Marcar como por fazer' : 'Marcar como feito'}
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs font-bold ${
                    ok ? 'border-green-600 bg-green-600 text-white' : 'border-ink-300 text-transparent'
                  } ${p.auto ? 'cursor-default opacity-90' : 'hover:border-ink-500'}`}
                >✓</button>
                <button type="button" onClick={() => setAberto(expandido ? null : p.id)} className="min-w-0 flex-1 text-left">
                  <span className={`block text-sm ${ok ? 'text-ink-400 line-through' : 'text-ink-900'}`}>
                    <span className="text-ink-400">{i + 1}.</span> {p.titulo}
                    {p.auto && <span className="ml-2 rounded bg-ink-100 px-1.5 py-0.5 text-[10px] font-medium text-ink-500 no-underline">automático</span>}
                  </span>
                  {expandido && (
                    <span className="mt-2 block space-y-1.5">
                      <span className="block text-xs leading-relaxed text-ink-600">{p.fazer}</span>
                      {p.produz && <span className="block text-xs text-ink-400">→ {p.produz}</span>}
                    </span>
                  )}
                </button>
                <span className="shrink-0 text-xs text-ink-300">{expandido ? '−' : '+'}</span>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function CredenciaisTab() {
  const { data, mutate } = useSWR<MCSettings>('/api/messaging/settings', api);
  const { data: cfgCanais } = useSWR<{ config: CanalCfg[] }>('/api/messaging/config', api);
  const { mutate: revalidar } = useSWRConfig();

  // O passo "provar que entrega" do assistente não é um visto: é a consequência de
  // uma entrega mesmo confirmada pelo botão Testar.
  async function registarTesteMeta() {
    const chave = '/api/settings/setup/whatsapp_meta';
    try {
      const atual = await api<{ dados: Record<string, boolean> }>(chave);
      await api(chave, { method: 'PUT', body: JSON.stringify({ dados: { ...(atual.dados ?? {}), teste: true } }) });
      revalidar(chave);
    } catch { /* o teste passou; falhar a registar o progresso não é motivo de alarme */ }
  }
  const [f, setF] = useState<Record<string, string>>({});
  const [segredos, setSegredos] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!data) return;
    setF({
      ses_region: data.ses_region ?? '', ses_from: data.ses_from ?? '',
      scw_tem_project_id: data.scw_tem_project_id ?? '', scw_tem_region: data.scw_tem_region ?? '',
      scw_tem_from: data.scw_tem_from ?? '', scw_tem_from_name: data.scw_tem_from_name ?? '',
      aws_sms_region: data.aws_sms_region ?? '', sms_sender: data.sms_sender ?? '',
      meta_wa_phone_number_id: data.meta_wa_phone_number_id ?? '', meta_wa_api_version: data.meta_wa_api_version ?? '',
      evolution_api_url: data.evolution_api_url ?? '', evolution_instance: data.evolution_instance ?? '',
    });
    setSegredos({});
  }, [data]);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });

  async function guardar() {
    setBusy(true); setMsg(null);
    try {
      // Só os segredos EM QUE se mexeu seguem no pedido; os restantes ficam de fora
      // e o backend preserva-os (campo ausente ≠ campo vazio).
      await api('/api/messaging/settings', { method: 'PUT', body: JSON.stringify({ ...f, ...segredos }) });
      setMsg('✓ Guardado.'); mutate();
    } catch (e: any) { setMsg(errDetail(e)); } finally { setBusy(false); }
  }

  if (!data) return <p className="text-sm text-ink-400">A carregar …</p>;
  const ch = data._channels ?? {};
  const ativos: Record<string, boolean> = Object.fromEntries((cfgCanais?.config ?? []).map((c) => [c.canal, c.ativo]));
  const metaAtivo = !!ativos.whatsapp_meta;
  const desligados = ['email', 'sms', 'whatsapp_meta', 'whatsapp_evolution'].filter((c) => ch[c] && !ativos[c]);

  return (
    <div className="space-y-4">
      <AssistenteMeta credenciaisOk={!!ch.whatsapp_meta} canalAtivo={metaAtivo} />
      <p className="text-sm text-ink-400">
        Credenciais de cada canal. O que gravar aqui <b>sobrepõe-se</b> ao <code>.env</code> do servidor;
        um campo vazio cai para o valor do <code>.env</code>. Um canal só entrega depois de ter
        credenciais <b>e</b> de ser ativado na tab Comunicação.
      </p>
      {desligados.length > 0 && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <b>{desligados.length === 1 ? 'Um canal está' : `${desligados.length} canais estão`} configurado{desligados.length === 1 ? '' : 's'} mas desligado{desligados.length === 1 ? '' : 's'}</b> — não entregam nada.
          O botão <b>Testar</b> ignora o interruptor de propósito, para se poder validar as credenciais antes de ligar o canal a sério.
          Ligue-os na tab <b>Comunicação</b>.
        </p>
      )}

      <div className="card space-y-3">
        <div className="flex items-center justify-between"><h3 className="text-sm font-semibold text-ink-900">Email</h3><Estado ok={!!ch.email} ativo={!!ativos.email} /></div>
        <p className="text-xs text-ink-400">
          Há dois transportes. O <b>Scaleway TEM</b> é o da frota e o preferido: se estiver preenchido,
          é o usado. O <b>AWS SES</b> fica como alternativa — mas exige credenciais AWS no servidor,
          que deixaram de existir quando a plataforma saiu da AWS.
        </p>

        <div className="rounded-lg border border-ink-100 p-3 space-y-3">
          <p className="text-xs font-semibold text-ink-600">Scaleway TEM</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Project ID" value={f.scw_tem_project_id ?? ''} onChange={set('scw_tem_project_id')} />
            <Field label="Região" value={f.scw_tem_region ?? ''} onChange={set('scw_tem_region')} placeholder="fr-par" />
            <Field label="Remetente (domínio verificado)" value={f.scw_tem_from ?? ''} onChange={set('scw_tem_from')} placeholder="noreply@notify.synertia-gw.ai" />
            <Field label="Nome do remetente" value={f.scw_tem_from_name ?? ''} onChange={set('scw_tem_from_name')} placeholder="DS Crédito" />
          </div>
          <Segredo label="Chave secreta do TEM" definido={!!data.scw_tem_secret_key}
                   valor={segredos.scw_tem_secret_key ?? ''}
                   onChange={(v) => setSegredos({ ...segredos, scw_tem_secret_key: v })}
                   onLimpar={() => setSegredos({ ...segredos, scw_tem_secret_key: '' })} />
        </div>

        <div className="rounded-lg border border-ink-100 p-3 space-y-3">
          <p className="text-xs font-semibold text-ink-600">AWS SES <span className="font-normal text-ink-400">(alternativa)</span></p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Região SES" value={f.ses_region ?? ''} onChange={set('ses_region')} placeholder="eu-west-1" />
            <Field label="Remetente (From)" value={f.ses_from ?? ''} onChange={set('ses_from')} placeholder="DS Crédito <noreply@notify.synertia-gw.ai>" />
          </div>
        </div>

        <TesteCanal canal="email" placeholder="o.seu.email@exemplo.pt" />
      </div>

      <div className="card space-y-3">
        <div className="flex items-center justify-between"><h3 className="text-sm font-semibold text-ink-900">SMS (AWS SNS)</h3><Estado ok={!!ch.sms} ativo={!!ativos.sms} /></div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Região" value={f.aws_sms_region ?? ''} onChange={set('aws_sms_region')} placeholder="eu-west-1" />
          <Field label="Sender ID" value={f.sms_sender ?? ''} onChange={set('sms_sender')} placeholder="DSCredito" />
        </div>
        <TesteCanal canal="sms" placeholder="+3519XXXXXXXX" />
      </div>

      <div className="card space-y-3">
        <div className="flex items-center justify-between"><h3 className="text-sm font-semibold text-ink-900">WhatsApp Meta (Cloud API)</h3><Estado ok={!!ch.whatsapp_meta} ativo={!!ativos.whatsapp_meta} /></div>
        <p className="text-xs text-ink-400">Número oficial da loja. Cada loja tem de usar as SUAS credenciais — com as de outra, as mensagens saem pelo número dessa loja.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Phone Number ID" value={f.meta_wa_phone_number_id ?? ''} onChange={set('meta_wa_phone_number_id')} />
          <Field label="Versão da API" value={f.meta_wa_api_version ?? ''} onChange={set('meta_wa_api_version')} placeholder="v21.0" />
        </div>
        <Segredo label="Access token (System User)" definido={!!data.meta_wa_access_token}
                 valor={segredos.meta_wa_access_token ?? ''}
                 onChange={(v) => setSegredos({ ...segredos, meta_wa_access_token: v })}
                 onLimpar={() => setSegredos({ ...segredos, meta_wa_access_token: '' })} />
        <TesteCanal canal="whatsapp_meta" placeholder="351XXXXXXXXX" onSucesso={registarTesteMeta} />
      </div>

      <div className="card space-y-3">
        <div className="flex items-center justify-between"><h3 className="text-sm font-semibold text-ink-900">WhatsApp Evolution</h3><Estado ok={!!ch.whatsapp_evolution} ativo={!!ativos.whatsapp_evolution} /></div>
        <p className="text-xs text-ink-400">Número próprio de cada consultor, ligado por QR na página WhatsApp.</p>
        <Field label="URL do servidor" value={f.evolution_api_url ?? ''} onChange={set('evolution_api_url')} placeholder="http://127.0.0.1:8088" />
        <Segredo label="API key" definido={!!data.evolution_api_key}
                 valor={segredos.evolution_api_key ?? ''}
                 onChange={(v) => setSegredos({ ...segredos, evolution_api_key: v })}
                 onLimpar={() => setSegredos({ ...segredos, evolution_api_key: '' })} />
        <div>
          <span className="mb-1 block text-xs font-medium text-ink-500">Prefixo das instâncias</span>
          <p className="rounded-lg border border-ink-100 bg-ink-50 px-3 py-2 font-mono text-sm text-ink-700">{data.evolution_instance_prefix || '(por definir)'}</p>
          <p className="mt-1 text-xs text-ink-400">
            Não se edita: deriva do <b>número da loja</b> (tab Loja). É o que separa as instâncias
            desta loja das das outras no servidor partilhado. Sem número de loja, o canal fica inativo.
          </p>
        </div>
        <TesteCanal canal="whatsapp_evolution" placeholder="351XXXXXXXXX" />
      </div>

      <div className="flex items-center gap-3">
        <button onClick={guardar} disabled={busy} className="btn-primary">{busy ? 'A guardar …' : 'Guardar'}</button>
        {msg && <span className="text-sm text-ink-600">{msg}</span>}
      </div>
    </div>
  );
}

// ---- Módulos tab ---------------------------------------------------------
type ModuleState = {
  id: string; label: string; installed: boolean; locked: boolean;
  installed_version: string | null; available_version: string; channels: string[];
};
// As chaves vão tal e qual para POST /module/install. Os dois canais WhatsApp são
// independentes: instalar/ativar um não mexe no outro, e podem correr em paralelo.
const INSTALL_CANAIS: { key: string; label: string; nota?: string }[] = [
  { key: 'email', label: 'Email (AWS SES)' },
  { key: 'sms', label: 'SMS (AWS SNS)' },
  { key: 'whatsapp_meta', label: 'WhatsApp Meta (Cloud API)', nota: 'Número oficial da loja' },
  { key: 'whatsapp_evolution', label: 'WhatsApp Evolution', nota: 'Número próprio de cada consultor' },
];

function InstallModuleDialog({
  version, busy, onConfirm, onClose,
}: {
  version: string;
  busy: boolean;
  onConfirm: (channels: string[]) => void;
  onClose: () => void;
}) {
  const [sel, setSel] = useState<Set<string>>(new Set(INSTALL_CANAIS.map((c) => c.key)));
  const toggle = (k: string) => setSel((prev) => {
    const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); return n;
  });
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4" onClick={onClose} role="dialog" aria-modal="true">
      <div className="w-full max-w-md overflow-hidden rounded-xl border border-ink-100 bg-white text-ink-900 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="border-b border-ink-100 px-4 py-3">
          <h2 className="text-sm font-semibold">Instalar Comunicação Multicanal <span className="text-ink-400">v{version}</span></h2>
        </div>
        <div className="space-y-4 px-4 py-4">
          <p className="text-sm text-ink-500">Escolha os canais a instalar. Ficam desligados até os ativar na tab Comunicação. Pode voltar aqui mais tarde para <b>acrescentar</b> canais.</p>
          <div className="space-y-1.5">
            {INSTALL_CANAIS.map((c) => (
              <label key={c.key} className="flex items-start gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-ink-50">
                <input type="checkbox" checked={sel.has(c.key)} onChange={() => toggle(c.key)} className="mt-0.5 h-4 w-4 shrink-0 accent-[color:var(--accent)]" />
                <span>
                  <span className="block text-ink-800">{c.label}</span>
                  {c.nota && <span className="block text-xs text-ink-400">{c.nota}</span>}
                </span>
              </label>
            ))}
          </div>
          <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700">
            A instalação é <b>definitiva</b> — depois de instalado, o módulo não se desativa.
          </p>
          <div className="flex items-center justify-end gap-3">
            <button onClick={onClose} className="btn-ghost">Cancelar</button>
            <button
              onClick={() => onConfirm([...sel])}
              disabled={busy || sel.size === 0}
              className="btn-primary"
            >
              {busy ? 'A instalar …' : 'Confirmar instalação'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ModulosTab() {
  const { data, mutate } = useSWR<ModuleState>('/api/messaging/module', api);
  const [popup, setPopup] = useState(false);
  const [busy, setBusy] = useState(false);
  const m = data;

  async function install(channels: string[]) {
    setBusy(true);
    try {
      await api('/api/messaging/module/install', { method: 'POST', body: JSON.stringify({ channels }) });
      await mutate();
      setPopup(false);
    } catch (e: any) { alert(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-400">
        Módulos da plataforma. Ligue a checkbox para instalar; a instalação é definitiva
        (o módulo não se desativa).
      </p>

      <div className="card flex items-center justify-between gap-4">
        <label className="flex min-w-0 items-start gap-3">
          <input
            type="checkbox"
            checked={!!m?.installed}
            disabled={!m || m.installed}
            onChange={() => { if (m && !m.installed) setPopup(true); }}
            className="mt-0.5 h-4 w-4 accent-[color:var(--accent)]"
          />
          <span className="min-w-0">
            <span className="block font-medium text-ink-900">Comunicação Multicanal</span>
            <span className="mt-0.5 block text-xs text-ink-400">Email · SMS · WhatsApp Meta · WhatsApp Evolution</span>
          </span>
        </label>
        {/* O rótulo mostra a versão A CORRER (available_version), que é a que governa
            o comportamento. A `installed_version` é só um carimbo do momento em que as
            tabelas foram semeadas e fica para trás a cada atualização do módulo —
            mostrá-la aqui fazia parecer que a plataforma estava desatualizada. */}
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${m?.installed ? 'bg-green-100 text-green-700' : 'bg-ink-100 text-ink-400'}`}
              title={m?.installed_version ? `Instalado na v${m.installed_version}` : undefined}>
          {m?.installed ? `instalado v${m.available_version}` : m ? `disponível v${m.available_version}` : '…'}
        </span>
      </div>

      {popup && m && (
        <InstallModuleDialog version={m.available_version} busy={busy} onConfirm={install} onClose={() => setPopup(false)} />
      )}
    </div>
  );
}

// ---- Loja tab ------------------------------------------------------------
type LojaCfg = {
  numero: string | null; nome: string | null;
  analise_max_ficheiros: number | null; analise_max_file_mb: number | null;
};
type LojaCatalogo = { numero: string; nome: string };

function LojaTab({ canEdit }: { canEdit: boolean }) {
  const { me } = useMe();
  const superadmin = !!me?.is_superadmin;
  const { data, mutate } = useSWR<LojaCfg>('/api/settings/loja', api);
  const { data: cat, mutate: mutCat } = useSWR<{ lojas: LojaCatalogo[] }>('/api/settings/lojas', api);
  const lojas = cat?.lojas ?? [];
  const [f, setF] = useState({ numero: '', nome: '', analise_max_ficheiros: '', analise_max_file_mb: '' });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showCat, setShowCat] = useState(false);

  useEffect(() => {
    if (data) setF({
      numero: data.numero ?? '', nome: data.nome ?? '',
      analise_max_ficheiros: String(data.analise_max_ficheiros ?? ''),
      analise_max_file_mb: String(data.analise_max_file_mb ?? ''),
    });
  }, [data]);

  async function save() {
    setBusy(true); setMsg(null);
    try {
      await api('/api/settings/loja', { method: 'PUT', body: JSON.stringify({
        numero: f.numero, nome: f.nome,
        analise_max_ficheiros: f.analise_max_ficheiros === '' ? null : Number(f.analise_max_ficheiros),
        analise_max_file_mb: f.analise_max_file_mb === '' ? null : Number(f.analise_max_file_mb),
      }) });
      setMsg('✓ Loja atualizada.'); mutate();
    } catch (e: any) { setMsg(`Erro: ${e.message}`); } finally { setBusy(false); }
  }

  if (!data) return <p className="text-sm text-ink-400">A carregar …</p>;
  return (
    <section className="card max-w-md space-y-4">
      {/* Que loja É esta instalação. Fixa para todos; só o superadmin (sentinela)
          a troca, porque muda a identidade da instalação inteira. */}
      <div>
        <Select label="Loja (número do CrediDesk)" value={f.numero}
                onChange={(e) => setF({ ...f, numero: e.target.value })} disabled={!superadmin}>
          <option value="">— por definir —</option>
          {lojas.map((l) => <option key={l.numero} value={l.numero}>{l.numero} · {l.nome}</option>)}
          {/* Um número gravado que já não conste do catálogo continua visível,
              senão o select mostrava vazio e o guardar apagava-o sem se perceber. */}
          {f.numero && !lojas.some((l) => l.numero === f.numero) && (
            <option value={f.numero}>{f.numero} · (fora do catálogo)</option>
          )}
        </Select>
        {superadmin ? (
          <button onClick={() => setShowCat(true)} className="mt-1 text-xs text-ds-700 hover:underline">Gerir catálogo de lojas</button>
        ) : (
          <p className="mt-1 text-xs text-ink-400">Definida pela GlobalWatch. Fale connosco se estiver errada.</p>
        )}
      </div>
      <Field label="Nome da loja (aparece no cabeçalho)" value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} disabled={!canEdit} />

      <div className="pt-2 border-t border-ink-100">
        <p className="text-sm font-medium text-ink-700 mb-1">Análise documental — limites da leitura de ficheiros</p>
        <p className="text-xs text-ink-400 mb-3">Controlam o custo/cobertura da análise profunda (Fase 2).</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Máx. ficheiros por processo (1–50)" type="number" value={f.analise_max_ficheiros}
                 onChange={(e) => setF({ ...f, analise_max_ficheiros: e.target.value })} disabled={!canEdit} />
          <Field label="Tamanho máx. por ficheiro (MB, 0.5–32)" type="number" value={f.analise_max_file_mb}
                 onChange={(e) => setF({ ...f, analise_max_file_mb: e.target.value })} disabled={!canEdit} />
        </div>
      </div>

      {canEdit ? (
        <div className="flex items-center gap-3">
          <button onClick={save} disabled={busy} className="btn-primary">{busy ? 'A guardar …' : 'Guardar'}</button>
          {msg && <span className="text-sm text-ink-500">{msg}</span>}
        </div>
      ) : (
        <p className="text-xs text-ink-400">Sem permissão para alterar os dados da loja.</p>
      )}
      {showCat && <CatalogoLojasDialog lojas={lojas} atual={data.numero} onClose={() => setShowCat(false)} onChange={() => mutCat()} />}
    </section>
  );
}

// Catálogo partilhado por todas as instalações DS — só o superadmin lhe mexe.
// Mantido à mão de propósito: o CrediDesk não expõe a lista de agências (cada
// conta só alcança a sua), por isso não há de onde a importar.
function CatalogoLojasDialog({
  lojas, atual, onClose, onChange,
}: { lojas: LojaCatalogo[]; atual: string | null; onClose: () => void; onChange: () => void }) {
  const [novo, setNovo] = useState({ numero: '', nome: '' });
  const [msg, setMsg] = useState<string | null>(null);

  async function run(fn: () => Promise<any>) {
    setMsg(null);
    try { await fn(); onChange(); } catch (e: any) { setMsg(errDetail(e)); }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4" onClick={onClose} role="dialog" aria-modal="true">
      <div className="w-full max-w-lg rounded-xl border border-ink-100 bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-ink-900">Catálogo de lojas</h2>
          <button onClick={onClose} className="text-2xl leading-none text-ink-400 hover:text-ds-600">×</button>
        </div>
        <div className="space-y-4 px-4 py-4">
          <p className="text-xs text-ink-400">
            O número é o <b>agencyId do CrediDesk</b> e serve de chave — não se altera depois de criado.
            Esta lista é a mesma em todas as instalações DS.
          </p>
          <ul className="divide-y divide-ink-100 rounded-lg border border-ink-100">
            {lojas.map((l) => (
              <li key={l.numero} className="flex items-center gap-2 px-3 py-2">
                <span className="w-14 shrink-0 font-mono text-sm text-ink-500">{l.numero}</span>
                <input defaultValue={l.nome} onBlur={(e) => {
                  const nome = e.target.value.trim();
                  if (nome && nome !== l.nome) run(() => api(`/api/settings/lojas/${l.numero}`, { method: 'PUT', body: JSON.stringify({ numero: l.numero, nome }) }));
                }} className="min-w-0 flex-1 rounded-md border border-ink-200 px-2 py-1 text-sm" />
                {l.numero === atual ? (
                  <span className="shrink-0 text-xs text-ink-400">(esta instalação)</span>
                ) : (
                  <button onClick={() => { if (confirm(`Apagar a loja ${l.numero} — ${l.nome}?`)) run(() => api(`/api/settings/lojas/${l.numero}`, { method: 'DELETE' })); }}
                          className="shrink-0 text-xs text-ds-700 hover:underline">apagar</button>
                )}
              </li>
            ))}
            {!lojas.length && <li className="px-3 py-2 text-sm text-ink-400">Catálogo vazio.</li>}
          </ul>
          <div className="flex items-end gap-2">
            <Field label="Número" value={novo.numero} onChange={(e) => setNovo({ ...novo, numero: e.target.value })} />
            <Field label="Nome" value={novo.nome} onChange={(e) => setNovo({ ...novo, nome: e.target.value })} />
            <button disabled={!novo.numero.trim() || !novo.nome.trim()}
                    onClick={() => run(async () => { await api('/api/settings/lojas', { method: 'POST', body: JSON.stringify(novo) }); setNovo({ numero: '', nome: '' }); })}
                    className="btn-primary shrink-0">Adicionar</button>
          </div>
          {msg && <p className="text-sm text-ds-700">{msg}</p>}
        </div>
      </div>
    </div>
  );
}

// ---- Page ----------------------------------------------------------------
export default function ConfiguracoesPage() {
  const { can } = useMe();
  type Tab = 'utilizadores' | 'perfis' | 'equipas' | 'comunicacao' | 'credenciais' | 'modulos' | 'loja';
  const tabs: { key: Tab; label: string }[] = [
    { key: 'utilizadores', label: 'Utilizadores' },
    ...(can('teams.manage') ? [{ key: 'equipas' as Tab, label: 'Equipas' }] : []),
    ...(can('profiles.manage') ? [{ key: 'perfis' as Tab, label: 'Perfis' }] : []),
    ...(can('messaging.config') ? [{ key: 'comunicacao' as Tab, label: 'Comunicação' }] : []),
    ...(can('messaging.config') ? [{ key: 'credenciais' as Tab, label: 'Credenciais' }] : []),
    ...(can('messaging.config') ? [{ key: 'modulos' as Tab, label: 'Módulos' }] : []),
    { key: 'loja', label: 'Loja' },
  ];
  const [tab, setTab] = useState<Tab>('utilizadores');

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-ink-900">Configurações</h1>
        <p className="text-sm text-ink-400">Utilizadores, perfis e dados da loja.</p>
      </header>

      <div className="flex gap-2 border-b border-ink-100">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === t.key ? 'border-[color:var(--accent)] font-medium text-ink-900' : 'border-transparent text-ink-500 hover:text-ink-700'}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'utilizadores' && <UtilizadoresTab canSync={can('crm.sync')} />}
      {tab === 'equipas' && can('teams.manage') && <EquipasTab />}
      {tab === 'perfis' && can('profiles.manage') && <PerfisTab />}
      {tab === 'comunicacao' && can('messaging.config') && <ComunicacaoTab />}
      {tab === 'credenciais' && can('messaging.config') && <CredenciaisTab />}
      {tab === 'modulos' && can('messaging.config') && <ModulosTab />}
      {tab === 'loja' && <LojaTab canEdit={can('loja.edit')} />}
    </div>
  );
}
