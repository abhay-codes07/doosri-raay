import { Amplify } from 'aws-amplify';

export const USER_POOL_ID = import.meta.env.VITE_USER_POOL_ID ?? '';
export const USER_POOL_CLIENT_ID = import.meta.env.VITE_USER_POOL_CLIENT_ID ?? '';
export const REGION = import.meta.env.VITE_REGION ?? 'ap-south-1';

export const isConfigured = (): boolean =>
  Boolean(USER_POOL_ID && USER_POOL_CLIENT_ID && import.meta.env.VITE_API_URL);

export function configureAmplify(): void {
  if (!USER_POOL_ID || !USER_POOL_CLIENT_ID) return;
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: USER_POOL_ID,
        userPoolClientId: USER_POOL_CLIENT_ID,
        loginWith: { email: true },
        signUpVerificationMethod: 'code',
      },
    },
  });
}
