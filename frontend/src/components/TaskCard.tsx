import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { CompleteTaskBody, Task } from '../api/types';
import { useT } from '../i18n/LangContext';
import type { StringKey } from '../i18n/strings';
import { formatTimeIST } from '../lib/dates';
import { Countdown } from './ui';
import { ACK_RE } from '../lib/validate';

export interface TaskCardProps {
  task: Task;
  parentName?: string;
  parentPhone?: string;
  onComplete: (taskId: string, body: CompleteTaskBody) => Promise<void>;
  /** Hide the "open the case" link when already on that case page. */
  inlineCase?: boolean;
}

const KIND_LABEL: Record<string, StringKey> = {
  guardian_call: 'taskKindGuardianCall',
  neighbour: 'taskKindNeighbour',
  emergency: 'taskKindEmergency',
  sos: 'taskKindSos',
  confirm_fields: 'taskKindConfirm',
  call_1930: 'taskKindCall1930',
  ncrp_filed: 'taskKindNcrp',
  mrm: 'taskKindMrm',
  puchho_family: 'taskKindPuchho',
};

const OUTCOME_LABEL: Record<string, StringKey> = {
  reached: 'reached',
  no_answer: 'noAnswer',
  done: 'done',
  later: 'later',
  filed: 'submitAck',
  yes: 'yesItsMe',
  no: 'noNotMe',
  confirmed: 'confirm',
};


function firstPhone(text: string): string | null {
  const m = text.match(/(\+91[\s-]?\d{5}[\s-]?\d{5}|\b\d{10}\b)/);
  return m ? m[1].replace(/[\s-]/g, '') : null;
}

function firstUrl(text: string): string | null {
  const m = text.match(/https?:\/\/\S+/);
  return m ? m[0] : null;
}

function asString(v: unknown): string | undefined {
  return typeof v === 'string' && v.trim() ? v : undefined;
}

function asStringList(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
}

