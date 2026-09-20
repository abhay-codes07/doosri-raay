import { lazy, Suspense, type ReactNode } from 'react';
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { isConfigured } from './amplify';
import { AppShell } from './AppShell';
import { AuthGate, type AuthedUser } from './auth/AuthGate';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Layout } from './components/Layout';
import { Spinner } from './components/ui';
import { useT } from './i18n/LangContext';
import { S } from './i18n/strings';
import { judgeConfigured } from './lib/judge';
import { useSession } from './session';

// Route-level code splitting: each page (and the demo, which bundles both faces) is its own chunk.
const HomePage = lazy(() => import('./pages/Home').then((m) => ({ default: m.HomePage })));
const OnboardingPage = lazy(() => import('./pages/Onboarding').then((m) => ({ default: m.OnboardingPage })));
const ParentScreen = lazy(() => import('./pages/Parent').then((m) => ({ default: m.ParentScreen })));
const GuardianScreen = lazy(() => import('./pages/Guardian').then((m) => ({ default: m.GuardianScreen })));
const CaseNewPage = lazy(() => import('./pages/CaseNew').then((m) => ({ default: m.CaseNewPage })));
const CaseDetailPage = lazy(() => import('./pages/CaseDetail').then((m) => ({ default: m.CaseDetailPage })));
const SettingsPage = lazy(() => import('./pages/Settings').then((m) => ({ default: m.SettingsPage })));
const DemoPage = lazy(() => import('./pages/Demo').then((m) => ({ default: m.DemoPage })));
const TryPage = lazy(() => import('./pages/Try').then((m) => ({ default: m.TryPage })));

function AuthHeader() {
  return (
    <div className="auth-hero">
      <div className="brand-mark" style={{ margin: '0 auto', width: 56, height: 56, fontSize: 28 }} aria-hidden="true">
        दू
      </div>
      <h1>{S.appName.hi}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {S.appName.en} · {S.tagline.hi}
      </p>
    </div>
  );
}

/** Under the sign-in form: judges never need an account. */
function JudgeLink() {
  if (!judgeConfigured()) return null;
  return (
    <p className="small muted" style={{ textAlign: 'center', marginTop: 12 }}>
      <Link to="/try" className="btn btn-quiet">
        <span className="bi">
          <span className="bi-hi" lang="hi">
            {S.judgeOpenTry.hi}
          </span>
          <span className="bi-en" lang="en">
            {S.judgeOpenTry.en}
          </span>
        </span>
      </Link>
    </p>
  );
}

export default function App() {
  if (!isConfigured()) {
    return (
      <div className="page page-narrow">
        <div className="auth-hero">
          <h1>{S.appName.hi}</h1>
        </div>
        <p className="alert alert-error" role="alert" lang="hi">
          {S.notConfigured.hi}
        </p>
        <p className="alert alert-error" role="alert" lang="en">
          {S.notConfigured.en}
        </p>
      </div>
    );
  }
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          {/* Public judge path: signs in the shared account by itself; no gate, no sign-up. */}
          <Route
            path="/try"
            element={
              <Guarded>
                <TryPage />
              </Guarded>
            }
          />
          <Route path="*" element={<GatedApp />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

/** Everything behind the sign-in gate. Unauthenticated visits to "/" land on /try when a judge account is built in. */
function GatedApp() {
  const { pathname } = useLocation();
  return (
    <AuthGate
      header={<AuthHeader />}
      footer={<JudgeLink />}
      whenOut={() => (judgeConfigured() && pathname === '/' ? <Navigate to="/try" replace /> : null)}
    >
      {(user, signOut) => <AuthedApp user={user} signOut={signOut} />}
    </AuthGate>
  );
}

function AuthedApp({ user, signOut }: { user: AuthedUser; signOut: () => void }) {
  return (
    <AppShell user={user} signOut={signOut}>
      <AppRoutes />
    </AppShell>
  );
}

function PageSpinner() {
  const { t } = useT();
  return (
    <div className="page">
      <Spinner label={t('loading')} />
    </div>
  );
}

function RequireCircle({ children }: { children: ReactNode }) {
  const s = useSession();
  if (s.loading && !s.profile) return <PageSpinner />;
  if (!s.loading && !s.error && !s.hasCircle) return <Navigate to="/onboarding" replace />;
  return <>{children}</>;
}

/**
 * Onboarding reads the session once on mount, so wait for the first profile load. It is not keyed
 * on circleId: session.reload() after the pact must not remount it back at the profile step.
 */
function OnboardingRoute() {
  const s = useSession();
  if (s.loading && !s.profile) return <PageSpinner />;
  return (
    <div className="page">
      <OnboardingPage />
    </div>
  );
}

/** A parent who has not accepted the family pact is sent to that step first (no pact, no tile). */
function ParentPage() {
  const s = useSession();
  if (s.profile && s.isParent && s.profile.pactAccepted !== true) return <Navigate to="/onboarding?step=pact" replace />;
  return <ParentScreen onSignOut={s.signOut} />;
}

/** Every route element sits inside its own boundary (reset on navigation) and its own Suspense. */
function Guarded({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return (
    <ErrorBoundary resetKey={pathname}>
      <Suspense fallback={<PageSpinner />}>{children}</Suspense>
    </ErrorBoundary>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <Guarded>
            <HomePage />
          </Guarded>
        }
      />
      <Route
        path="/onboarding"
        element={
          <Guarded>
            <OnboardingRoute />
          </Guarded>
        }
      />
      <Route
        path="/parent"
        element={
          <Guarded>
            <RequireCircle>
              <ParentPage />
            </RequireCircle>
          </Guarded>
        }
      />
      <Route
        element={
          <Guarded>
            <Layout />
          </Guarded>
        }
      >
        <Route
          path="/guardian"
          element={
            <Guarded>
              <RequireCircle>
                <GuardianScreen />
              </RequireCircle>
            </Guarded>
          }
        />
        <Route
          path="/case/new"
          element={
            <Guarded>
              <RequireCircle>
                <CaseNewPage />
              </RequireCircle>
            </Guarded>
          }
        />
        <Route
          path="/case/:id"
          element={
            <Guarded>
              <RequireCircle>
                <CaseDetailPage />
              </RequireCircle>
            </Guarded>
          }
        />
        <Route
          path="/settings"
          element={
            <Guarded>
              <RequireCircle>
                <SettingsPage />
              </RequireCircle>
            </Guarded>
          }
        />
        <Route
          path="/demo"
          element={
            <Guarded>
              <DemoPage />
            </Guarded>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
