import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { fetchAuthSession, getCurrentUser, signIn, signOut } from 'aws-amplify/auth';
import { UNAUTHORIZED_EVENT } from '../api/client';
import { AppShell } from '../AppShell';
import type { AuthedUser } from '../auth/AuthGate';
import { JudgeFaq } from '../components/JudgeFaq';
import { ProgressBar } from '../components/ProgressBar';
import { Spinner } from '../components/ui';
import { S } from '../i18n/strings';
import { cognitoPasswordAuth } from '../lib/cognitoPasswordAuth';
import { judgeConfig, type JudgeConfig } from '../lib/judge';
import { DemoPage } from './Demo';

/**
 * /try — the judges' front door. No sign-up, no form: the shared judge guardian is signed in
 * through Amplify (so the normal session, nav and dashboard work), the shared judge parent through
 * the direct Cognito flow into the left pane, then the split demo renders under a judge FAQ.
 */
export function TryPage() {
  const cfg = useMemo(() => judgeConfig(), []);
  if (!cfg) return <JudgeNotConfigured />;
  return <TryAuthed cfg={cfg} />;
}

type State = { kind: 'signing' } | { kind: 'in'; user: AuthedUser } | { kind: 'error'; message: string };

function TryAuthed({ cfg }: { cfg: JudgeConfig }) {
  const navigate = useNavigate();
  const [state, setState] = useState<State>({ kind: 'signing' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        // Keep an existing judge session; replace anything else (a judge may have signed in elsewhere).
        const current = await getCurrentUser().catch(() => null);
        if (current && (current.signInDetails?.loginId ?? '').toLowerCase() === cfg.email.toLowerCase()) {
          const session = await fetchAuthSession();
          if (session.tokens?.idToken) {
            if (alive) setState({ kind: 'in', user: { userId: current.userId, email: cfg.email } });
            return;
          }
        }
        if (current) await signOut().catch(() => undefined);
        const r = await signIn({ username: cfg.email, password: cfg.password });
        if (!r.isSignedIn) throw new Error(`Cognito wants step ${r.nextStep.signInStep}; seed the judge with a permanent password.`);
        const u = await getCurrentUser();
        if (alive) setState({ kind: 'in', user: { userId: u.userId, email: cfg.email } });
      } catch (e) {
        if (alive) setState({ kind: 'error', message: e instanceof Error ? `${e.name}: ${e.message}` : String(e) });
      }
    })();
    return () => {
      alive = false;
    };
  }, [cfg, attempt]);

  // The judge session expired or was revoked: sign in again instead of falling back to a form.
  useEffect(() => {
    if (state.kind !== 'in') return undefined;
    const again = () => {
      setState({ kind: 'signing' });
      setAttempt((n) => n + 1);
    };
    window.addEventListener(UNAUTHORIZED_EVENT, again);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, again);
  }, [state.kind]);

  const doSignOut = useCallback(() => {
    void signOut()
      .catch(() => undefined)
      .finally(() => navigate('/signin', { replace: true }));
  }, [navigate]);

  const autoParent = useCallback(() => cognitoPasswordAuth(cfg.parentEmail, cfg.parentPassword), [cfg]);

  if (state.kind === 'signing') {
    return (
      <div className="page auth-wrap">
        <div className="auth-card" style={{ textAlign: 'center' }}>
          <JudgeBanner />
          <Spinner label={`${S.judgeSigningIn.en} · ${S.judgeSigningIn.hi}`} />
        </div>
      </div>
    );
  }
  if (state.kind === 'error') {
    return (
      <div className="page auth-wrap">
        <div className="auth-card">
          <JudgeBanner />
          <p className="alert alert-error" role="alert" lang="en">
            {S.judgeSignInFailed.en} <span className="small muted">({state.message})</span>
          </p>
          <p className="alert alert-error" role="alert" lang="hi">
            {S.judgeSignInFailed.hi}
          </p>
          <div className="row">
            <button type="button" className="btn btn-primary" onClick={() => { setState({ kind: 'signing' }); setAttempt((n) => n + 1); }}>
              {S.retry.en} · {S.retry.hi}
            </button>
            <Link className="btn" to="/signin">
              {S.judgeOwnAccount.en}
            </Link>
          </div>
        </div>
      </div>
    );
  }
  return (
    <AppShell user={state.user} signOut={doSignOut}>
      <div className="page">
        <ProgressBar />
        <header className="topbar">
          <Link to="/" className="brand" aria-label={S.appName.en}>
            <span className="brand-mark" aria-hidden="true">
              दू
            </span>
            <span>{S.appName.en}</span>
          </Link>
          <nav className="nav" aria-label="judge">
            <Link to="/guardian">{S.judgeFullDashboard.en}</Link>
            <Link to="/signin" onClick={(e) => { e.preventDefault(); doSignOut(); }}>
              {S.judgeOwnAccount.en}
            </Link>
          </nav>
        </header>
        <JudgeBanner />
        <DemoPage autoParent={autoParent} faq={<JudgeFaq cfg={cfg} />} />
      </div>
    </AppShell>
  );
}

function JudgeBanner() {
  return (
    <p className="judge-banner" role="note">
      <span aria-hidden="true">🧑‍⚖️</span> <strong lang="en">{S.judgeBanner.en}</strong> <span className="muted" lang="hi">· {S.judgeBanner.hi}</span>
    </p>
  );
}

/** Build has no judge credentials: say how to get in, in both languages. */
function JudgeNotConfigured() {
  return (
    <div className="page auth-wrap">
      <div className="auth-card">
        <div className="auth-hero">
          <h1>{S.appName.hi}</h1>
          <p className="muted" style={{ margin: 0 }}>
            {S.appName.en}
          </p>
        </div>
        <section className="card mt">
          <h2 lang="en">{S.judgeNotConfiguredTitle.en}</h2>
          <p lang="en">{S.judgeNotConfiguredBody.en}</p>
          <pre className="pre small" lang="en">
            VITE_JUDGE_EMAIL / VITE_JUDGE_PASSWORD (guardian){'\n'}VITE_JUDGE_PARENT_EMAIL / VITE_JUDGE_PARENT_PASSWORD (parent)
          </pre>
          <h2 lang="hi" className="mt">
            {S.judgeNotConfiguredTitle.hi}
          </h2>
          <p lang="hi">{S.judgeNotConfiguredBody.hi}</p>
          <p className="mt">
            <Link className="btn btn-primary btn-big btn-block" to="/signin">
              {S.authSignIn.en} · {S.authSignIn.hi}
            </Link>
          </p>
        </section>
      </div>
    </div>
  );
}
