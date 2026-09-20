import { useCallback, useEffect, useId, useState, type FormEvent, type ReactNode } from 'react';
import { ApiTokenProvider, jwtSub, useApi, useApiIdentity } from '../api/context';
import { describeError } from '../api/client';
import type { DemoConfig } from '../api/types';
import { Spinner } from '../components/ui';
import { useT } from '../i18n/LangContext';
import { cognitoPasswordAuth, cognitoRefreshAuth, refreshDelayMs, type PasswordAuthResult } from '../lib/cognitoPasswordAuth';
import { KEYS, removePrefix } from '../lib/storage';
import { GuardianScreen } from './Guardian';
import { ParentScreen } from './Parent';

export interface DemoPageProps {
  /** Judge path: the parent pane signs in by itself on mount and again after a 401. */
  autoParent?: () => Promise<PasswordAuthResult>;
  /** Rendered between the header and the two phones (the judge FAQ). */
  faq?: ReactNode;
  /** Extra header controls (e.g. a "watch expires in" hint). */
  headerExtra?: ReactNode;
}

/**
 * One-browser split view for judges. Left: Papa's phone (second identity via direct Cognito
 * USER_PASSWORD_AUTH, tokens in memory only, refreshed 5 minutes before expiry). Right: Priya's
 * phone (the normal Amplify session).
 */
