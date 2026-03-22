import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        greige: '#E8E3DC',
        surface: '#F4F0EC',
        accent: '#C4543A',
        'accent-dark': '#A83D28',
        ink: '#2B2018',
        'ink-muted': '#7A6A60',
        rose: '#E8B5AC',
        lavender: '#C3BDDF',
        sage: '#7BB3A6',
        'sage-light': '#D4EBE7',
      },
      fontFamily: {
        display: ['"DM Serif Display"', 'Georgia', 'serif'],
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      keyframes: {
        breathe: {
          '0%, 100%': {
            transform: 'scale(1)',
            boxShadow: '0 8px 40px rgba(196,84,58,0.35)',
          },
          '50%': {
            transform: 'scale(1.05)',
            boxShadow: '0 12px 60px rgba(196,84,58,0.55)',
          },
        },
        'slide-up': {
          '0%': { transform: 'translateY(100%)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(14px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'pulse-ring': {
          '0%': { transform: 'scale(1)', opacity: '0.6' },
          '100%': { transform: 'scale(1.5)', opacity: '0' },
        },
      },
      animation: {
        breathe: 'breathe 3s ease-in-out infinite',
        'slide-up': 'slide-up 0.35s cubic-bezier(0.16,1,0.3,1)',
        'fade-up': 'fade-up 0.45s ease forwards',
        shimmer: 'shimmer 1.6s linear infinite',
        'pulse-ring': 'pulse-ring 2s ease-out infinite',
      },
    },
  },
  plugins: [],
} satisfies Config
