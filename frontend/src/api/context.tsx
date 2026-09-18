import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { api, createApiClient, type ApiClient } from './client';

interface ApiCtx {
  client: ApiClient;
  /** Identity (Cognito sub) behind this client; used only to namespace localStorage. */
  identity: string;
  overridden: boolean;
}

const ApiContext = createContext<ApiCtx>({ client: api, identity: 'me', overridden: false });

/** Decode the `sub` claim of a JWT without verifying it (only used as a storage namespace). */
export function jwtSub(token: string): string {
  try {
    const payload = token.split('.')[1] ?? '';
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    const parsed: unknown = JSON.parse(json);
    if (typeof parsed === 'object' && parsed !== null) {
      const sub = (parsed as { sub?: unknown }).sub;
      if (typeof sub === 'string') return sub;
    }
  } catch {
    /* ignore */
  }
  return 'unknown';
}

/** Wrap a subtree so every useApi() inside uses an explicit ID token (the /demo left pane). */
export function ApiTokenProvider({ token, children }: { token: string; children: ReactNode }) {
  const value = useMemo<ApiCtx>(
    () => ({ client: createApiClient(async () => token), identity: jwtSub(token), overridden: true }),
    [token],
  );
  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

/** Provide the identity of the Amplify-signed-in user for storage namespacing. */
export function ApiIdentityProvider({ identity, children }: { identity: string; children: ReactNode }) {
  const value = useMemo<ApiCtx>(() => ({ client: api, identity, overridden: false }), [identity]);
  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

export function useApi(): ApiClient {
  return useContext(ApiContext).client;
}

export function useApiIdentity(): string {
  return useContext(ApiContext).identity;
}

export function useApiOverridden(): boolean {
  return useContext(ApiContext).overridden;
}
