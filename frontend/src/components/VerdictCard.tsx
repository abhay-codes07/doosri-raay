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
 *
 * The report is stored server-side, but nothing here claims a family member has seen it:
 * we only offer a direct call ("Parivaar se baat karein") when a family phone number is known.
 */
export function VerdictCard({
  verdict,
  familyName,
  familyPhone,
  parentMode = false,
}: {
  verdict: Verdict;
  /** Who the tel: link reaches (guardian1 for the parent, the parent for a guardian). */
  familyName?: string;
  familyPhone?: string;
  parentMode?: boolean;
}) {
  const { t, lang } = useT();
  const state = verdict.state === 'likely' || verdict.state === 'watching' ? verdict.state : 'none';
  const titleKey: StringKey = state === 'likely' ? 'verdictLikely' : state === 'watching' ? 'verdictWatching' : 'verdictNone';
  const say = lang === 'hi' ? (verdict.sayHi ?? verdict.sayEn) : (verdict.sayEn ?? verdict.sayHi);
  const tactics = (verdict.tactics ?? []).filter((x): x is string => typeof x === 'string');
  const flags = (verdict.redFlags ?? []).filter((x): x is string => typeof x === 'string');
  const phone = familyPhone?.replace(/[^\d+]/g, '') ?? '';
  const name = familyName ?? t('familyGeneric');

  return (
    <div className={`verdict verdict-${state}`} role="status" aria-live="polite">
      <p className="verdict-title">{parentMode ? <Bi k={titleKey} /> : t(titleKey)}</p>
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
      {state !== 'none' && (
        <p className="mt" style={{ fontWeight: 600, marginBottom: 8 }}>
          {parentMode ? <Bi k="talkToFamily" /> : t('talkToFamily')}
        </p>
      )}
      {phone && (
        <div className="row">
          <a className={`btn btn-big ${state !== 'none' ? 'btn-primary' : ''}`} href={`tel:${phone}`}>
            {t('callName', { name })}
          </a>
        </div>
      )}
    </div>
  );
}
