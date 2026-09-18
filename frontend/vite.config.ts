import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      devOptions: { enabled: false },
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,svg,png,ico,json,woff2}'],
        maximumFileSizeToCacheInBytes: 6 * 1024 * 1024,
      },
      manifest: {
        name: 'Doosri Raay',
        short_name: 'Doosri Raay',
        description: 'दूसरी राय — परिवार का साथ। Second opinion for the family.',
        lang: 'hi',
        start_url: '/',
        display: 'standalone',
        background_color: '#fbf6ee',
        theme_color: '#b5541c',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
  server: { port: 5173 },
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 1800,
  },
});
