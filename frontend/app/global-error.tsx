'use client';
import { useEffect } from 'react';

/**
 * Rede de segurança para exceções que escapam a toda a árvore de componentes.
 *
 * O caso real que a motivou: a plataforma faz deploy automático de dois em dois
 * minutos, e quem tem um separador aberto quando o build muda fica com HTML que
 * pede pedaços de JavaScript que já não existem no servidor. O Next não sabe
 * recuperar disso e mostra "Application error: a client-side exception has
 * occurred" — um ecrã em branco para o utilizador, sem pista do que fazer.
 *
 * Aqui recarrega-se a página UMA vez (é isso que traz o build novo). A marca em
 * sessionStorage evita o ciclo infinito no caso de o erro ser mesmo do código:
 * à segunda, mostra-se a mensagem e o botão, em vez de recarregar para sempre.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    let jaTentou = true;
    try {
      jaTentou = sessionStorage.getItem('ds-recarregou-por-erro') === '1';
      if (!jaTentou) sessionStorage.setItem('ds-recarregou-por-erro', '1');
    } catch {
      /* sessionStorage bloqueado (modo privado): não recarrega, mostra a mensagem */
    }
    if (!jaTentou) window.location.reload();
  }, []);

  return (
    <html lang="pt">
      <body style={{ fontFamily: 'system-ui, sans-serif', padding: '3rem', color: '#1f2430' }}>
        <h1 style={{ fontSize: '1.25rem', fontWeight: 600 }}>A plataforma foi atualizada</h1>
        <p style={{ marginTop: '.75rem', color: '#5b6472' }}>
          Esta página ficou com uma versão antiga carregada. Estamos a recarregar — se não
          acontecer nada, use o botão abaixo.
        </p>
        <div style={{ marginTop: '1.5rem', display: 'flex', gap: '.75rem' }}>
          <button
            onClick={() => {
              try {
                sessionStorage.removeItem('ds-recarregou-por-erro');
              } catch { /* sem sessionStorage: recarrega na mesma */ }
              window.location.reload();
            }}
            style={{
              background: '#a91b60', color: '#fff', border: 0, borderRadius: '.75rem',
              padding: '.6rem 1.1rem', fontSize: '.9rem', cursor: 'pointer',
            }}
          >
            Recarregar
          </button>
          <button
            onClick={() => reset()}
            style={{
              background: 'transparent', color: '#5b6472', border: '1px solid #d8dde5',
              borderRadius: '.75rem', padding: '.6rem 1.1rem', fontSize: '.9rem', cursor: 'pointer',
            }}
          >
            Tentar continuar
          </button>
        </div>
        {error?.digest && (
          <p style={{ marginTop: '2rem', fontSize: '.75rem', color: '#9aa3b0' }}>
            Referência técnica: {error.digest}
          </p>
        )}
      </body>
    </html>
  );
}
