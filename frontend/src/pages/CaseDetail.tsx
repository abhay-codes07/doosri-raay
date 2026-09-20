import { useCallback, useId, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApi } from '../api/context';
import { describeError } from '../api/client';
import type { Case, CompleteTaskBody, RuleSource, Txn } from '../api/types';
import { TaskCard } from '../components/TaskCard';
import { CopyButton, ErrorBox, Section, Spinner } from '../components/ui';
import { usePoll, useProfile } from '../hooks/useProfile';
import { useT } from '../i18n/LangContext';
import type { StringKey } from '../i18n/strings';
import { datetimeLocalFromIso, isoFromDatetimeLocal } from '../lib/dates';
import { getPreview } from '../lib/storage';
import { REF_MAX_LEN, classifyReference, parseAmount, txnIssues, type TxnIssue } from '../lib/validate';

const STEPS: ReadonlyArray<{ id: string; key: StringKey }> = [
  { id: 'open', key: 'statusOpen' },
  { id: 'awaiting_confirmation', key: 'statusAwaitingConfirmation' },
  { id: 'building', key: 'statusBuilding' },
  { id: 'awaiting_1930', key: 'statusAwaiting1930' },
  { id: 'awaiting_ncrp', key: 'statusAwaitingNcrp' },
  { id: 'mrm', key: 'statusMrm' },
  { id: 'filed', key: 'statusFiled' },
];

interface EditableTxn extends Txn {
  amountText: string;
  /** "YYYY-MM-DDTHH:mm" in IST for the datetime-local input; converted to ISO (+05:30) on submit. */
  timestampLocal: string;
}

const ISSUE_KEY: Record<TxnIssue, StringKey> = {
  utr_invalid: 'utrInvalid',
  amount_invalid: 'amountInvalid',
  payee_missing: 'payeeMissing',
  timestamp_missing: 'timestampMissing',
};

const rowIssues = (x: EditableTxn): TxnIssue[] =>
  txnIssues({ utr: x.utr, amountText: x.amountText, payee: x.payee, timestampIso: isoFromDatetimeLocal(x.timestampLocal) });

function toEditable(txns: Txn[]): EditableTxn[] {
  return txns.map((x) => ({
    utr: typeof x.utr === 'string' ? x.utr : '',
    amount: typeof x.amount === 'number' ? x.amount : null,
    amountText: typeof x.amount === 'number' ? String(x.amount) : '',
    payee: typeof x.payee === 'string' ? x.payee : '',
    timestamp: typeof x.timestamp === 'string' ? x.timestamp : '',
    timestampLocal: datetimeLocalFromIso(typeof x.timestamp === 'string' ? x.timestamp : ''),
    app: typeof x.app === 'string' ? x.app : '',
    objectKey: typeof x.objectKey === 'string' ? x.objectKey : undefined,
    rail: typeof x.rail === 'string' ? x.rail : undefined,
    valid: x.valid,
    issues: Array.isArray(x.issues) ? x.issues.filter((i): i is string => typeof i === 'string') : [],
    manual: x.manual === true,
  }));
}

const blankTxn = (): EditableTxn => ({
  utr: '',
  amount: null,
  amountText: '',
  payee: '',
  timestamp: '',
  timestampLocal: '',
  app: '',
  issues: [],
  manual: true,
});

