import { NavLink, Outlet } from 'react-router-dom';
import { useLang, useT } from '../i18n/LangContext';
import { judgeConfigured } from '../lib/judge';
import { useSession } from '../session';

/** Top bar + nav for guardian screens. The parent tile hides the nav (it is the whole app for them). */
export function Layout() {
  const { t } = useT();
  const { lang, setLang } = useLang();
  const session = useSession();
  return (
    <div className="page">
      <header className="topbar">
        <NavLink to="/" className="brand" aria-label={t('appName')}>
          <span className="brand-mark" aria-hidden="true">
            दू
          </span>
          <span>{t('appName')}</span>
        </NavLink>
        <nav className="nav" aria-label="main">
          {session.hasCircle && !session.isParent && <NavLink to="/guardian">{t('navGuardian')}</NavLink>}
          {session.hasCircle && session.isParent && <NavLink to="/parent">{t('navParent')}</NavLink>}
          <NavLink to="/demo">{t('navDemo')}</NavLink>
          {judgeConfigured() && <NavLink to="/try">{t('navTry')}</NavLink>}
          <button type="button" onClick={() => setLang(lang === 'hi' ? 'en' : 'hi')} aria-label={t('langLabel')}>
            {lang === 'hi' ? 'EN' : 'हि'}
          </button>
          <button type="button" onClick={session.signOut}>
            {t('signOut')}
          </button>
        </nav>
      </header>
      <Outlet />
    </div>
  );
}
