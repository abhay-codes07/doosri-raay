import { useEffect, useId, useState, type FormEvent } from 'react';
import { ApiTokenProvider, useApi } from '../api/context';
import { describeError } from '../api/client';
import type { DemoConfig } from '../api/types';
import { Spinner } from '../components/ui';
import { useT } from '../i18n/LangContext';
import { cognitoPasswordAuth } from '../lib/cognitoPasswordAuth';
import { KEYS, removePrefix } from '../lib/storage';
import { GuardianScreen } from './Guardian';
import { ParentScreen } from './Parent';

/**
 * One-browser split view for judges. Left: Papa's phone (second identity via direct Cognito
 * USER_PASSWORD_AUTH, token in memory only). Right: Priya's phone (the normal Amplify session).
 */
export function DemoPage() {
  const api = useApi();
  const { t } = useT();
  const uid = useId();
  const [parentToken, setParentToken] = useState<string | null>(null);
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
      setParentToken(r.idToken);
      setPassword('');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  /** POST /demo/reset as the guardian (the Amplify session), then clear this browser's state. */
  const resetDemo = async () => {
    setResetting(true);
    setResetMsg(null);
    let msg = t('demoResetDone');
    try {
      await api.demoReset();
    } catch (e) {
      msg = `${t('demoResetServerFailed')} (${describeError(e)})`;
    } finally {
      removePrefix(KEYS.prefix);
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
          <span className="small muted">{t('demoTimings')}</span>
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

      <div className="demo-split">
        <section className="phone" aria-label={t('demoLeft')}>
          <div className="phone-head">
            <span>📱 {t('demoLeft')}</span>
            {parentToken && (
              <button type="button" className="btn btn-quiet small" onClick={() => setParentToken(null)}>
                {t('demoSignOutParent')}
              </button>
            )}
          </div>
          <div className="phone-body">
            {!parentToken ? (
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
            ) : (
              <ApiTokenProvider token={parentToken}>
                <p className="small muted" style={{ margin: '0 0 8px' }}>
                  {t('demoSignedIn', { email: parentEmail })}
                </p>
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
