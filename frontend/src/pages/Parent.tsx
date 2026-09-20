import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApi, useApiIdentity } from '../api/context';
import { describeError, isAbort } from '../api/client';
import type { PuchhoAuthorityResponse, PuchhoStatus } from '../api/types';
import { ScreenshotCheck } from '../components/ScreenshotCheck';
import { ErrorBox, Spinner } from '../components/ui';
import thoughts from '../data/thoughts.json';
import { useProfile } from '../hooks/useProfile';
import { Bi, LangProvider, useT } from '../i18n/LangContext';
import { dayOfYearIST, formatDateEn, formatDateHi, istDateString } from '../lib/dates';
import { geoPermissionState, retryInBackground, sosLocation, startPositionWatch } from '../lib/geo';
import { moonEmoji, tithiForIstDay, vikramSamvat } from '../lib/panchang';
import { normalizeMedicines } from '../lib/medicines';
import { KEYS, readJson, readString, writeJson, writeString } from '../lib/storage';
import { describeWeatherCode, fetchWeather, staleWeather, type Weather } from '../lib/weather';

const TRIPLE_TAP_WINDOW_MS = 1500;
const CHECKIN_RETRY_MS = 30000;

/**
 * The Panchang tile. Everything here is ordinary and useful; nothing mentions alerts or the ladder.
 * Opening it posts the daily check-in silently. Triple-tapping the date sends a covert SOS.
 */
export function ParentScreen({ embedded = false, onSignOut }: { embedded?: boolean; onSignOut?: () => void }) {
  return (
    <LangProvider lang="hi" setLang={() => undefined}>
      <ParentTile embedded={embedded} onSignOut={onSignOut} />
    </LangProvider>
  );
}

