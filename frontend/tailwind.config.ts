/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // TRACE-X Dark Investigator Theme
        'tracex-bg': '#0a0d14',
        'tracex-surface': '#111827',
        'tracex-card': '#1a2236',
        'tracex-border': '#1e293b',
        'tracex-accent': '#3b82f6',
        'tracex-accent-glow': '#60a5fa',
        'tracex-danger': '#ef4444',
        'tracex-warning': '#f59e0b',
        'tracex-success': '#10b981',
        'tracex-text': '#e2e8f0',
        'tracex-muted': '#64748b',
        'tracex-critical': '#dc2626',
        'tracex-high': '#ea580c',
        'tracex-medium': '#ca8a04',
        'tracex-low': '#16a34a',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      backgroundImage: {
        'grid-pattern': 'radial-gradient(circle, #1e293b 1px, transparent 1px)',
        'glow-accent': 'radial-gradient(ellipse at center, rgba(59,130,246,0.15) 0%, transparent 70%)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
        'slide-in': 'slideIn 0.3s ease-out',
        'fade-in': 'fadeIn 0.4s ease-out',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(59,130,246,0.3)' },
          '100%': { boxShadow: '0 0 20px rgba(59,130,246,0.6)' },
        },
        slideIn: {
          '0%': { transform: 'translateY(-10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
};