export function CaseDetailPage() {
  const { id = '' } = useParams();
  const api = useApi();
  const { t, lang } = useT();
  const profile = useProfile(true);
  const parent = profile.data?.circle?.members.find((m) => m.role === 'parent');
  const [terminal, setTerminal] = useState(false);
  const kase = usePoll(() => api.getCase(id), 3000, [api, id], Boolean(id) && !terminal);
  const c: Case | null = kase.data;
  const reachedEnd = c !== null && (c.status === 'filed' || c.status === 'error');
  if (reachedEnd && !terminal) setTerminal(true); // stop polling once the case is final (adjust state on render)

  // tasks for this case (call_1930 / ncrp_filed / mrm / confirm_fields)
  const tasks = usePoll(() => api.listTasks(), 5000, [api]);
  const caseTasks = useMemo(
    () => (tasks.data?.tasks ?? []).filter((tk) => tk.context?.caseId === id || tk.taskId === c?.openTaskId),
    [tasks.data, id, c?.openTaskId],
  );
  const onComplete = useCallback(
    async (taskId: string, body: CompleteTaskBody) => {
      await api.completeTask(taskId, body);
      await Promise.all([tasks.refresh(), kase.refresh()]);
    },
    [api, tasks, kase],
  );

  if (!id) return <ErrorBox message={t('caseNotFound')} />;
  if (kase.error && !c) return <ErrorBox message={kase.error} onRetry={() => void kase.refresh()} />;
  if (!c) return <Spinner label={t('loading')} />;

  const stepIndex = STEPS.findIndex((s) => s.id === c.status);
  const isError = c.status === 'error';
  const a = c.artifacts;
  const confirmTaskId =
    c.openTaskId ?? caseTasks.find((tk) => tk.kind === 'confirm_fields')?.taskId;

  return (
    <div className="page-narrow" style={{ margin: '0 auto' }}>
      <p>
        <Link to="/guardian">← {t('back')}</Link>
      </p>
      <div className="row spread">
        <h1 style={{ fontSize: '1.4em', margin: '0 0 8px' }}>
          {t('caseTitle')}: {c.victimName ?? c.caseId.slice(0, 8)}
        </h1>
        {kase.loading && <Spinner />}
      </div>
      <p className="muted small" style={{ marginTop: 0 }}>
        {c.state ?? ''} {c.incidentDate ? `· ${c.incidentDate}` : ''} · {c.caseId}
      </p>

      <ol className="stepper" aria-label="status">
        {STEPS.map((s, i) => (
          <li
            key={s.id}
            className={isError ? (i < stepIndex ? 'done' : '') : i < stepIndex ? 'done' : i === stepIndex ? 'current' : ''}
            aria-current={i === stepIndex ? 'step' : undefined}
          >
            {i < stepIndex ? '✓ ' : ''}
            {t(s.key)}
          </li>
        ))}
        {isError && <li className="error">{t('statusError')}</li>}
      </ol>

      {isError && <ErrorBox message={c.error ?? t('caseError')} />}

      {(c.status === 'open' || (c.status === 'awaiting_confirmation' && !c.extracted)) && (
        <section className="card">
          <Spinner label={t('extractedWaiting')} />
        </section>
      )}

      {c.status === 'awaiting_confirmation' && c.extracted && (
        <ConfirmTxns
          key={confirmTaskId ?? 'no-task'}
          kase={c}
          taskId={confirmTaskId}
          onConfirm={async (txns) => {
            if (!confirmTaskId) throw new Error(t('caseNotFound'));
            await onComplete(confirmTaskId, { outcome: 'confirmed', txns });
          }}
        />
      )}

      {c.status === 'building' && (
        <section className="card">
          <Spinner label={t('statusBuilding')} />
        </section>
      )}

      {c.confirmedTxns && c.confirmedTxns.length > 0 && c.status !== 'awaiting_confirmation' && (
        <Section title={t('confirmedTxns')}>
          <ul className="list-plain">
            {c.confirmedTxns.map((x, i) => (
              <li key={`${x.utr}-${i}`}>
                {x.utr} · ₹{x.amount ?? '—'} · {x.payee} · {x.app} · {x.timestamp}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {caseTasks.filter((tk) => tk.kind !== 'confirm_fields').length > 0 && (
        <Section title={t('taskActions')}>
          <div className="stack">
            {caseTasks
              .filter((tk) => tk.kind !== 'confirm_fields')
              .map((tk) => (
                <TaskCard key={tk.taskId} task={tk} parentName={parent?.name} parentPhone={parent?.phone} onComplete={onComplete} inlineCase />
              ))}
          </div>
        </Section>
      )}

      {c.ackNo && (
        <p className="badge badge-ok">
          {t('ackRecorded')}: {c.ackNo}
        </p>
      )}

      {a && (
        <div className="stack mt" style={{ gap: 16 }}>
          <h2 style={{ fontSize: '1.2em', margin: 0 }}>{t('artifactsTitle')}</h2>

          {a.script1930 && (
            <Section
              title={t('script1930')}
              aside={
                <span className="row">
                  <a className="btn btn-primary" href="tel:1930">
                    {t('call1930')}
                  </a>
                  <CopyButton text={a.script1930} />
                </span>
              }
            >
              <pre className="pre">{a.script1930}</pre>
            </Section>
          )}

          {a.ncrpNarrative && (
            <Section
              title={t('narrative')}
              aside={
                <span className="row">
                  <span className="badge">
                    {a.ncrpNarrativeLength ?? a.ncrpNarrative.length} {t('chars')}
                  </span>
                  <CopyButton text={a.ncrpNarrative} />
                </span>
              }
            >
              <pre className="pre">{a.ncrpNarrative}</pre>
              <p className="mt">
                <a className="btn" href={a.ncrp?.portal ?? 'https://cybercrime.gov.in'} target="_blank" rel="noreferrer">
                  {t('openNcrp')}
                </a>
              </p>
              <SourceLine source={a.ncrp?.source} caveat={a.ncrp?.caveat} />
            </Section>
          )}

          {a.freezeLetter && (
            <Section title={t('freezeLetter')} aside={<CopyButton text={a.freezeLetter} />}>
              <pre className="pre">{a.freezeLetter}</pre>
            </Section>
          )}

          {a.ezeroFir && (
            <Section title={t('ezero')}>
              <p>
                {typeof a.ezeroFir.thresholdInr === 'number'
                  ? t('ezeroThreshold', {
                      state: a.ezeroFir.state ?? c.state ?? '',
                      amount: a.ezeroFir.thresholdInr.toLocaleString(lang === 'hi' ? 'hi-IN' : 'en-IN'),
                    })
                  : t('ezeroNoThreshold', { state: a.ezeroFir.state ?? c.state ?? '' })}
              </p>
              {a.ezeroFir.note && <p className="muted">{a.ezeroFir.note}</p>}
              <SourceLine source={a.ezeroFir.source ?? (a.ezeroFir.sourceUrl ? { url: a.ezeroFir.sourceUrl } : undefined)} caveat={a.ezeroFir.caveat} />
            </Section>
          )}

          {a.mrm && (
            <Section title={t('mrmTitle')}>
              <p>
                <span className={`badge ${a.mrm.eligible ? 'badge-ok' : ''}`}>{a.mrm.eligible ? t('mrmEligible') : t('mrmNotEligible')}</span>{' '}
                {a.mrm.firRequired && <span className="badge badge-amber">{t('mrmFirRequired')}</span>}
              </p>
              {a.mrm.checklist && a.mrm.checklist.length > 0 && (
                <ul className="list-plain">
                  {a.mrm.checklist.map((item, i) => (
                    <li key={`${i}-${item}`}>{item}</li>
                  ))}
                </ul>
              )}
              <p className="alert mt">
                <strong>{t('refundGuard')}</strong> {t('refundGuardSub')}
              </p>
              <p>
                <a className="btn" href={a.mrm.portal ?? 'https://mrm-ncrp.mha.gov.in'} target="_blank" rel="noreferrer">
                  {t('mrmPortal')}
                </a>
              </p>
              <SourceLine source={a.mrm.source} caveat={a.mrm.caveat} />
            </Section>
          )}
        </div>
      )}
    </div>
  );
}

function ConfirmTxns({
  kase,
  taskId,
  onConfirm,
}: {
  kase: Case;
  taskId?: string;
  onConfirm: (txns: Txn[]) => Promise<void>;
}) {
  const { t, lang } = useT();
  const uid = useId();
  const [txns, setTxns] = useState<EditableTxn[]>(() => toEditable(kase.extracted?.txns ?? []));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const keys = kase.objectKeys ?? [];
  const nothingExtracted = (kase.extracted?.txns ?? []).length === 0;

  const update = (i: number, patch: Partial<EditableTxn>) =>
    setTxns((cur) => cur.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const addRow = () => setTxns((cur) => [...cur, blankTxn()]);
  const removeRow = (i: number) => setTxns((cur) => cur.filter((_, j) => j !== i));

  // Mirror the server's rules so a confirm never bounces with 400 invalid_txns.
  const allValid = txns.length > 0 && txns.every((x) => rowIssues(x).length === 0);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await onConfirm(
        txns.map((x) => ({
          utr: x.utr.trim(),
          amount: parseAmount(x.amountText),
          payee: x.payee.trim(),
          timestamp: isoFromDatetimeLocal(x.timestampLocal),
          app: x.app.trim(),
          objectKey: x.objectKey,
          rail: classifyReference(x.utr).rail ?? undefined,
          manual: x.manual ? true : undefined,
        })),
      );
    } catch (e) {
      setError(describeError(e, lang));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Section title={t('extractedTitle')}>
      {nothingExtracted && (
        <div className="alert" role="status">
          <p style={{ margin: '0 0 4px', fontWeight: 600 }}>{t('noTxnsFound')}</p>
          <p className="small" style={{ margin: 0 }}>
            {t('noTxnsFoundSub')}
          </p>
        </div>
      )}
      <div className="stack" style={{ gap: 18 }}>
        {txns.map((x, i) => {
          // Pair each row with the screenshot it came from; a single-screenshot case has no ambiguity.
          const preview = x.objectKey ? getPreview(x.objectKey) : keys.length === 1 && !x.manual ? getPreview(keys[0]) : null;
          const ref = classifyReference(x.utr);
          const issues = rowIssues(x);
          const has = (k: TxnIssue) => issues.includes(k);
          const id = (f: string) => `${uid}-${f}-${i}`;
          return (
            <div key={i} className="txn">
              <div>
                {preview ? (
                  <img className="thumb" src={preview} alt={`${t('txn')} ${i + 1}`} />
                ) : (
                  <div className="placeholder">{x.manual ? t('manualRow') : t('noPreview')}</div>
                )}
              </div>
              <div>
                <div className="row spread">
                  <h3 style={{ margin: '0 0 8px', fontSize: '1em' }}>
                    {t('txn')} {i + 1} {x.manual && <span className="badge">{t('manualRow')}</span>}
                  </h3>
                  <button type="button" className="btn btn-quiet small" disabled={busy} onClick={() => removeRow(i)} aria-label={`${t('removeTxn')} ${i + 1}`}>
                    {t('remove')}
                  </button>
                </div>
                <div className="field">
                  <label htmlFor={id('utr')}>{t('utr')}</label>
                  <input
                    id={id('utr')}
                    value={x.utr}
                    autoComplete="off"
                    autoCapitalize="characters"
                    maxLength={REF_MAX_LEN}
                    aria-invalid={!ref.valid}
                    aria-describedby={id('utr-err')}
                    onChange={(e) => update(i, { utr: e.target.value.replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, REF_MAX_LEN) })}
                  />
                  <span id={id('utr-err')} className={ref.valid ? 'help' : 'err'}>
                    {ref.valid ? (
                      <>
                        <span className="badge badge-ok">{ref.rail}</span> {x.utr.length}
                      </>
                    ) : (
                      t('utrInvalid')
                    )}
                  </span>
                </div>
                <div className="field">
                  <label htmlFor={id('amt')}>{t('amount')}</label>
                  <input
                    id={id('amt')}
                    value={x.amountText}
                    inputMode="decimal"
                    aria-invalid={has('amount_invalid')}
                    aria-describedby={id('amt-err')}
                    onChange={(e) => update(i, { amountText: e.target.value })}
                  />
                  {has('amount_invalid') && (
                    <span id={id('amt-err')} className="err">
                      {t('amountInvalid')}
                    </span>
                  )}
                </div>
                <div className="field">
                  <label htmlFor={id('payee')}>{t('payee')}</label>
                  <input
                    id={id('payee')}
                    value={x.payee}
                    aria-invalid={has('payee_missing')}
                    aria-describedby={id('payee-err')}
                    onChange={(e) => update(i, { payee: e.target.value })}
                  />
                  {has('payee_missing') && (
                    <span id={id('payee-err')} className="err">
                      {t('payeeMissing')}
                    </span>
                  )}
                </div>
                <div className="field">
                  <label htmlFor={id('ts')}>{t('timestamp')}</label>
                  <input
                    id={id('ts')}
                    type="datetime-local"
                    value={x.timestampLocal}
                    aria-invalid={has('timestamp_missing')}
                    aria-describedby={id('ts-err')}
                    onChange={(e) => update(i, { timestampLocal: e.target.value })}
                  />
                  <span id={id('ts-err')} className={has('timestamp_missing') ? 'err' : 'help'}>
                    {has('timestamp_missing') ? t('timestampMissing') : t('timestampHelp')}
                  </span>
                </div>
                <div className="field">
                  <label htmlFor={id('app')}>{t('appLabel')}</label>
                  <input id={id('app')} value={x.app} placeholder="PhonePe / GPay / Paytm / bank" onChange={(e) => update(i, { app: e.target.value })} />
                </div>
                {x.issues && x.issues.length > 0 && issues.length > 0 && (
                  <div className="alert">
                    <strong>{t('issues')}:</strong>
                    <ul className="list-plain">
                      {issues.map((iss) => (
                        <li key={iss}>{t(ISSUE_KEY[iss])}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt">
        <button type="button" className="btn" disabled={busy || txns.length >= 20} onClick={addRow}>
          + {t('addManually')}
        </button>
      </p>
      {error && (
        <p className="alert alert-error mt" role="alert">
          {error}
        </p>
      )}
      <div className="row mt">
        <button type="button" className="btn btn-primary btn-big" disabled={busy || !allValid || !taskId} onClick={submit}>
          {busy ? <Spinner label={t('confirming')} /> : t('confirm')}
        </button>
        {txns.length > 0 && !allValid && <span className="muted small">{t('fixUtr')}</span>}
        {!taskId && <span className="muted small">{t('loading')}</span>}
      </div>
    </Section>
  );
}

/** "Source: outlet, date" (linked) plus the rule's caveat, under the rule-based cards. */
function SourceLine({ source, caveat }: { source?: RuleSource; caveat?: string }) {
  const { t } = useT();
  const outlet = typeof source?.outlet === 'string' ? source.outlet.trim() : '';
  const date = typeof source?.date === 'string' ? source.date.trim() : '';
  const url = typeof source?.url === 'string' && /^https?:\/\//.test(source.url) ? source.url : '';
  const label = [outlet, date].filter(Boolean).join(', ') || (url ? url.replace(/^https?:\/\//, '').split('/')[0] : '');
  if (!label && !caveat) return null;
  return (
    <div className="source-line small muted">
      {label && (
        <p style={{ margin: '8px 0 0' }}>
          {t('source')}:{' '}
          {url ? (
            <a href={url} target="_blank" rel="noreferrer">
              {label}
            </a>
          ) : (
            label
          )}
        </p>
      )}
      {caveat && (
        <p style={{ margin: '4px 0 0' }} lang="en">
          {caveat}
        </p>
      )}
    </div>
  );
}
