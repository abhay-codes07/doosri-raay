import { lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { ApiIdentityProvider } from './api/context';
import { isConfigured } from './amplify';
import { AuthGate, type AuthedUser } from './auth/AuthGate';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Layout } from './components/Layout';
import { Spinner } from './components/ui';
import { LangProvider, useT } from './i18n/LangContext';
import { S, type Lang } from './i18n/strings';
import { readString, writeString } from './lib/storage';
import { SessionProvider, useSession } from './session';

// Route-level code splitting: each page (and the demo, which bundles both faces) is its own chunk.
const HomePage = lazy(() => import('./pages/Home').then((m) => ({ default: m.HomePage })));
const OnboardingPage = lazy(() => import('./pages/Onboarding').then((m) => ({ default: m.OnboardingPage })));
const ParentScreen = lazy(() => import('./pages/Parent').then((m) => ({ default: m.ParentScreen })));
const GuardianScreen = lazy(() => import('./pages/Guardian').then((m) => ({ default: m.GuardianScreen })));
const CaseNewPage = lazy(() => import('./pages/CaseNew').then((m) => ({ default: m.CaseNewPage })));
const CaseDetailPage = lazy(() => import('./pages/CaseDetail').then((m) => ({ default: m.CaseDetailPage })));
const SettingsPage = lazy(() => import('./pages/Settings').then((m) => ({ default: m.SettingsPage })));
const DemoPage = lazy(() => import('./pages/Demo').then((m) => ({ default: m.DemoPage })));

const LANG_KEY = 'dr:lang';

function readLang(): Lang {
  const v = readString(LANG_KEY);
  return v === 'en' ? 'en' : 'hi';
}

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
      <AuthGate header={<AuthHeader />}>{(user, signOut) => <AuthedApp user={user} signOut={signOut} />}</AuthGate>
    </ErrorBoundary>
  );
}

function AuthedApp({ user, signOut }: { user: AuthedUser; signOut: () => void }) {
  const sub = user.userId || 'me';
  const email = user.email;
  const doSignOut = useCallback(() => signOut(), [signOut]);
  const [lang, setLangState] = useState<Lang>(readLang);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    writeString(LANG_KEY, l);
  }, []);

  return (
    <BrowserRouter>
      <ApiIdentityProvider identity={sub}>
        <LangProvider lang={lang} setLang={setLang}>
          <SessionProvider sub={sub} email={email} signOut={doSignOut}>
            <LangFromProfile setLang={setLang} />
            <AppRoutes />
          </SessionProvider>
        </LangProvider>
      </ApiIdentityProvider>
    </BrowserRouter>
  );
}

/** Adopt the profile's language once, unless the user already chose one on this device. */
function LangFromProfile({ setLang }: { setLang: (l: Lang) => void }) {
  const s = useSession();
  useEffect(() => {
    if (s.profile?.lang && !readString(LANG_KEY)) setLang(s.profile.lang);
  }, [s.profile?.lang, setLang]);
  return null;
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

function ParentPage() {
  const s = useSession();
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
