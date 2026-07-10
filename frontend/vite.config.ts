import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Proxy: redireciona /api para o backend FastAPI.
    // O frontend chama /api/v1/... e o Vite repassa para localhost:8000.
    // Vantagem: sem CORS em desenvolvimento, sem hardcode de URL no código.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
