import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  base: '/dashboard/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/analytics': 'http://127.0.0.1:8000',
      '/detections': 'http://127.0.0.1:8000',
      '/debug': 'http://127.0.0.1:8000',
      '/scan': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000'
    }
  }
});
