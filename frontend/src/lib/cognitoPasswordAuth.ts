/**
 * Direct Cognito USER_PASSWORD_AUTH for the /demo and /try left pane's second identity.
 * Calls the Cognito IDP endpoint without Amplify so the right pane's Amplify session is untouched.
 * The returned tokens are kept in React state only (never localStorage). The refresh token lets the
 * pane renew its ID token (REFRESH_TOKEN_AUTH) before the 60-minute expiry.
 */

export interface PasswordAuthResult {
  idToken: string;
  accessToken?: string;
  /** Absent on a refresh (Cognito does not rotate it); callers keep the one from sign-in. */
  refreshToken?: string;
  expiresIn?: number;
  /** Epoch ms when the ID token expires (from ExpiresIn, else 60 min). */
  expiresAt: number;
}

export interface PasswordAuthOptions {
  region?: string;
  clientId?: string;
}

interface InitiateAuthResponse {
  AuthenticationResult?: { IdToken?: string; AccessToken?: string; RefreshToken?: string; ExpiresIn?: number };
  ChallengeName?: string;
  __type?: string;
  message?: string;
  Message?: string;
}

function isInitiateAuthResponse(v: unknown): v is InitiateAuthResponse {
  return typeof v === 'object' && v !== null;
}

/** Error name mirrors the Cognito exception type (e.g. NotAuthorizedException) for UI mapping. */
export class CognitoAuthError extends Error {
  constructor(name: string, message: string) {
    super(message);
    this.name = name;
  }
}

async function initiateAuth(flow: 'USER_PASSWORD_AUTH' | 'REFRESH_TOKEN_AUTH', params: Record<string, string>, opts: PasswordAuthOptions): Promise<PasswordAuthResult> {
  const region = opts.region ?? import.meta.env.VITE_REGION ?? 'ap-south-1';
  const clientId = opts.clientId ?? import.meta.env.VITE_USER_POOL_CLIENT_ID ?? '';
  if (!clientId) throw new CognitoAuthError('NotConfigured', 'VITE_USER_POOL_CLIENT_ID is not set');

  let res: Response;
  try {
    res = await fetch(`https://cognito-idp.${region}.amazonaws.com/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth',
      },
      body: JSON.stringify({ AuthFlow: flow, ClientId: clientId, AuthParameters: params }),
    });
  } catch (e) {
    throw new CognitoAuthError('NetworkError', e instanceof Error ? e.message : 'network error');
  }

  let parsed: unknown = null;
  try {
    parsed = await res.json();
  } catch {
    /* non-JSON */
  }
  if (!isInitiateAuthResponse(parsed)) throw new CognitoAuthError('AuthError', `Cognito returned HTTP ${res.status}`);

  if (!res.ok) {
    const type = (parsed.__type ?? '').split('#').pop() ?? 'AuthError';
    const msg = parsed.message ?? parsed.Message ?? '';
    if (type === 'InvalidParameterException' && /USER_PASSWORD_AUTH|REFRESH_TOKEN_AUTH/.test(msg)) {
      throw new CognitoAuthError(type, `${flow} flow is not enabled on this app client (enable ALLOW_${flow}).`);
    }
    throw new CognitoAuthError(type, `${type}: ${msg}`.trim());
  }
  if (parsed.ChallengeName) {
    throw new CognitoAuthError('ChallengeNotSupported', `Cognito challenge ${parsed.ChallengeName} is not supported here (set a permanent password via scripts/seed.py).`);
  }
  const r = parsed.AuthenticationResult;
  const idToken = r?.IdToken;
  if (!idToken) throw new CognitoAuthError('AuthError', 'Cognito did not return an IdToken');
  const expiresIn = typeof r?.ExpiresIn === 'number' ? r.ExpiresIn : 3600;
  return {
    idToken,
    accessToken: r?.AccessToken,
    refreshToken: r?.RefreshToken,
    expiresIn,
    expiresAt: Date.now() + expiresIn * 1000,
  };
}

export function cognitoPasswordAuth(username: string, password: string, opts: PasswordAuthOptions = {}): Promise<PasswordAuthResult> {
  return initiateAuth('USER_PASSWORD_AUTH', { USERNAME: username.trim(), PASSWORD: password }, opts);
}

/** Renew the ID token with the refresh token from `cognitoPasswordAuth`. */
export function cognitoRefreshAuth(refreshToken: string, opts: PasswordAuthOptions = {}): Promise<PasswordAuthResult> {
  return initiateAuth('REFRESH_TOKEN_AUTH', { REFRESH_TOKEN: refreshToken }, opts);
}

/** Milliseconds until the token should be refreshed: 5 minutes before expiry, never less than 10 s. */
export function refreshDelayMs(auth: PasswordAuthResult, now = Date.now()): number {
  return Math.max(10_000, auth.expiresAt - 5 * 60 * 1000 - now);
}
