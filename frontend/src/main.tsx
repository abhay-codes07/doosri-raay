import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@aws-amplify/ui-react/styles.css';
import './styles/global.css';
import { registerSW } from 'virtual:pwa-register';
import App from './App';
import { configureAmplify } from './amplify';

configureAmplify();

// Service worker: precache + Web Push handlers (src/sw.ts). Auto-updates in the background.
if ('serviceWorker' in navigator) {
  registerSW({ immediate: true });
}

const root = document.getElementById('root');
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
