/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: 'var(--clr-bg)',
        surface: 'var(--clr-surface)',
        surface2: 'var(--clr-surface-2)',
        border: 'var(--clr-border)',
        accent: 'var(--clr-accent)',
        'accent-glow': 'var(--clr-accent-glow)',
        ok: 'var(--clr-ok)',
        error: 'var(--clr-error)',
        text: 'var(--clr-text)',
        muted: 'var(--clr-muted)',
      },
      animation: {
        fadeSlideDown: 'fadeSlideDown 0.4s ease-out forwards',
        fadeSlideUp: 'fadeSlideUp 0.4s ease-out forwards',
      },
      keyframes: {
        fadeSlideDown: {
          '0%': { opacity: '0', transform: 'translateY(-16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeSlideUp: {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      }
    },
  },
  plugins: [],
}
