/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_USER_POOL_ID?: string;
  readonly VITE_USER_POOL_CLIENT_ID?: string;
  readonly VITE_REGION?: string;
  readonly VITE_VAPID_PUBLIC_KEY?: string;
  readonly VITE_DEMO_PARENT_EMAIL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