export function DemoPage({ autoParent, faq, headerExtra }: DemoPageProps = {}) {
  const api = useApi();
  const guardianIdentity = useApiIdentity();
  const { t } = useT();
  const uid = useId();
  const [parentAuth, setParentAuth] = useState<PasswordAuthResult | null>(null);
  const [parentEmail, setParentEmail] = useState(import.meta.env.VITE_DEMO_PARENT_EMAIL ?? '');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<DemoConfig | null | 'error'>(null);
  const [epoch, setEpoch] = useState(0);
  const [resetMsg, setResetMsg] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .getDemoConfig()
      .then((c) => alive && setConfig(c))
      .catch(() => alive && setConfig('error'));
    return () => {
      alive = false;
    };
  }, [api]);

  const signInParent = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await cognitoPasswordAuth(parentEmail, password);
      setParentAuth(r);
      setPassword('');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  // Judge path: sign the parent in without a form (and again whenever the pane is signed out).
  const [autoTries, setAutoTries] = useState(0);
  const [autoError, setAutoError] = useState<string | null>(null);
  const autoSigning = Boolean(autoParent) && !parentAuth && !autoError;
  useEffect(() => {
    if (!autoParent || parentAuth || autoError) return undefined;
    let alive = true;
    autoParent()
      .then((r) => {
        if (alive) setParentAuth(r);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setAutoError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      alive = false;
    };
    // `autoTries` re-runs the auto sign-in after "retry", `epoch` after a reset or a 401.
  }, [autoParent, parentAuth, autoError, autoTries, epoch]);
  const retryAuto = () => {
    setAutoError(null);
    setAutoTries((n) => n + 1);
  };

  // Refresh the parent's ID token 5 minutes before it expires; on failure fall back to the form.
  useEffect(() => {
    if (!parentAuth?.refreshToken) return undefined;
    const refreshToken = parentAuth.refreshToken;
    const id = window.setTimeout(() => {
      cognitoRefreshAuth(refreshToken)
        .then((r) => setParentAuth({ ...r, refreshToken: r.refreshToken ?? refreshToken }))
        .catch(() => {
          setParentAuth(null);
          setError(t('demoSessionExpired'));
        });
    }, refreshDelayMs(parentAuth));
    return () => window.clearTimeout(id);
  }, [parentAuth, t]);

  /** A 401 on the parent client: show the sign-in form again (never touches the guardian session). */
  const onParentUnauthorized = useCallback(() => {
    setParentAuth(null);
    setError(t('demoSessionExpired'));
    setAutoError(null);
  }, [t]);

  /** POST /demo/reset as the guardian (the Amplify session), then clear this browser's state for both identities. */
  const resetDemo = async () => {
    setResetting(true);
    setResetMsg(null);
    let msg = t('demoResetDone');
    try {
      await api.demoReset();
    } catch (e) {
      msg = `${t('demoResetServerFailed')} (${describeError(e)})`;
    } finally {
      // Scoped to the two identities on screen: language, geocode and weather caches survive.
      removePrefix(KEYS.identityPrefix(guardianIdentity));
      if (parentAuth) removePrefix(KEYS.identityPrefix(jwtSub(parentAuth.idToken)));
      setEpoch((n) => n + 1);
      setResetting(false);
      setResetMsg(msg);
      window.setTimeout(() => setResetMsg(null), 4000);
    }
  };

  return (
    <div>
      <div className="row spread" style={{ marginBottom: 12 }}>
        <h1 style={{ fontSize: '1.3em', margin: 0 }}>{t('demoTitle')}</h1>
        <div className="row">
          {config === null && <Spinner />}
          {config === 'error' && <span className="badge">{t('demoConfigUnknown')}</span>}
          {config && config !== 'error' && (
            <span className={`badge ${config.demoTimeouts ? 'badge-amber' : ''}`}>
              {config.demoTimeouts ? t('demoConfigOn') : t('demoConfigOff')}
              {config.demoTimeouts && ` · watch ${config.watchDeadlineSeconds ?? 45} s · rung ${config.rungTimeoutSeconds ?? 45} s`}
            </span>
          )}
          {headerExtra}
          <button type="button" className="btn" disabled={resetting} onClick={() => void resetDemo()}>
            {resetting ? <Spinner label={t('demoResetting')} /> : t('demoReset')}
          </button>
          {resetMsg && (
            <span className={`badge ${resetMsg === t('demoResetDone') ? 'badge-ok' : 'badge-amber'}`} role="status">
              {resetMsg}
            </span>
          )}
        </div>
      </div>

      {faq}

      <div className="demo-split">
        <section className="phone" aria-label={t('demoLeft')}>
          <div className="phone-head">
            <span>📱 {t('demoLeft')}</span>
            {parentAuth && !autoParent && (
              <button type="button" className="btn btn-quiet small" onClick={() => setParentAuth(null)}>
                {t('demoSignOutParent')}
              </button>
            )}
          </div>
          <div className="phone-body">
            {!parentAuth ? (
              autoParent ? (
                <div className="card">
                  {autoSigning ? (
                    <Spinner label={t('demoSigningIn')} />
                  ) : (
                    <>
                      <p className="alert alert-error" role="alert">
                        {autoError ?? error}
                      </p>
                      <button type="button" className="btn btn-primary btn-big btn-block" onClick={retryAuto}>
                        {t('retry')}
                      </button>
                    </>
                  )}
                </div>
              ) : (
                <form className="card" onSubmit={signInParent}>
                  <div className="field">
                    <label htmlFor={`${uid}-email`}>{t('demoParentEmail')}</label>
                    <input id={`${uid}-email`} type="email" value={parentEmail} autoComplete="username" onChange={(e) => setParentEmail(e.target.value)} required />
                  </div>
                  <div className="field">
                    <label htmlFor={`${uid}-pw`}>{t('demoParentPassword')}</label>
                    <input id={`${uid}-pw`} type="password" value={password} autoComplete="current-password" onChange={(e) => setPassword(e.target.value)} required />
                  </div>
                  {error && (
                    <p className="alert alert-error" role="alert">
                      {error}
                    </p>
                  )}
                  <button type="submit" className="btn btn-primary btn-big btn-block" disabled={busy}>
                    {busy ? <Spinner label={t('demoSigningIn')} /> : t('demoSignIn')}
                  </button>
                  <p className="small muted">{t('demoTokenNote')}</p>
                </form>
              )
            ) : (
              <ApiTokenProvider token={parentAuth.idToken} onUnauthorized={onParentUnauthorized}>
                {!autoParent && (
                  <p className="small muted" style={{ margin: '0 0 8px' }}>
                    {t('demoSignedIn', { email: parentEmail })}
                  </p>
                )}
                <ParentScreen key={`p-${epoch}`} embedded />
              </ApiTokenProvider>
            )}
          </div>
        </section>

        <section className="phone" aria-label={t('demoRight')}>
          <div className="phone-head">
            <span>📱 {t('demoRight')}</span>
          </div>
          <div className="phone-body">
            <GuardianScreen key={`g-${epoch}`} embedded />
          </div>
        </section>
      </div>
    </div>
  );
}
