import path from 'node:path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const proxyTarget = process.env.VITE_DEV_API_TARGET || 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: [{ find: '@', replacement: path.resolve(__dirname, './src') }],
    dedupe: ['vue', '@iconify/vue'],
  },
  build: {
    outDir: path.resolve(__dirname, 'dist'),
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/auth': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/version': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/images': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/image-thumbnails': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/v1': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
})
