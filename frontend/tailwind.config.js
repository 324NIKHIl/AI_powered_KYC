
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],

  theme: {
    extend: {
      colors: {
        // VERIQO brand identity — Option A
        brand: {
          teal: '#0F8178',
          navy: '#101828',
          mint: '#DFF7F2',
          background: '#F5F8FA',
          white: '#FFFFFF',
          muted: '#64748B',
        },

        // Primary brand colours
        primary: {
          DEFAULT: '#0F8178',
          dark: '#115E59',
          light: '#14B8A6',
        },

        // Secondary cyan accent
        accent: {
          DEFAULT: '#19B9D2',
          light: '#67D9E8',
        },

        // Semantic status colours — preserved
        success: {
          DEFAULT: '#10B981',
          light: '#6EE7B7',
        },

        danger: {
          DEFAULT: '#EF4444',
          light: '#FCA5A5',
        },

        warning: {
          DEFAULT: '#F59E0B',
          light: '#FCD34D',
        },

        // Application surfaces
        surface: {
          900: '#F5F8FA',
          800: '#FFFFFF',
          700: '#F1F5F9',
          600: '#E2E8F0',
          500: '#CBD5E1',
        },
      },

      // Typography
      fontFamily: {
        sans: ['Manrope', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },

      // Blur effects
      backdropBlur: {
        xs: '2px',
      },

      // Shadows
      boxShadow: {
        glow: '0 4px 14px rgba(15, 129, 120, 0.16)',
        'glow-lg': '0 8px 24px rgba(15, 129, 120, 0.20)',
        card: '0 12px 32px rgba(16, 24, 40, 0.07)',
      },

      // Animations — preserved
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 3s linear infinite',
        'bounce-slow': 'bounce 2s infinite',
        'fade-in': 'fadeIn 0.5s ease-in-out',
      },

      // Keyframes — preserved
      keyframes: {
        fadeIn: {
          '0%': {
            opacity: 0,
            transform: 'translateY(10px)',
          },
          '100%': {
            opacity: 1,
            transform: 'translateY(0)',
          },
        },
      },
    },
  },

  plugins: [],
};