export function TaskCard({ task, parentName, parentPhone, onComplete, inlineCase = false }: TaskCardProps) {
  const { t, lang } = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ackNo, setAckNo] = useState('');
  const [codeWord, setCodeWord] = useState('');
  const [ticks, setTicks] = useState<Record<number, boolean>>({});

  const ctx = task.context ?? {};
  const kind = task.kind;
  const text = lang === 'hi' && task.textHi ? task.textHi : task.text;
  const allowed = task.allowedOutcomes?.length ? task.allowedOutcomes : defaultOutcomes(kind);
  const label = KIND_LABEL[kind] ? t(KIND_LABEL[kind]) : t('taskKindInfo');
  const parent = parentName ?? (lang === 'hi' ? 'माता-पिता' : 'your parent');

  const complete = async (body: CompleteTaskBody) => {
    setBusy(true);
    setError(null);
    try {
      await onComplete(task.taskId, body);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const outcomeButton = (outcome: string, className = 'btn', extra?: Partial<CompleteTaskBody>) =>
    allowed.includes(outcome) ? (
      <button
        key={outcome}
        type="button"
        className={`${className} btn-big`}
        disabled={busy}
        onClick={() => complete({ outcome, ...extra })}
      >
        {OUTCOME_LABEL[outcome] ? t(OUTCOME_LABEL[outcome]) : outcome}
      </button>
    ) : null;

  const neighbour = ctx.neighbour ?? {};
  const neighbourPhone = asString(neighbour.phone) ?? firstPhone(text);
  const address = asString(ctx.address) ?? asString(neighbour.address) ?? '';
  const since = asString(ctx.since) ? formatTimeIST(asString(ctx.since), lang) : formatTimeIST(task.createdAt, lang);
  const mapsUrl =
    asString(ctx.mapsUrl) ??
    (typeof ctx.lat === 'number' && typeof ctx.lon === 'number'
      ? `https://maps.google.com/?q=${ctx.lat},${ctx.lon}`
      : firstUrl(text));
  const caseId = asString(ctx.caseId);
  const checklist = asStringList(ctx.checklist);

  let body: ReactNode;
  switch (kind) {
    case 'guardian_call':
      body = (
        <div className="task-actions">
          {parentPhone && (
            <a className="btn btn-primary btn-big" href={`tel:${parentPhone}`}>
              {t('callNow')}
            </a>
          )}
          {outcomeButton('reached', 'btn btn-ok')}
          {outcomeButton('no_answer', 'btn btn-danger')}
        </div>
      );
      break;
    case 'neighbour':
      body = (
        <>
          <p className="pre">
            {asString(ctx.scriptHi) && lang === 'hi'
              ? asString(ctx.scriptHi)
              : (asString(ctx.script) ??
                t('scriptNeighbour', {
                  neighbour: asString(neighbour.name) ?? (lang === 'hi' ? 'पड़ोसी' : 'neighbour'),
                  parent,
                  address: address || '—',
                }))}
          </p>
          {address && (
            <p>
              <strong>{t('addressLabel')}:</strong> {address}
            </p>
          )}
          <div className="task-actions">
            {neighbourPhone && (
              <a className="btn btn-primary btn-big" href={`tel:${neighbourPhone}`}>
                {t('callNeighbour')}
              </a>
            )}
            {outcomeButton('reached', 'btn btn-ok')}
            {outcomeButton('no_answer', 'btn btn-danger')}
          </div>
        </>
      );
      break;
    case 'emergency':
      body = (
        <>
          <p className="pre">{asString(ctx.script) ?? t('script112', { since: since || '—', address: address || '—' })}</p>
          <div className="task-actions">
            <a className="btn btn-danger btn-big" href="tel:112">
              {t('call112')}
            </a>
            {outcomeButton('done')}
          </div>
        </>
      );
      break;
    case 'sos':
      body = (
        <div className="task-actions">
          {mapsUrl && (
            <a className="btn btn-primary btn-big" href={mapsUrl} target="_blank" rel="noreferrer">
              {t('mapLink')}
            </a>
          )}
          {parentPhone && (
            <a className="btn btn-danger btn-big" href={`tel:${parentPhone}`}>
              {t('callNow')}
            </a>
          )}
          {outcomeButton('done')}
        </div>
      );
      break;
    case 'confirm_fields':
      body = inlineCase ? null : (
        <div className="task-actions">
          {caseId ? (
            <Link className="btn btn-primary btn-big" to={`/case/${caseId}`}>
              {t('openTheCase')}
            </Link>
          ) : (
            <span className="muted">{t('caseNotFound')}</span>
          )}
        </div>
      );
      break;
    case 'call_1930':
      body = (
        <>
          <p className="pre">{asString(ctx.script) ?? t('script1930Short')}</p>
          <div className="task-actions">
            <a className="btn btn-primary btn-big" href="tel:1930">
              {t('call1930')}
            </a>
            {outcomeButton('done', 'btn btn-ok')}
            {outcomeButton('later')}
          </div>
          {caseId && !inlineCase && (
            <p className="mt">
              <Link to={`/case/${caseId}`}>{t('openTheCase')}</Link>
            </p>
          )}
        </>
      );
      break;
    case 'ncrp_filed': {
      const valid = ACK_RE.test(ackNo.trim());
      body = (
        <>
          <div className="field">
            <label htmlFor={`ack-${task.taskId}`}>{t('ackNo')}</label>
            <input
              id={`ack-${task.taskId}`}
              inputMode="numeric"
              autoComplete="off"
              maxLength={14}
              value={ackNo}
              aria-invalid={ackNo.length > 0 && !valid}
              aria-describedby={`ack-help-${task.taskId}`}
              onChange={(e) => setAckNo(e.target.value.replace(/\D/g, ''))}
            />
            <span id={`ack-help-${task.taskId}`} className={ackNo.length > 0 && !valid ? 'err' : 'help'}>
              {ackNo.length > 0 && !valid ? t('ackNoInvalid') : t('ackNoHelp')}
            </span>
          </div>
          <div className="task-actions">
            <a className="btn btn-big" href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">
              {t('openNcrp')}
            </a>
            <button
              type="button"
              className="btn btn-ok btn-big"
              disabled={busy || !valid}
              onClick={() => complete({ outcome: 'filed', ackNo: ackNo.trim() })}
            >
              {t('submitAck')}
            </button>
          </div>
          {caseId && !inlineCase && (
            <p className="mt">
              <Link to={`/case/${caseId}`}>{t('openTheCase')}</Link>
            </p>
          )}
        </>
      );
      break;
    }
    case 'mrm':
      body = (
        <>
          {checklist.length > 0 && (
            <div className="stack" style={{ marginBottom: 12 }}>
              {checklist.map((item, i) => (
                <label key={`${i}-${item}`} className={`check ${ticks[i] ? 'done' : ''}`}>
                  <input
                    type="checkbox"
                    checked={Boolean(ticks[i])}
                    onChange={(e) => setTicks({ ...ticks, [i]: e.target.checked })}
                  />
                  <span>{item}</span>
                </label>
              ))}
            </div>
          )}
          <p className="alert">
            <strong>{t('refundGuard')}</strong> {t('refundGuardSub')}
          </p>
          <div className="task-actions">
            <a className="btn btn-big" href="https://mrm-ncrp.mha.gov.in" target="_blank" rel="noreferrer">
              {t('mrmPortal')}
            </a>
            {outcomeButton('done', 'btn btn-ok')}
          </div>
        </>
      );
      break;
    case 'puchho_family':
      body = (
        <>
          <div className="field">
            <label htmlFor={`cw-${task.taskId}`}>{t('codeWordInput')}</label>
            <input
              id={`cw-${task.taskId}`}
              value={codeWord}
              autoComplete="off"
              onChange={(e) => setCodeWord(e.target.value)}
              aria-describedby={`cw-help-${task.taskId}`}
            />
            <span id={`cw-help-${task.taskId}`} className="help">
              {t('codeWordAsk')}
            </span>
          </div>
          <div className="task-actions">
            {outcomeButton('yes', 'btn btn-ok', { codeWord: codeWord.trim() })}
            {outcomeButton('no', 'btn btn-danger')}
          </div>
        </>
      );
      break;
    default:
      body = allowed.length > 0 ? <div className="task-actions">{allowed.map((o) => outcomeButton(o))}</div> : null;
  }

  return (
    <article className={`card task kind-${kind}`} aria-labelledby={`task-${task.taskId}`}>
      <div className="row spread">
        <div className="row">
          <span className="badge">{label}</span>
          {typeof ctx.rung === 'number' && (
            <span className="badge">
              {t('rung')} {ctx.rung}
            </span>
          )}
          {task.assigneeName && <span className="small muted">{task.assigneeName}</span>}
        </div>
        <Countdown until={task.expiresAt} />
      </div>
      <h3 id={`task-${task.taskId}`} className="sr-only">
        {label}
      </h3>
      <p className="task-text">{text}</p>
      {body}
      {error && (
        <p className="err" role="alert" style={{ color: 'var(--red)' }}>
          {error}
        </p>
      )}
      {busy && <p className="small muted">{t('completing')}</p>}
    </article>
  );
}

function defaultOutcomes(kind: string): string[] {
  switch (kind) {
    case 'guardian_call':
    case 'neighbour':
      return ['reached', 'no_answer'];
    case 'emergency':
    case 'sos':
    case 'mrm':
      return ['done'];
    case 'call_1930':
      return ['done', 'later'];
    case 'ncrp_filed':
      return ['filed'];
    case 'confirm_fields':
      return ['confirmed'];
    case 'puchho_family':
      return ['yes', 'no'];
    default:
      return [];
  }
}
