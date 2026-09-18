import { useState } from 'react';
import { useApi, useApiIdentity } from '../api/context';
import { useT } from '../i18n/LangContext';
import { enablePush, pushSupport } from '../lib/push';
import { KEYS, readString, writeString } from '../lib/storage';

type State = 'idle' | 'working' | 'on' | 'denied' | 'unsupported' | 'ios' | 'failed';

function initialState(identity: string): State {
  const support = pushSupport();
  if (support === 'unsupported') return 'unsupported';
  if (support === 'ios_needs_install') return 'ios';
  if (Notification.permission === 'denied') return 'denied';
  if (readString(KEYS.pushDone(identity)) === '1' && Notification.permission === 'granted') return 'on';
  return 'idle';
}

export function PushButton() {
  const api = useApi();
  const identity = useApiIdentity();
  const { t } = useT();
  const [state, setState] = useState<State>(() => initialState(identity));
  const [detail, setDetail] = useState<string | null>(null);

  const onClick = async () => {
    setState('working');
    setDetail(null);
    const r = await enablePush(api);
    if (r.ok) {
      writeString(KEYS.pushDone(identity), '1');
      setState('on');
      return;
    }
    if (r.reason === 'denied') setState('denied');
    else if (r.reason === 'unsupported') setState('unsupported');
    else {
      setState('failed');
      setDetail(r.detail ?? r.reason);
    }
  };

  if (state === 'on') return <span className="badge badge-ok">{t('alertsEnabled')}</span>;
  if (state === 'unsupported') return <span className="muted small">{t('alertsUnsupported')}</span>;
  if (state === 'ios') return <span className="muted small">{t('alertsIos')}</span>;
  if (state === 'denied') return <span className="muted small">{t('alertsDenied')}</span>;
  return (
    <span className="row">
      <button type="button" className="btn" onClick={onClick} disabled={state === 'working'}>
        {state === 'working' ? t('enabling') : t('enableAlerts')}
      </button>
      {state === 'failed' && (
        <span className="small muted" role="alert">
          {t('alertsFailed')}
          {detail ? ` (${detail})` : ''}
        </span>
      )}
    </span>
  );
}