function ParentTile({ embedded, onSignOut }: { embedded: boolean; onSignOut?: () => void }) {
  const api = useApi();
  const identity = useApiIdentity();
  const { t } = useT();
  const uid = useId();
  const { data, loading, error, reload } = useProfile(true);
  const profile = data?.profile ?? null;
  const guardian1 = data?.circle?.members.find((m) => m.role === 'guardian1');
  const guardianName = guardian1?.name;

  // A 60 s tick keeps the date honest when the tile stays open across IST midnight and lets the
  // check-in effect below run again for the new day.
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(id);
  }, []);
  const today = istDateString(now);
  const tithi = useMemo(() => tithiForIstDay(now), [now]);
  const samvat = useMemo(() => vikramSamvat(now), [now]);
  const thought = thoughts[dayOfYearIST(now) % thoughts.length];

  // ---- silent daily check-in (once per IST day, retry on failure) ----
  // The server's lastCheckinDate (GET /profile) wins over the local marker: after a demo reset or
  // on a second device the marker can say "done" while the server has no check-in for today.
  const serverCheckinDate = profile?.lastCheckinDate;
  const postedDay = useRef<string | null>(null);
  useEffect(() => {
    if (!profile || profile.role !== 'parent') return undefined;
    let timer: number | undefined;
    let cancelled = false;
    const attempt = async () => {
      if (cancelled) return;
      const day = istDateString();
      if (postedDay.current === day) return;
      const doneToday =
        typeof serverCheckinDate === 'string' ? serverCheckinDate === day : readString(KEYS.checkinDay(identity)) === day;
      if (doneToday) {
        writeString(KEYS.checkinDay(identity), day);
        return;
      }
      try {
        await api.checkin('tile');
        postedDay.current = day;
        writeString(KEYS.checkinDay(identity), day);
      } catch {
        timer = window.setTimeout(attempt, CHECKIN_RETRY_MS);
      }
    };
    void attempt();
    const onVisible = () => {
      if (document.visibilityState === 'visible') void attempt();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
    // `today` re-arms this effect when the IST date changes while the tile is open.
  }, [api, identity, profile, serverCheckinDate, today]);

  // ---- covert SOS: triple tap on the date ----
  // Permission was asked during onboarding; here we only keep a background watch so the SOS can
  // go out at once with the last known fix. Nothing on screen changes except a 200 ms flicker.
  // Never prompt from the tile: only keep a watch when the browser already granted permission
  // (seeded demo parents never onboarded, and a prompt on camera would give the SOS away).
  useEffect(() => {
    if (!profile || profile.role !== 'parent') return undefined;
    let stop: (() => void) | undefined;
    let cancelled = false;
    void geoPermissionState().then((state) => {
      if (!cancelled && state === 'granted') stop = startPositionWatch();
    });
    return () => {
      cancelled = true;
      stop?.();
    };
  }, [profile]);
  const taps = useRef<number[]>([]);
  const [flick, setFlick] = useState(false);
  const sendSos = useCallback(() => {
    setFlick(true);
    window.setTimeout(() => setFlick(false), 200);
    const loc = sosLocation();
    // fire immediately; retry up to 3 times with backoff, silently
    void retryInBackground(() => api.sos(loc), 3);
  }, [api]);
  const onDateTap = () => {
    const nowMs = Date.now();
    taps.current = [...taps.current.filter((ts) => nowMs - ts <= TRIPLE_TAP_WINDOW_MS), nowMs];
    if (taps.current.length >= 3) {
      taps.current = [];
      sendSos();
    }
  };

  // ---- weather ----
  const city = profile?.city ?? '';
  const [weather, setWeather] = useState<Weather | null>(null);
  const [weatherStale, setWeatherStale] = useState(false);
  const [weatherState, setWeatherState] = useState<'loading' | 'ok' | 'fail'>('loading');
  useEffect(() => {
    if (!city) return undefined;
    let alive = true;
    fetchWeather(city)
      .then((w) => {
        if (!alive) return;
        if (w) {
          setWeather(w);
          setWeatherStale(false);
          setWeatherState('ok');
        } else setWeatherState('fail');
      })
      .catch(() => {
        if (!alive) return;
        const s = staleWeather(city);
        if (s) {
          setWeather(s);
          setWeatherStale(true);
          setWeatherState('ok');
        } else setWeatherState('fail');
      });
    return () => {
      alive = false;
    };
  }, [city]);

  // ---- medicines ----
  const meds = useMemo(() => normalizeMedicines(profile?.medicines), [profile?.medicines]);
  const medsKey = KEYS.meds(identity, today);
  const [taken, setTaken] = useState<Record<number, boolean>>(() => readJson(medsKey, {}));
  const toggleMed = (i: number) => {
    const next = { ...taken, [i]: !taken[i] };
    setTaken(next);
    writeJson(medsKey, next);
  };
  const allTaken = meds.length > 0 && meds.every((_, i) => taken[i]);

  if (loading && !profile) {
    return (
      <div className="parent-mode page">
        <Spinner label={t('loading')} />
      </div>
    );
  }
  if (error && !profile) {
    return (
      <div className="parent-mode page">
        <ErrorBox message={error} onRetry={() => void reload()} />
      </div>
    );
  }

  const wx = weather ? describeWeatherCode(weather.code) : null;

  return (
    <div className={`parent-mode ${embedded ? '' : 'page page-narrow'}`} lang="hi">
      <div className="stack" style={{ gap: 16 }}>
        {/* Date + tithi */}
        <section className="card" aria-labelledby={`${uid}-date`}>
          <div className={`tile-date ${flick ? 'flick' : ''}`} onClick={onDateTap} role="presentation">
            <p id={`${uid}-date`} className="tile-date-hi">
              {formatDateHi(now)}
            </p>
            <p className="tile-date-en" lang="en">
              {formatDateEn(now)}
            </p>
          </div>
          <div className="row tithi-line">
            <span className="tithi-moon" aria-hidden="true">
              {moonEmoji(tithi.index)}
            </span>
            <span>
              <strong>{tithi.pakshaHi}</strong>, {tithi.nameHi}
              <br />
              <span className="small muted" lang="en">
                {tithi.pakshaEn}, {tithi.nameEn} · {t('samvat')} {samvat} · {t('approx')}
              </span>
            </span>
          </div>
        </section>

        {/* Weather */}
        <section className="card" aria-labelledby={`${uid}-wx`}>
          <h2 id={`${uid}-wx`} style={{ fontSize: '1em' }} className="muted">
            <Bi k="weather" /> {city && <span>· {weather?.place ?? city}</span>}
          </h2>
          {!city && <p className="muted">{t('weatherNoCity')}</p>}
          {city && weatherState === 'loading' && !weather && <Spinner />}
          {city && weatherState === 'fail' && <p className="muted">{t('weatherOffline')}</p>}
          {weather && wx && (
            <div className="row">
              <span className="weather-icon" aria-hidden="true">
                {wx.icon}
              </span>
              <span className="weather-big">{Math.round(weather.tempC)}°C</span>
              <span>
                {wx.hi}
                <br />
                <span className="small muted" lang="en">
                  {wx.en}
                  {weatherStale ? ` (${t('weatherStale')})` : ''}
                </span>
              </span>
            </div>
          )}
          {city && (
            <p className="small muted attribution" style={{ margin: '8px 0 0' }}>
              {t('weatherCredit')}{' '}
              <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">
                Open-Meteo.com
              </a>{' '}
              (
              <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">
                CC BY 4.0
              </a>
              )
            </p>
          )}
        </section>

        {/* Medicines */}
        <section className="card" aria-labelledby={`${uid}-meds`}>
          <h2 id={`${uid}-meds`} style={{ fontSize: '1.1em' }}>
            <Bi k="medsTitle" />
          </h2>
          {meds.length === 0 && <p className="muted">{t('medsNone')}</p>}
          {meds.map((m, i) => (
            <label key={`${i}-${m.name}`} className={`check ${taken[i] ? 'done' : ''}`}>
              <input type="checkbox" checked={Boolean(taken[i])} onChange={() => toggleMed(i)} />
              <span>
                {m.time && <strong className="med-time">{m.time} · </strong>}
                {m.name}
              </span>
            </label>
          ))}
          {allTaken && (
            <p className="badge badge-ok" role="status">
              {t('medsAllDone')}
            </p>
          )}
        </section>

        {/* Photo of the day */}
        <section className="card" aria-labelledby={`${uid}-photo`}>
          <h2 id={`${uid}-photo`} style={{ fontSize: '1em' }} className="muted">
            <Bi k="photoTitle" />
          </h2>
          {profile?.photoUrl ? (
            <img className="photo" src={profile.photoUrl} alt={t('photoTitle')} />
          ) : (
            <div className="photo-placeholder">
              <span>
                <span style={{ fontSize: '2.4em' }} aria-hidden="true">
                  🪷
                </span>
                <br />
                <Bi k="photoPlaceholder" />
              </span>
            </div>
          )}
        </section>

        {/* Thought */}
        <section className="card card-soft" aria-labelledby={`${uid}-thought`}>
          <h2 id={`${uid}-thought`} style={{ fontSize: '1em' }} className="muted">
            <Bi k="thoughtTitle" />
          </h2>
          <p className="thought">“{thought.hi}”</p>
          <p className="thought-en" lang="en">
            {thought.en}
          </p>
        </section>

        {/* Madad */}
        <MadadSection guardianName={guardianName} />

        <ScreenshotCheck parentMode familyName={guardianName} familyPhone={guardian1?.phone} />

        {!embedded && (
          <p className="row" style={{ justifyContent: 'center' }}>
            <Link className="btn btn-quiet small" to="/settings">
              {t('settingsTitle')}
            </Link>
            {onSignOut && (
              <button type="button" className="btn btn-quiet small" onClick={onSignOut}>
                {t('signOut')}
              </button>
            )}
          </p>
        )}
      </div>
    </div>
  );
}

