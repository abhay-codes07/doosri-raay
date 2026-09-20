import { useEffect, useState, type ReactNode } from 'react';
import { useT } from '../i18n/LangContext';
import { secondsUntil } from '../lib/dates';

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="row" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label && <span>{label}</span>}
    </span>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useT();
  return (
    <div className="alert alert-error" role="alert">
      <div className="row spread">
        <span>{message}</span>
        {onRetry && (
          <button type="button" className="btn" onClick={onRetry}>
            {t('retry')}
          </button>
        )}
      </div>
    </div>
  );
}

/** Empty state: one emoji (no external assets) beside the sentence. */
export function Empty({ icon = '🌿', children }: { icon?: string; children: ReactNode }) {
  return (
    <p className="empty">
      <span className="empty-icon" aria-hidden="true">
        {icon}
      </span>
      <span>{children}</span>
    </p>
  );
}

export function CopyButton({ text, label }: { text: string; label?: string }) {
  const { t } = useT();
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (!done) return undefined;
    const id = window.setTimeout(() => setDone(false), 1800);
    return () => window.clearTimeout(id);
  }, [done]);
  return (
    <button
      type="button"
      className="btn"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
        } catch {
          // clipboard blocked: select-all fallback is the user's own copy gesture
          window.prompt(t('copy'), text);
        }
      }}
    >
      {done ? t('copied') : (label ?? t('copy'))}
    </button>
  );
}

/** Live countdown to an ISO timestamp. */
export function Countdown({ until }: { until?: string | null }) {
  const { t } = useT();
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, []);
  const secs = secondsUntil(until);
  if (secs === null) return null;
  if (secs <= 0) return <span className="badge badge-amber timer">{t('expired')}</span>;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return (
    <span className="badge timer" aria-label={t('expiresIn')}>
      {t('expiresIn')}: {m}:{String(s).padStart(2, '0')}
    </span>
  );
}

export function Section({ title, children, aside }: { title: ReactNode; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="card">
      <div className="card-title spread row">
        <h2 style={{ fontSize: '1.15em' }}>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}
