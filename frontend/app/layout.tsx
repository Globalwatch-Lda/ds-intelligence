import './globals.css';
import type { Metadata, Viewport } from 'next';
import { Montserrat } from 'next/font/google';
import AppChrome from '../components/AppChrome';
import { LOJA_NAME } from '../lib/loja';

// Synertia brand typeface.
const montserrat = Montserrat({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-sans',
  display: 'swap',
});

export const metadata: Metadata = {
  title: `DS Matrix — ${LOJA_NAME}`,
  description: 'Plataforma de Inteligência Comercial para DS Crédito + DS Seguros',
};

// Garante o viewport (largura = dispositivo) para a app ser usável em
// telemóvel/tablet — sem isto o chrome responsivo (drawer/rail) não encaixa.
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-PT" className={montserrat.variable}>
      <body className="min-h-screen font-sans antialiased">
        <AppChrome>{children}</AppChrome>
      </body>
    </html>
  );
}
