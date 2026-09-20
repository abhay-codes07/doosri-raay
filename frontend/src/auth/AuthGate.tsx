import { useCallback, useEffect, useId, useState, type FormEvent, type ReactNode } from 'react';
import {
  confirmSignUp,
  fetchAuthSession,
  getCurrentUser,
  resendSignUpCode,
  signIn,
  signOut,
  signUp,
} from 'aws-amplify/auth';
import { UNAUTHORIZED_EVENT } from '../api/client';
import { S, type StringKey } from '../i18n/strings';

export interface AuthedUser {
  /** Cognito sub. */
  userId: string;
  /** The e-mail used to sign in, when known. */
  email?: string;
}

type Status = { kind: 'loading' } | { kind: 'out' } | { kind: 'in'; user: AuthedUser };
type View = 'signIn' | 'signUp' | 'confirm';

/** Hindi first, English small: the parent-screen text pattern, without the LangContext. */
function Bi2({ k, as: Tag = 'span' }: { k: StringKey; as?: 'span' | 'h1' | 'h2' | 'p' | 'label' }) {
  return (
    <Tag className="bi">
      <span className="bi-hi" lang="hi">
        {S[k].hi}
      </span>
      <span className="bi-en" lang="en">
        {S[k].en}
      </span>
    </Tag>
  );
}

function errorKey(e: unknown): StringKey {
  const name = e instanceof Error ? e.name : '';
  switch (name) {
    // The pool hides user existence (PreventUserExistenceErrors), so both read the same.
    case 'UserNotFoundException':
    case 'NotAuthorizedException':
      return 'authErrWrong';
    case 'UsernameExistsException':
      return 'authErrExists';
    case 'CodeMismatchException':
      return 'authErrCode';
    case 'ExpiredCodeException':
      return 'authErrCodeExpired';
    case 'InvalidPasswordException':
      return 'authErrPassword';
    case 'LimitExceededException':
    case 'TooManyRequestsException':
      return 'authErrLimit';
    case 'NetworkError':
      return 'offlineHint';
    default:
      return 'authErrGeneric';
  }
}

async function loadUser(): Promise<AuthedUser | null> {
  try {
    const u = await getCurrentUser();
    // make sure tokens are actually available (refresh if needed)
    const session = await fetchAuthSession();
    if (!session.tokens?.idToken) return null;
    return { userId: u.userId, email: u.signInDetails?.loginId ?? undefined };
  } catch {
    return null;
  }
}

/**
 * Custom bilingual sign-in / sign-up / confirm-code gate on top of `aws-amplify/auth`.
 * Replaces the Amplify UI Authenticator (≈ 400 kB of JS + CSS) with plain form elements
 * styled by global.css: large type, 48 px targets.
 */
