/**
 * Direct Cognito USER_PASSWORD_AUTH for the /demo left pane's second identity.
 * Calls the Cognito IDP endpoint without Amplify so the right pane's Amplify session is untouched.
 * The returned IdToken is kept in React state only (never localStorage).
 */

export interface PasswordAuthResult {
  idToken: string;
  accessToken?: string;
  expiresIn?: number;
}

export interface PasswordAuthOptions {
  region?: string;
  clientId?: string;
}

interface InitiateAuthResponse {
  AuthenticationResult?: { IdToken?: string; AccessToken?: string; ExpiresIn?: number };
  ChallengeName?: string;
  __type?: string;
  message?: string;
  Message?: string;
}

function isInitiateAuthResponse(v: unknown): v is InitiateAuthResponse {
  return typeof v === 'object' && v !== null;
}

export async function cognitoPasswordAuth(
  username: string,
  password: string,
  opts: PasswordAuthOptions = {},
): Promise<PasswordAuthResult> {
  const region = opts.region ?? import.meta.env.VITE_REGION ?? 'ap-south-1';
  const clientId = opts.clientId ?? import.meta.env.VITE_USER_POOL_CLIENT_ID ?? '';
  if (!clientId) throw new Error('VITE_USER_POOL_CLIENT_ID is not set');

  const res = await fetch(`https://cognito-idp.${region}.amazonaws.com/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-amz-json-1.1',
      'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth',
    },
    body: JSON.stringify({
      AuthFlow: 'USER_PASSWORD_AUTH',
      ClientId: clientId,
      AuthParameters: { USERNAME: username.trim(), PASSWORD: password },
    }),
  });

  let parsed: unknown = null;
  try {
    parsed = await res.json();
  } catch {
    /* non-JSON */
  }
  if (!isInitiateAuthResponse(parsed)) throw new Error(`Cognito returned HTTP ${res.status}`);

  if (!res.ok) {
    const type = (parsed.__type ?? '').split('#').pop() ?? 'AuthError';
    const msg = parsed.message ?? parsed.Message ?? '';
    if (type === 'InvalidParameterException' && /USER_PASSWORD_AUTH/.test(msg)) {
      throw new Error('USER_PASSWORD_AUTH flow is not enabled on this app client (enable ALLOW_USER_PASSWORD_AUTH).');
    }
    throw new Error(`${type}: ${msg}`.trim());
  }
  if (parsed.ChallengeName) {
    throw new Error(`Cognito challenge ${parsed.ChallengeName} is not supported here (set a permanent password via scripts/seed.py).`);
  }
  const idToken = parsed.AuthenticationResult?.IdToken;
  if (!idToken) throw new Error('Cognito did not return an IdToken');
  return {
    idToken,
    accessToken: parsed.AuthenticationResult?.AccessToken,
    expiresIn: parsed.AuthenticationResult?.ExpiresIn,
  };
}
