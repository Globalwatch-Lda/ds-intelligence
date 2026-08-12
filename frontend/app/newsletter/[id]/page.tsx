import { headers } from 'next/headers';
import { redirect } from 'next/navigation';
import { LOJA_NAME_FULL } from '../../../lib/loja';

const FALLBACK_URL = 'https://www.dsicredito.pt/pt/odivelas-jardim-da-amoreira';

export const dynamic = 'force-dynamic';

function mdToHtml(md: string): string {
  const lines = md.split('\n');
  let html = '';
  let inUl = false;
  for (const line of lines) {
    if (line.startsWith('### ')) {
      if (inUl) { html += '</ul>'; inUl = false; }
      html += `<h3 class="text-base font-semibold mt-4 mb-1">${line.slice(4)}</h3>`;
    } else if (line.startsWith('## ')) {
      if (inUl) { html += '</ul>'; inUl = false; }
      html += `<h2 class="text-lg font-semibold mt-5 mb-2 text-ds-700">${line.slice(3)}</h2>`;
    } else if (line.startsWith('# ')) {
      if (inUl) { html += '</ul>'; inUl = false; }
      html += `<h1 class="text-2xl font-bold mb-2 text-ink-900">${line.slice(2)}</h1>`;
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      if (!inUl) { html += '<ul class="list-disc pl-5 space-y-1 my-2">'; inUl = true; }
      html += `<li>${line.slice(2)}</li>`;
    } else if (line.trim() === '') {
      if (inUl) { html += '</ul>'; inUl = false; }
    } else if (line.trim() === '---') {
      if (inUl) { html += '</ul>'; inUl = false; }
      html += '<hr class="my-4 border-ink-100" />';
    } else {
      if (inUl) { html += '</ul>'; inUl = false; }
      html += `<p class="my-2 leading-relaxed">${line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>')}</p>`;
    }
  }
  if (inUl) html += '</ul>';
  return html;
}

async function getNewsletter(id: string) {
  const h = await headers();
  const host = h.get('x-forwarded-host') || h.get('host') || 'localhost:3005';
  const proto = h.get('x-forwarded-proto') || 'https';
  // The basic-auth header is forwarded by nginx; on the same origin we can fetch the API directly.
  const res = await fetch(`${proto}://${host}/api/newsletter/${id}`, {
    cache: 'no-store',
    headers: { cookie: h.get('cookie') || '', authorization: h.get('authorization') || '' },
  });
  if (!res.ok) return null;
  return res.json();
}

export default async function NewsletterDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const nl = await getNewsletter(id);

  if (!nl) {
    redirect(FALLBACK_URL);
  }

  return (
    <article className="max-w-2xl mx-auto bg-white rounded-2xl shadow-card p-8 prose max-w-none">
      <div dangerouslySetInnerHTML={{ __html: mdToHtml(nl.conteudo_md || '') }} />
      <hr className="my-6 border-ink-100" />
      <p className="text-xs text-ink-400">
        Newsletter da {LOJA_NAME_FULL}. Gerada em {new Date(nl.created_at).toLocaleDateString('pt-PT')}.
      </p>
    </article>
  );
}