export function AuthGate({
  header,
  footer,
  whenOut,
  children,
}: {
  header: ReactNode;
  /** Rendered under the forms (e.g. the judges' /try link). */
  footer?: ReactNode;
  /** Return a node to render instead of the forms while signed out (e.g. a redirect); null keeps the forms. */
  whenOut?: () => ReactNode | null;
  children: (user: AuthedUser, signOut: () => void) => ReactNode;
}) {
  const [status, setStatus] = useState<Status>({ kind: 'loading' });
  const [view, setView] = useState<View>('signIn');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<StringKey | null>(null);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [notice, setNotice] = useState<StringKey | null>(null);
  const uid = useId();

  useEffect(() => {
    let alive = true;
    void loadUser().then((u) => {
      if (alive) setStatus(u ? { kind: 'in', user: u } : { kind: 'out' });
    });
    return () => {
      alive = false;
    };
  }, []);

  const fail = (e: unknown) => {
    setError(errorKey(e));
    const msg = e instanceof Error ? e.message : '';
    setErrorDetail(errorKey(e) === 'authErrGeneric' && msg ? msg : null);
  };

  const finishSignIn = async () => {
    const u = await loadUser();
    if (u) {
      setPassword('');
      setCode('');
      setStatus({ kind: 'in', user: u });
    } else {
      setError('authErrGeneric');
    }
  };

  const doSignIn = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const r = await signIn({ username: email.trim(), password });
      if (r.isSignedIn) {
        await finishSignIn();
      } else if (r.nextStep.signInStep === 'CONFIRM_SIGN_UP') {
        setView('confirm');
        setNotice('authNeedsConfirm');
      } else {
        setError('authErrUnsupportedStep');
        setErrorDetail(r.nextStep.signInStep);
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'UserNotConfirmedException') {
        setView('confirm');
        setNotice('authNeedsConfirm');
      } else fail(err);
    } finally {
      setBusy(false);
    }
  };

  const doSignUp = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const r = await signUp({
        username: email.trim(),
        password,
        options: { userAttributes: { email: email.trim() } },
      });
      if (r.isSignUpComplete) {
        await signIn({ username: email.trim(), password });
        await finishSignIn();
      } else {
        setView('confirm');
        setNotice('authCodeSent');
      }
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const doConfirm = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await confirmSignUp({ username: email.trim(), confirmationCode: code.trim() });
      if (password) {
        await signIn({ username: email.trim(), password });
        await finishSignIn();
      } else {
        setView('signIn');
        setNotice('authConfirmed');
      }
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const doResend = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await resendSignUpCode({ username: email.trim() });
      setNotice('authCodeSent');
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const doSignOut = useCallback(() => {
    void signOut()
      .catch(() => undefined)
      .finally(() => {
        setStatus({ kind: 'out' });
        setView('signIn');
      });
  }, []);

  // The API client saw a 401 (expired/revoked session): back to the sign-in form with a notice.
  useEffect(() => {
    if (status.kind !== 'in') return undefined;
    let fired = false;
    const onUnauthorized = () => {
      if (fired) return;
      fired = true;
      setNotice('authSessionExpired');
      setError(null);
      doSignOut();
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [status.kind, doSignOut]);

  if (status.kind === 'loading') {
    return (
      <div className="page auth-wrap">
        <span className="row" role="status" aria-live="polite">
          <span className="spinner" aria-hidden="true" />
          <span lang="hi">{S.loading.hi}</span>
        </span>
      </div>
    );
  }

  if (status.kind === 'in') return <>{children(status.user, doSignOut)}</>;

  const override = whenOut?.();
  if (override) return <>{override}</>;

  const emailField = (autoComplete: string) => (
    <div className="field">
      <label htmlFor={`${uid}-email`}>
        <Bi2 k="authEmail" />
      </label>
      <input
        id={`${uid}-email`}
        type="email"
        inputMode="email"
        autoComplete={autoComplete}
        autoCapitalize="none"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
    </div>
  );

  const passwordField = (autoComplete: string, help?: StringKey) => (
    <div className="field">
      <label htmlFor={`${uid}-pw`}>
        <Bi2 k="authPassword" />
      </label>
      <input
        id={`${uid}-pw`}
        type="password"
        autoComplete={autoComplete}
        required
        minLength={8}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        aria-describedby={help ? `${uid}-pw-help` : undefined}
      />
      {help && (
        <span id={`${uid}-pw-help`} className="help">
          <Bi2 k={help} />
        </span>
      )}
    </div>
  );

  return (
    <div className="page auth-wrap" lang="hi">
      <div className="auth-card">
        {header}
        <div className="auth-tabs" role="tablist" aria-label={S.authSignIn.en}>
          <button
            type="button"
            role="tab"
            aria-selected={view === 'signIn'}
            className={`btn ${view === 'signIn' ? 'btn-primary' : ''}`}
            onClick={() => {
              setView('signIn');
              setError(null);
            }}
          >
            <Bi2 k="authSignIn" />
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view !== 'signIn'}
            className={`btn ${view !== 'signIn' ? 'btn-primary' : ''}`}
            onClick={() => {
              setView('signUp');
              setError(null);
            }}
          >
            <Bi2 k="authSignUp" />
          </button>
        </div>

        {notice && (
          <p className="alert" role="status">
            <Bi2 k={notice} />
          </p>
        )}
        {error && (
          <p className="alert alert-error" role="alert">
            <Bi2 k={error} />
            {errorDetail && (
              <span className="small muted" lang="en">
                {' '}
                ({errorDetail})
              </span>
            )}
          </p>
        )}

        {view === 'signIn' && (
          <form className="card auth-form" onSubmit={doSignIn}>
            {emailField('username')}
            {passwordField('current-password')}
            <button type="submit" className="btn btn-primary btn-big btn-block" disabled={busy}>
              {busy ? <span className="spinner" aria-hidden="true" /> : <Bi2 k="authSignIn" />}
            </button>
            <p className="small muted" style={{ marginBottom: 0 }}>
              <Bi2 k="authNewHere" />
            </p>
          </form>
        )}

        {view === 'signUp' && (
          <form className="card auth-form" onSubmit={doSignUp}>
            {emailField('username')}
            {passwordField('new-password', 'authPasswordHelp')}
            <button type="submit" className="btn btn-primary btn-big btn-block" disabled={busy}>
              {busy ? <span className="spinner" aria-hidden="true" /> : <Bi2 k="authSignUp" />}
            </button>
            <p className="small muted" style={{ marginBottom: 0 }}>
              <Bi2 k="authCodeInfo" />
            </p>
          </form>
        )}

        {view === 'confirm' && (
          <form className="card auth-form" onSubmit={doConfirm}>
            {emailField('username')}
            <div className="field">
              <label htmlFor={`${uid}-code`}>
                <Bi2 k="authCode" />
              </label>
              <input
                id={`${uid}-code`}
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                maxLength={8}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                style={{ letterSpacing: '0.25em', fontSize: '1.3em', textAlign: 'center' }}
              />
              <span className="help">
                <Bi2 k="authCodeHelp" />
              </span>
            </div>
            <button type="submit" className="btn btn-primary btn-big btn-block" disabled={busy || code.length < 4}>
              {busy ? <span className="spinner" aria-hidden="true" /> : <Bi2 k="authConfirm" />}
            </button>
            <div className="row mt">
              <button type="button" className="btn" disabled={busy || !email.trim()} onClick={() => void doResend()}>
                <Bi2 k="authResend" />
              </button>
              <button
                type="button"
                className="btn btn-quiet"
                onClick={() => {
                  setView('signIn');
                  setError(null);
                }}
              >
                <Bi2 k="back" />
              </button>
            </div>
          </form>
        )}
        {footer}
      </div>
    </div>
  );
}
