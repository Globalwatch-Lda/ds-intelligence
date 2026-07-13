'use client';
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { VERSION as UI_VERSION } from '@globalwatch-lda/synertia-ui';

// Diálogo "Sobre" da DS Matrix: versão da Plataforma, da Interface (UI) e dos
// módulos instalados com a respetiva versão. A versão do módulo Comunicação
// Multicanal vem do backend (GET /api/messaging/module — reportada pelo próprio
// pacote synertia-multicanal). Se o módulo ainda não estiver ligado, aparece como
// "não instalado" em vez de rebentar.
type ModuleRow = { id: string; label: string; version?: string; installed: boolean };

export function AboutDialog({
  open,
  onClose,
  platformVersion,
  buildSha,
}: {
  open: boolean;
  onClose: () => void;
  platformVersion: string;
  buildSha?: string;
}) {
  const [modules, setModules] = useState<ModuleRow[]>([]);
  useEffect(() => {
    if (!open) return;
    fetch('/api/messaging/module')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d) return;
        setModules([
          {
            id: d.id ?? 'multicanal',
            label: d.label ?? 'Comunicação Multicanal',
            version: d.installed ? d.installed_version : d.available_version,
            installed: !!d.installed,
          },
        ]);
      })
      .catch(() => {});
  }, [open]);

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Sobre a DS Matrix"
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-xl border border-ink-100 bg-white text-ink-900 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3">
          <h2 className="text-sm font-semibold">Sobre a DS Matrix</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-ink-400 hover:bg-ink-100"
            aria-label="Fechar"
          >
            ✕
          </button>
        </div>

        <div className="space-y-4 px-4 py-4 text-sm">
          <div className="space-y-1.5">
            <Row label="Plataforma" value={platformVersion} sub={buildSha ? `build ${buildSha}` : undefined} />
            <Row label="Interface" value={UI_VERSION} />
          </div>

          <div>
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-400">
              Módulos instalados
            </div>
            <ul className="divide-y divide-ink-100 overflow-hidden rounded-md border border-ink-100">
              {modules.map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-3 px-3 py-2">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{m.label}</div>
                    <div className="truncate text-xs text-ink-400">Email · SMS · WhatsApp</div>
                  </div>
                  <span className="shrink-0 rounded-full bg-ink-100 px-2 py-0.5 text-xs font-semibold text-ink-400">
                    {m.installed && m.version ? `v${m.version}` : 'não instalado'}
                  </span>
                </li>
              ))}
              {modules.length === 0 && (
                <li className="px-3 py-2 text-xs text-ink-400">Nenhum módulo instalado.</li>
              )}
            </ul>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

function Row({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-ink-400">{label}</span>
      <span className="font-mono">
        {value}
        {sub ? <span className="ml-2 text-xs text-ink-400">{sub}</span> : null}
      </span>
    </div>
  );
}
