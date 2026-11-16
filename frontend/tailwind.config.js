/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Calm, accessible identity-product palette
        primary:  { DEFAULT: '#0F766E', dark: '#115E59', light: '#14B8A6' },
        accent:   { DEFAULT: '#4F46E5', light: '#818CF8' },
        success:  { DEFAULT: '#10B981', light: '#6EE7B7' },
        danger:   { DEFAULT: '#EF4444', light: '#FCA5A5' },
        warning:  { DEFAULT: '#F59E0B', light: '#FCD34D' },
        surface:  {
          900: '#F8FAFC',
          800: '#FFFFFF',
          700: '#F1F5F9',
          600: '#E2E8F0',
          500: '#CBD5E1',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      backdropBlur: { xs: '2px' },
      boxShadow: {
        glow:      '0 4px 14px rgba(15, 118, 110, 0.16)',
        'glow-lg': '0 8px 24px rgba(15, 118, 110, 0.2)',
        card:      '0 12px 32px rgba(15, 23, 42, 0.07)',
      },
      animation: {
        'pulse-slow':  'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow':   'spin 3s linear infinite',
        'bounce-slow': 'bounce 2s infinite',
        'fade-in':     'fadeIn 0.5s ease-in-out',
      },
      keyframes: {
        fadeIn: { '0%': { opacity: 0, transform: 'translateY(10px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
      },
    },
  },
  plugins: [],
}
