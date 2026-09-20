/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_USER_POOL_ID?: string;
  readonly VITE_USER_POOL_CLIENT_ID?: string;
  readonly VITE_REGION?: string;
  readonly VITE_VAPID_PUBLIC_KEY?: string;
  readonly VITE_DEMO_PARENT_EMAIL?: string;
  /** Judge path (/try): shared guardian account, signed in through Amplify. */
  readonly VITE_JUDGE_EMAIL?: string;
  readonly VITE_JUDGE_PASSWORD?: string;
  /** Judge path (/try): shared parent account for the left pane (direct Cognito flow). */
  readonly VITE_JUDGE_PARENT_EMAIL?: string;
  readonly VITE_JUDGE_PARENT_PASSWORD?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
