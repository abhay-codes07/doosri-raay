import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApi, useApiIdentity } from '../api/context';
import { isTaskExpired } from '../api/client';
import type { CaseSummary, CompleteTaskBody, LadderState, Report } from '../api/types';
import { PushButton } from '../components/PushButton';
import { ScreenshotCheck } from '../components/ScreenshotCheck';
import { SourcesPanel } from '../components/SourcesPanel';
import { TaskCard } from '../components/TaskCard';
import { VerdictCard } from '../components/VerdictCard';
import { Empty, ErrorBox, Section, Spinner } from '../components/ui';
import { usePoll } from '../hooks/useProfile';
import { useT } from '../i18n/LangContext';
import type { StringKey } from '../i18n/strings';
import { formatTimeIST, relativeTime } from '../lib/dates';
import { listReports } from '../lib/storage';

const LADDER_COPY: Record<LadderState, { key: StringKey; badge: string }> = {
  ok: { key: 'ladderOk', badge: 'badge-ok' },
  watching: { key: 'ladderWatching', badge: 'badge-amber' },
  escalated: { key: 'ladderEscalated', badge: 'badge-red' },
};

const STATUS_KEY: Record<string, StringKey> = {
  open: 'statusOpen',
  awaiting_confirmation: 'statusAwaitingConfirmation',
  building: 'statusBuilding',
  awaiting_1930: 'statusAwaiting1930',
  awaiting_ncrp: 'statusAwaitingNcrp',
  mrm: 'statusMrm',
  filed: 'statusFiled',
  error: 'statusError',
};

/** Guardian dashboard. Also rendered inside the /demo right pane. */
export function GuardianScreen({ embedded = false }: { embedded?: boolean }) {
  const api = useApi();
  const identity = useApiIdentity();
  const { t, lang } = useT();
  // The status card polls GET /profile alongside tasks so ladderState/lastCheckin update live.
  const profile = usePoll(() => api.getProfile(), 5000, [api]);
  const circle = profile.data?.circle ?? null;
  const parent = circle?.members.find((m) => m.role === 'parent') ?? null;
  const me = profile.data?.profile ?? null;

  const tasks = usePoll(() => api.listTasks(), 5000, [api]);
  const cases = usePoll(() => api.listCases(), 15000, [api]);

  const [notice, setNotice] = useState<string | null>(null);
  const onComplete = useCallback(
    async (taskId: string, body: CompleteTaskBody) => {
      try {
        await api.completeTask(taskId, body);
      } catch (e) {
        if (!isTaskExpired(e)) throw e;
        setNotice(t('taskExpiredNotice'));
        window.setTimeout(() => setNotice(null), 8000);
      }
      await Promise.all([tasks.refresh(), profile.refresh()]);
    },
    [api, tasks, profile, t],
  );

  const ladderState: LadderState | undefined =
    parent?.ladderState ?? (me?.role === 'parent' ? me.ladderState : undefined);
  const lastCheckin = parent?.lastCheckin ?? parent?.lastCheckinDate ?? me?.lastCheckin ?? me?.lastCheckinDate;

  return (
    <div className={embedded ? '' : 'page-narrow'} style={{ margin: '0 auto' }}>
      <div className="stack" style={{ gap: 16 }}>
        {/* Parent status */}
        <section className={`card ${ladderState ? `tone-${ladderState === 'ok' ? 'ok' : ladderState === 'watching' ? 'amber' : 'red'}` : ''}`}>
          <div className="card-title spread row">
            <h2 style={{ fontSize: '1.15em' }}>
              {t('parentStatus')}
              {parent?.name ? ` · ${parent.name}` : ''}
            </h2>
            {ladderState && <span className={`badge ${LADDER_COPY[ladderState].badge}`}>{ladderState}</span>}
          </div>
          {profile.loading && !profile.data && <Spinner label={t('loading')} />}
          {profile.error && !profile.data && <ErrorBox message={profile.error} onRetry={() => void profile.refresh()} />}
          {profile.data && !parent && (
            <p className="muted">
              {t('noParent')} <strong>{circle?.inviteCode ?? '—'}</strong>
            </p>
          )}
          {parent && (
            <>
              <p style={{ margin: '4px 0' }}>
                <strong>{t('lastCheckin')}:</strong>{' '}
                {lastCheckin ? `${formatTimeIST(lastCheckin, lang)} (${relativeTime(lastCheckin, lang)})` : t('noCheckinYet')}
              </p>
              {ladderState && <p style={{ margin: '4px 0' }}>{t(LADDER_COPY[ladderState].key)}</p>}
            </>
          )}
          <div className="row mt spread">
            <PushButton />
            {!embedded && (
              <Link className="btn btn-quiet" to="/settings">
                {t('settingsTitle')}
              </Link>
            )}
          </div>
        </section>

        {/* Open tasks */}
        <Section title={t('openTasks')} aside={tasks.loading ? <Spinner /> : null}>
          {notice && (
            <p className="alert" role="status">
              {notice}
            </p>
          )}
          {tasks.error && !tasks.data && <ErrorBox message={t('tasksError')} onRetry={() => void tasks.refresh()} />}
          {tasks.data && tasks.data.tasks.length === 0 && <Empty icon="🌿">{t('noTasks')}</Empty>}
          <div className="stack">
            {(tasks.data?.tasks ?? []).map((task) => (
              <TaskCard key={task.taskId} task={task} parentName={parent?.name} parentPhone={parent?.phone} onComplete={onComplete} />
            ))}
          </div>
        </Section>

        {/* Cases */}
        <Section
          title={t('casesTitle')}
          aside={
            <Link className="btn btn-primary" to="/case/new">
              {t('openCase')}
            </Link>
          }
        >
          {cases.error && !cases.data && <ErrorBox message={cases.error} onRetry={() => void cases.refresh()} />}
          {cases.data && cases.data.cases.length === 0 && <Empty icon="📂">{t('noCases')}</Empty>}
          <ul className="stack" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {(cases.data?.cases ?? []).map((c: CaseSummary) => (
              <li key={c.caseId} className="row spread">
                <Link to={`/case/${c.caseId}`}>
                  {c.victimName ?? c.caseId.slice(0, 8)} · {formatTimeIST(c.createdAt, lang)}
                </Link>
                <span className="badge">{STATUS_KEY[c.status] ? t(STATUS_KEY[c.status]) : c.status}</span>
              </li>
            ))}
          </ul>
        </Section>

        <ScreenshotCheck familyName={parent?.name} familyPhone={parent?.phone} />

        <RecentReports identity={identity} familyName={parent?.name} familyPhone={parent?.phone} />

        <SourcesPanel />
      </div>
    </div>
  );
}

