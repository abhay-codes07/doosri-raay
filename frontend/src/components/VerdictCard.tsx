import { useState } from 'react';
import type { Verdict } from '../api/types';
import { Bi, useT } from '../i18n/LangContext';
import type { StringKey } from '../i18n/strings';

const TACTIC_KEYS: Record<string, StringKey> = {
  authority: 'tacticAuthority',
  urgency: 'tacticUrgency',
  secrecy: 'tacticSecrecy',
  payment: 'tacticPayment',
  payment_method_switch: 'tacticPayment',
  fear: 'tacticFear',
  isolation: 'tacticIsolation',
};

/**
 * Three-state verdict. All model output is rendered as plain text (never HTML).
 * The copy for `none` is fixed by the API contract.
 */
export function VerdictCard({
  verdict,
  guardianName,
  parentMode = false,
}: {
  verdict: Verdict;
  guardianName?: string;
  parentMode?: boolean;
}) {
  const { t, lang } = useT();
  const [sent, setSent] = useState(false);
  const state = verdict.state === 'likely' || verdict.state === 'watching' ? verdict.state : 'none';
  const titleKey: StringKey = state === 'likely' ? 'verdictLikely' : state === 'watching' ? 'verdictWatching' : 'verdictNone';
  const say = lang === 'hi' ? (verdict.sayHi ?? verdict.sayEn) : (verdict.sayEn ?? verdict.sayHi);
  const tactics = (verdict.tactics ?? []).filter((x): x is string => typeof x === 'string');
  const flags = (verdict.redFlags ?? []).filter((x): x is string => typeof x === 'string');
  const name = guardianName ?? t('familyGeneric');

  return (
    <div className={`verdict verdict-${state}`} role="status" aria-live="polite">
      <p className="verdict-title">
        {parentMode ? <Bi k={titleKey} /> : t(titleKey)}
      </p>
      {say && <p style={{ margin: '0 0 8px' }}>{say}</p>}
      {state !== 'none' && tactics.length > 0 && (
        <div>
          <strong>{t('tactics')}:</strong>
          <ul className="list-plain">
            {tactics.map((tc) => {
              const key = TACTIC_KEYS[tc.toLowerCase()];
              return <li key={tc}>{key ? t(key) : tc}</li>;
            })}
          </ul>
        </div>
      )}
      {state !== 'none' && flags.length > 0 && (
        <div>
          <strong>{t('redFlags')}:</strong>
          <ul className="list-plain">
            {flags.map((f, i) => (
              <li key={`${i}-${f.slice(0, 12)}`}>{f}</li>
            ))}
          </ul>
        </div>
      )}
      {verdict.scamType && state !== 'none' && (
        <p className="small muted" style={{ margin: '8px 0 0' }}>
          {verdict.scamType.replace(/_/g, ' ').toLowerCase()}
        </p>
      )}
      <div className="row mt">
        {sent ? (
          <span className="badge badge-ok">{t('familySeeing', { name })}</span>
        ) : (
          <button type="button" className="btn" onClick={() => setSent(true)}>
            {parentMode ? <Bi k="sendToFamily" /> : t('sendToFamily')}
          </button>
        )}
      </div>
    </div>
  );
}
