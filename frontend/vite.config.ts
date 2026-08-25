import { defineConfig } from 'vite'

export default defineConfig({
  server: {
    host: '0.0.0.0',
    // Proxy same-origin requests from the browser to the local FastAPI server.
    // This avoids cross-port auth/CORS issues in Codespaces tunnels.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
