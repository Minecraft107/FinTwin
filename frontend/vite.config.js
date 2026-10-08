import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev server proxies /api to Flask so the browser sees one origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': process.env.VITE_PROXY_TARGET ?? 'http://localhost:5000',
    },
  },
})
