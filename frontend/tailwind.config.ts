import type { Config } from 'tailwindcss';

const config: Config = {
  presets: [require('@globalwatch-lda/synertia-ui/tailwind-preset')],
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
    './node_modules/@globalwatch-lda/synertia-ui/src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // DS Intermediários de Crédito — actual brand magenta from the logo
        ds: {
          50:  '#fdf2f7',
          100: '#fbe2ed',
          200: '#f5c3da',
          500: '#a91b60',
          600: '#8e1551',
          700: '#741043',
          900: '#3f0623',
        },
        ink: {
          50:  '#f7f8fb',
          100: '#eef0f5',
          400: '#727a8a',
          700: '#1f2533',
          900: '#0c0f17',
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(15,23,42,.04), 0 4px 12px rgba(15,23,42,.04)',
      },
    },
  },
  plugins: [],
};
export default config;
