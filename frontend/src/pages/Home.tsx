import { Navigate } from 'react-router-dom';
import { ErrorBox, Spinner } from '../components/ui';
import { useT } from '../i18n/LangContext';
import { useSession } from '../session';

/** Role-aware redirect after sign-in. */
export function HomePage() {
  const s = useSession();
  const { t } = useT();
  if (s.loading && !s.profile) {
    return (
      <div className="page">
        <Spinner label={t('loading')} />
      </div>
    );
  }
  if (s.error && !s.profile) {
    return (
      <div className="page">
        <ErrorBox message={s.error} onRetry={() => void s.reload()} />
      </div>
    );
  }
  if (!s.hasCircle) return <Navigate to="/onboarding" replace />;
  return <Navigate to={s.isParent ? '/parent' : '/guardian'} replace />;
}
