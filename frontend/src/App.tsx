import { Authenticator, type UseAuthenticator } from '@aws-amplify/ui-react';
import type { AuthUser } from 'aws-amplify/auth';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { ApiIdentityProvider } from './api/context';
import { isConfigured } from './amplify';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Layout } from './components/Layout';
import { Spinner } from './components/ui';
import { LangProvider, useT } from './i18n/LangContext';
import { S, type Lang } from './i18n/strings';
import { readString, writeString } from './lib/storage';
import { CaseDetailPage } from './pages/CaseDetail';
import { CaseNewPage } from './pages/CaseNew';
import { DemoPage } from './pages/Demo';
import { GuardianScreen } from './pages/Guardian';
import { HomePage } from './pages/Home';
import { OnboardingPage } from './pages/Onboarding';
import { ParentScreen } from './pages/Parent';
import { SessionProvider, useSession } from './session';

const LANG_KEY = 'dr:lang';

function readLang(): Lang {
  const v = readString(LANG_KEY);
  return v === 'en' ? 'en' : 'hi';
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
    <div className="auth-wrap-outer">
      <Authenticator
        loginMechanisms={['email']}
        signUpAttributes={['email']}
        components={{
          Header() {
            return (
              <div className="auth-hero">
                <div className="brand-mark" style={{ margin: '0 auto', width: 48, height: 48, fontSize: 24 }} aria-hidden="true">
                  दू
                </div>
                <h1>{S.appName.hi}</h1>
                <p className="muted" style={{ margin: 0 }}>
                  {S.appName.en} · {S.tagline.hi}
                </p>
              </div>
            );
          },
        }}
      >
        {({ signOut, user }) => <AuthedApp signOut={signOut} user={user} />}
      </Authenticator>
    </div>
  );
}

function AuthedApp({ signOut, user }: { signOut: UseAuthenticator['signOut'] | undefined; user: AuthUser | undefined }) {
  const sub = user?.userId ?? 'me';
  const email = user?.signInDetails?.loginId;
  const doSignOut = useCallback(() => signOut?.(), [signOut]);
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

function RequireCircle({ children }: { children: ReactNode }) {
  const s = useSession();
  const { t } = useT();
  if (s.loading && !s.profile) {
    return (
      <div className="page">
        <Spinner label={t('loading')} />
      </div>
    );
  }
  if (!s.loading && !s.error && !s.hasCircle) return <Navigate to="/onboarding" replace />;
  return <>{children}</>;
}

/** Onboarding reads the session once on mount, so wait for the first profile load. */
function OnboardingRoute() {
  const s = useSession();
  const { t } = useT();
  if (s.loading && !s.profile) {
    return (
      <div className="page">
        <Spinner label={t('loading')} />
      </div>
    );
  }
  return (
    <div className="page">
      <OnboardingPage key={s.profile?.circleId ?? 'none'} />
    </div>
  );
}

function ParentPage() {
  const s = useSession();
  return <ParentScreen onSignOut={s.signOut} />;
}

/** Every route element sits inside its own boundary; the key resets it on navigation. */
function Guarded({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return <ErrorBoundary resetKey={pathname}>{children}</ErrorBoundary>;
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
