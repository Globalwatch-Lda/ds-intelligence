// Ícones próprios da plataforma — os que o pacote @globalwatch-lda/synertia-ui não
// traz. Vivem aqui, e não dentro de um componente, porque são usados em mais do que
// um sítio: a barra lateral (AppChrome) e a grelha de cartões da home.
//
// Aceitam `className` para escalarem: 20px na sidebar, 36px nos cartões. Foi por
// não haver isto que a Análise Documental acabou a partilhar o IconReport com o
// Recap nos DOIS sítios — duplicar o SVG à mão convida a esquecer um deles.

export function IconDocScan({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M13 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4" />
      <path d="M13 3l4 4v3" />
      <circle cx="16" cy="15" r="3.5" />
      <path d="m18.6 17.6 2.4 2.4" />
    </svg>
  );
}
