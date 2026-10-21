import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Shared contract cases live one directory above the frontend root.
    fs: { allow: ['..'] },
    port: 5173,
    // Proxy API calls to the development backend.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
