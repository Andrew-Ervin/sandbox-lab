import tailwindcss from '@tailwindcss/postcss';
import vinext from 'vinext';
import { defineConfig } from 'vite';

// Local Python API and Kubernetes; no cloud bindings or public tunnel.
export default defineConfig({
  css: { postcss: { plugins: [tailwindcss()] } },
  server: {
    host: '127.0.0.1', port: 3000, strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8787', changeOrigin: false } },
    watch: { useFsEvents: false, usePolling: true, ignored: ['**/.runtime.nosync/**', '**/.local/**', '**/.venv/**', '**/backend/**', '**/sandbox/**', '**/docs/**', '**/reports/**', '**/infra/**', '**/scripts/**', '**/tests/**', '**/dist/**'] },
  },
  plugins: [vinext()],
});