function RecentReports({ identity, familyName, familyPhone }: { identity: string; familyName?: string; familyPhone?: string }) {
  const api = useApi();
  const { t } = useT();
  const refs = listReports(identity);
  const [reports, setReports] = useState<Record<string, Report | 'error'>>({});
  const [open, setOpen] = useState<string | null>(null);
  const ids = refs.map((r) => r.reportId).join(',');

  useEffect(() => {
    let alive = true;
    const load = async () => {
      for (const id of ids.split(',').filter(Boolean)) {
        try {
          const r = await api.getReport(id);
          if (alive) setReports((cur) => ({ ...cur, [id]: r }));
        } catch {
          if (alive) setReports((cur) => ({ ...cur, [id]: 'error' }));
        }
      }
    };
    void load();
    return () => {
      alive = false;
    };
  }, [api, ids]);

  return (
    <Section title={t('reportsTitle')}>
      {refs.length === 0 && <Empty icon="🔍">{t('noReports')}</Empty>}
      <ul className="stack" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {refs.map((ref) => {
          const r = reports[ref.reportId];
          const state = r && r !== 'error' ? r.verdict?.state : undefined;
          const badge = state === 'likely' ? 'badge-red' : state === 'watching' ? 'badge-amber' : 'badge';
          return (
            <li key={ref.reportId}>
              <div className="row spread">
                <button
                  type="button"
                  className="btn btn-quiet"
                  style={{ justifyContent: 'flex-start', textAlign: 'left' }}
                  onClick={() => setOpen(open === ref.reportId ? null : ref.reportId)}
                  aria-expanded={open === ref.reportId}
                >
                  {ref.label || ref.reportId.slice(0, 8)} · {relativeTime(ref.createdAt)}
                </button>
                {r === 'error' ? (
                  <span className="badge">{t('error')}</span>
                ) : r ? (
                  <span className={`badge ${badge}`}>{r.status === 'done' ? (state ?? '—') : r.status}</span>
                ) : (
                  <Spinner />
                )}
              </div>
              {open === ref.reportId && r && r !== 'error' && r.verdict && (
                <VerdictCard verdict={r.verdict} familyName={familyName} familyPhone={familyPhone} />
              )}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}
