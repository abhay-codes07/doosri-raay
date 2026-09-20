import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { ApiIdentityProvider } from './api/context';
import type { AuthedUser } from './auth/AuthGate';
import { LangProvider } from './i18n/LangContext';
import type { Lang } from './i18n/strings';
import { readString, writeString } from './lib/storage';
import { SessionProvider, useSession } from './session';

const LANG_KEY = 'dr:lang';

function readLang(): Lang {
  const v = readString(LANG_KEY);
  return v === 'en' ? 'en' : 'hi';
}

/**
 * Everything a signed-in screen needs: API identity (storage namespace), language, and the
 * session (GET /profile). Used by the normal app and by the judge path, which signs in by itself.
 * Must be rendered inside a router.
 */
export function AppShell({ user, signOut, children }: { user: AuthedUser; signOut: () => void; children: ReactNode }) {
  const sub = user.userId || 'me';
  const email = user.email;
  const doSignOut = useCallback(() => signOut(), [signOut]);
  const [lang, setLangState] = useState<Lang>(readLang);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    writeString(LANG_KEY, l);
  }, []);

  return (
    <ApiIdentityProvider identity={sub}>
      <LangProvider lang={lang} setLang={setLang}>
        <SessionProvider sub={sub} email={email} signOut={doSignOut}>
          <LangFromProfile setLang={setLang} />
          {children}
        </SessionProvider>
      </LangProvider>
    </ApiIdentityProvider>
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