type PuchhoPhase =
  | { kind: 'idle' }
  | { kind: 'authority_loading' }
  | { kind: 'authority'; data: PuchhoAuthorityResponse; audioFailed: boolean }
  | { kind: 'family_asking' }
  | { kind: 'family_result'; result: PuchhoStatus }
  | { kind: 'family_timeout' }
  | { kind: 'error'; message: string };

function MadadSection({ guardianName }: { guardianName?: string }) {
  const api = useApi();
  const { t } = useT();
  const uid = useId();
  const [phase, setPhase] = useState<PuchhoPhase>({ kind: 'idle' });
  const audioRef = useRef<HTMLAudioElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => () => abortRef.current?.abort(), []);

  const askAuthority = async () => {
    // iOS only allows audio that starts inside a user gesture: unlock the persistent element
    // synchronously in the tap (play() on an empty src rejects, which is fine), then swap in the
    // real URL once the API answers and play again on the now-unlocked element.
    const el = audioRef.current;
    if (el) {
      el.muted = true;
      el.play().catch(() => undefined);
    }
    setPhase({ kind: 'authority_loading' });
    try {
      const data = await api.puchhoAuthority();
      setPhase({ kind: 'authority', data, audioFailed: false });
      if (el && data.audioUrl) {
        el.pause();
        el.muted = false;
        el.src = data.audioUrl;
        el.play().catch(() => setPhase((p) => (p.kind === 'authority' ? { ...p, audioFailed: true } : p)));
      }
    } catch (e) {
      setPhase({ kind: 'error', message: describeError(e, 'hi') });
    }
  };

  const askFamily = async () => {
    setPhase({ kind: 'family_asking' });
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const { taskId } = await api.puchhoFamily();
      const result = await api.pollPuchho(taskId, { signal: ctrl.signal });
      setPhase({ kind: 'family_result', result });
    } catch (e) {
      if (isAbort(e)) return;
      if (e instanceof Error && e.message === 'No answer yet') setPhase({ kind: 'family_timeout' });
      else setPhase({ kind: 'error', message: describeError(e, 'hi') });
    }
  };

  const reset = () => {
    abortRef.current?.abort();
    audioRef.current?.pause();
    setPhase({ kind: 'idle' });
  };

  // "सच है" only when the son said yes AND the code word matched. null = no code word configured
  // or none checked: say so and tell Papa to call the family himself. false or "no" = not true.
  const familyVerdict: 'true' | 'unverified' | 'false' =
    phase.kind !== 'family_result' || phase.result.outcome !== 'yes'
      ? 'false'
      : phase.result.codeWordMatched === true
        ? 'true'
        : phase.result.codeWordMatched === null
          ? 'unverified'
          : 'false';
  const familyOk = familyVerdict === 'true';

  return (
    <section className="card" aria-labelledby={`${uid}-madad`}>
      <h2 id={`${uid}-madad`} style={{ fontSize: '1.2em' }}>
        <Bi k="madad" />
      </h2>
      <p className="muted" style={{ marginTop: 0 }}>
        <Bi k="madadSub" />
      </p>

      {/* Persistent element (never remounted) so the gesture unlock above survives the fetch. */}
      <audio ref={audioRef} controls preload="auto" hidden={phase.kind !== 'authority' || !phase.data.audioUrl} style={{ width: '100%' }} />

      {phase.kind === 'idle' && (
        <div className="stack">
          <button type="button" className="btn btn-big btn-block" onClick={askAuthority}>
            <Bi k="puchhoAuthority" />
          </button>
          <button type="button" className="btn btn-big btn-block" onClick={askFamily}>
            <Bi k="puchhoFamily" />
          </button>
        </div>
      )}

      {phase.kind === 'authority_loading' && <Spinner label={t('loading')} />}

      {phase.kind === 'authority' && (
        <div className="stack" aria-live="polite">
          {phase.audioFailed && <p className="muted small">{t('puchhoAudioFail')}</p>}
          <p className="puchho-result">{phase.data.textHi}</p>
          {phase.data.textEn && (
            <p className="muted" lang="en">
              {phase.data.textEn}
            </p>
          )}
          <div className="row">
            {phase.data.audioUrl && (
              <button type="button" className="btn" onClick={() => audioRef.current?.play().catch(() => undefined)}>
                <Bi k="puchhoPlay" />
              </button>
            )}
            <button type="button" className="btn btn-quiet" onClick={reset}>
              <Bi k="close" />
            </button>
          </div>
        </div>
      )}

      {phase.kind === 'family_asking' && (
        <div className="stack" aria-live="polite">
          <p className="puchho-result">
            <Bi k="puchhoAsking" />
          </p>
          <Spinner label={t('puchhoAskingSub')} />
          <button type="button" className="btn btn-quiet" onClick={reset}>
            <Bi k="cancel" />
          </button>
        </div>
      )}

      {phase.kind === 'family_result' && (
        <div className={`card ${familyOk ? 'tone-ok' : familyVerdict === 'unverified' ? 'tone-amber' : 'tone-red'}`} role="status" aria-live="assertive">
          <p className="puchho-result">
            <Bi k={familyOk ? 'puchhoTrue' : familyVerdict === 'unverified' ? 'puchhoYesUnverified' : 'puchhoNotTrue'} />
          </p>
          {familyVerdict === 'false' && guardianName && <p className="muted small">{t('familySeeing', { name: guardianName })}</p>}
          <button type="button" className="btn mt" onClick={reset}>
            <Bi k="close" />
          </button>
        </div>
      )}

      {phase.kind === 'family_timeout' && (
        <div className="card tone-amber" role="status" aria-live="assertive">
          <p className="puchho-result">
            <Bi k="puchhoNoAnswer" />
          </p>
          <button type="button" className="btn mt" onClick={reset}>
            <Bi k="close" />
          </button>
        </div>
      )}

      {phase.kind === 'error' && (
        <div className="stack">
          <ErrorBox message={phase.message} onRetry={reset} />
        </div>
      )}
    </section>
  );
}
