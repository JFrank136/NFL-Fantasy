import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        turf: {
          DEFAULT: '#1f3d2b',
          light: '#2a533a',
          line: '#496f58',
        }
      }
    },
  },
  plugins: [],
} satisfies Config
