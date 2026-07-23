import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../src/opswitness/console/static',
    emptyOutDir: true,
    sourcemap: false,
    target: 'es2022',
  },
});
