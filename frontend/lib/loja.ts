// Branding por instância — o nome da loja vem do env de BUILD (NEXT_PUBLIC_*),
// para o mesmo código servir várias lojas (Ramada, Loulé, …) só com env diferente.
// Sem env definido, os defaults mantêm o comportamento da instância original (Ramada).
const short = process.env.NEXT_PUBLIC_LOJA_NAME;

/** Nome curto da loja (cabeçalho/chrome), ex. "DS Crédito Ramada". */
export const LOJA_NAME = short ?? 'DS Crédito Ramada';

/** Nome completo (com localização), ex. "DS Crédito Ramada – Jardim da Amoreira". */
export const LOJA_NAME_FULL =
  process.env.NEXT_PUBLIC_LOJA_NAME_FULL ?? short ?? 'DS Crédito Ramada – Jardim da Amoreira';
