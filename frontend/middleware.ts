import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Gate every page on the presence of the session cookie (item 1). This only
// hides the UI; the real data gate is the backend, which validates the cookie's
// signature on every /api/* call. /api itself is proxied straight to the backend
// by nginx (never reaches this middleware), so we don't touch it here.
export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const authed = req.cookies.has('ds_session');

  if (pathname === '/login') {
    if (authed) {
      const url = req.nextUrl.clone();
      url.pathname = '/';
      url.search = '';
      return NextResponse.redirect(url);
    }
    return NextResponse.next();
  }

  // Public pages reachable when logged out (links opened from email).
  if (pathname === '/reset' || pathname === '/unsubscribe') {
    return NextResponse.next();
  }

  if (!authed) {
    const url = req.nextUrl.clone();
    url.pathname = '/login';
    url.search = '';
    url.searchParams.set('next', pathname);
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

// Run on everything except Next internals, the API proxy, and static assets.
export const config = {
  matcher: ['/((?!_next/static|_next/image|api/|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|ico|css|js|woff2?)$).*)'],
};
