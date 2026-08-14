import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Gate every page on the session cookie (item 1). This only hides the UI; the
// real data gate is the backend, which validates the cookie's signature on
// every /api/* call. /api itself is proxied straight to the backend by nginx
// (never reaches this middleware), so we don't touch it here.

const COOKIE = 'ds_session';
const MAX_AGE = 7 * 24 * 3600; // igual ao MAX_AGE do backend (routers/auth.py)

/**
 * O cookie é `<iat>.<utilizador>.<assinatura>`. Aqui NÃO se valida a assinatura
 * — o APP_SESSION_SECRET vive só no backend, e é lá que ela é verificada em
 * cada /api/*. Valida-se o que se consegue sem segredo: o formato e a idade.
 *
 * Porque isto existe: até 14 ago 2026 bastava a PRESENÇA do cookie
 * (`cookies.has`). Um ds_session expirado ou truncado continuava presente,
 * portanto o /login redirecionava para / — e a pessoa ficava a ver uma app sem
 * dados (todos os /api/* a 401) SEM CONSEGUIR CHEGAR AO FORMULÁRIO DE LOGIN,
 * porque a única porta de saída redirecionava para dentro. Presença não é
 * validade.
 */
function sessaoUtilizavel(raw: string | undefined): boolean {
  if (!raw) return false;
  const partes = raw.split('.');
  if (partes.length < 3 || !partes[1] || !partes[2]) return false;
  const iat = Number(partes[0]);
  if (!Number.isInteger(iat)) return false;
  const idade = Math.floor(Date.now() / 1000) - iat;
  return idade >= 0 && idade <= MAX_AGE;
}

/** Um cookie que já não serve é APAGADO, senão volta a prender no pedido
 *  seguinte e o utilizador anda em círculos sem perceber porquê. */
function semCookie(res: NextResponse): NextResponse {
  res.cookies.delete(COOKIE);
  return res;
}

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const raw = req.cookies.get(COOKIE)?.value;
  const authed = sessaoUtilizavel(raw);
  const inutil = Boolean(raw) && !authed; // existe, mas expirado/malformado

  if (pathname === '/login') {
    if (authed) {
      const url = req.nextUrl.clone();
      url.pathname = '/';
      url.search = '';
      return NextResponse.redirect(url);
    }
    // Com sessão inválida deixa-se VER o login (era aqui que se ficava preso).
    return inutil ? semCookie(NextResponse.next()) : NextResponse.next();
  }

  // Public pages reachable when logged out (links opened from email).
  if (pathname === '/reset' || pathname === '/unsubscribe' || pathname.startsWith('/newsletter/')) {
    return NextResponse.next();
  }

  if (!authed) {
    const url = req.nextUrl.clone();
    url.pathname = '/login';
    url.search = '';
    url.searchParams.set('next', pathname);
    const res = NextResponse.redirect(url);
    return inutil ? semCookie(res) : res;
  }

  return NextResponse.next();
}

// Run on everything except Next internals, the API proxy, and static assets.
export const config = {
  matcher: ['/((?!_next/static|_next/image|api/|favicon.ico|.*\.(?:svg|png|jpg|jpeg|gif|ico|css|js|woff2?)$).*)'],
};
