/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Neon-blue KYC brand palette
        primary:  { DEFAULT: '#00D4FF', dark: '#0099BB', light: '#80EAFF' },
        accent:   { DEFAULT: '#7C3AED', light: '#A78BFA' },
        success:  { DEFAULT: '#10B981', light: '#6EE7B7' },
        danger:   { DEFAULT: '#EF4444', light: '#FCA5A5' },
        warning:  { DEFAULT: '#F59E0B', light: '#FCD34D' },
        surface:  {
          900: '#0A0E1A',
          800: '#0F1629',
          700: '#151D3B',
          600: '#1E2A4A',
          500: '#263354',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      backdropBlur: { xs: '2px' },
      boxShadow: {
        glow:      '0 0 20px rgba(0, 212, 255, 0.3)',
        'glow-lg': '0 0 40px rgba(0, 212, 255, 0.4)',
        card:      '0 8px 32px rgba(0, 0, 0, 0.4)',
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
