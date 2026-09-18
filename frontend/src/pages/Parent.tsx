import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useApi, useApiIdentity } from '../api/context';
import { describeError, isAbort } from '../api/client';
import type { PuchhoAuthorityResponse, PuchhoStatus } from '../api/types';
import { ScreenshotCheck } from '../components/ScreenshotCheck';
import { ErrorBox, Spinner } from '../components/ui';
import thoughts from '../data/thoughts.json';
import { useProfile } from '../hooks/useProfile';
import { Bi, LangProvider, useT } from '../i18n/LangContext';
import { dayOfYearIST, formatDateEn, formatDateHi, istDateString } from '../lib/dates';
import { moonEmoji, tithiForIstDay, vikramSamvat } from '../lib/panchang';
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
  const { data, loading, error, reload } = useProfile(true);
  const profile = data?.profile ?? null;
  const guardianName = data?.circle?.members.find((m) => m.role === 'guardian1')?.name;

  const now = useMemo(() => new Date(), []);
  const today = istDateString(now);
  const tithi = useMemo(() => tithiForIstDay(now), [now]);
  const samvat = useMemo(() => vikramSamvat(now), [now]);
  const thought = thoughts[dayOfYearIST(now) % thoughts.length];

  // ---- silent daily check-in (once per IST day, retry on failure) ----
  useEffect(() => {
    if (!profile || profile.role !== 'parent') return undefined;
    let timer: number | undefined;
    let cancelled = false;
    const attempt = async () => {
      if (cancelled) return;
      const day = istDateString();
      if (readString(KEYS.checkinDay(identity)) === day) return;
      try {
        await api.checkin('tile');
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
  }, [api, identity, profile]);

  // ---- covert SOS: triple tap on the date ----
  const taps = useRef<number[]>([]);
  const [flick, setFlick] = useState(false);
  const sendSos = useCallback(() => {
    setFlick(true);
    window.setTimeout(() => setFlick(false), 200);
    const post = (lat: number, lon: number, accuracy: number) => {
      api.sos({ lat, lon, accuracy }).catch(() => undefined);
    };
    if (!('geolocation' in navigator)) {
      post(0, 0, -1);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => post(pos.coords.latitude, pos.coords.longitude, Math.round(pos.coords.accuracy)),
      () => post(0, 0, -1),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
    );
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
  const meds = profile?.medicines ?? [];
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
        <section className="card" aria-labelledby="date-hi">
          <div className={`tile-date ${flick ? 'flick' : ''}`} onClick={onDateTap} role="presentation">
            <p id="date-hi" className="tile-date-hi">
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
        <section className="card" aria-labelledby="wx-title">
          <h2 id="wx-title" style={{ fontSize: '1em' }} className="muted">
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
        </section>

        {/* Medicines */}
        <section className="card" aria-labelledby="meds-title">
          <h2 id="meds-title" style={{ fontSize: '1.1em' }}>
            <Bi k="medsTitle" />
          </h2>
          {meds.length === 0 && <p className="muted">{t('medsNone')}</p>}
          {meds.map((m, i) => (
            <label key={`${i}-${m}`} className={`check ${taken[i] ? 'done' : ''}`}>
              <input type="checkbox" checked={Boolean(taken[i])} onChange={() => toggleMed(i)} />
              <span>{m}</span>
            </label>
          ))}
          {allTaken && (
            <p className="badge badge-ok" role="status">
              {t('medsAllDone')}
            </p>
          )}
        </section>

        {/* Photo of the day */}
        <section className="card" aria-labelledby="photo-title">
          <h2 id="photo-title" style={{ fontSize: '1em' }} className="muted">
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
        <section className="card card-soft" aria-labelledby="thought-title">
          <h2 id="thought-title" style={{ fontSize: '1em' }} className="muted">
            <Bi k="thoughtTitle" />
          </h2>
          <p className="thought">“{thought.hi}”</p>
          <p className="thought-en" lang="en">
            {thought.en}
          </p>
        </section>

        {/* Madad */}
        <MadadSection guardianName={guardianName} />

        <ScreenshotCheck parentMode guardianName={guardianName} />

        {!embedded && onSignOut && (
          <p className="row" style={{ justifyContent: 'center' }}>
            <button type="button" className="btn btn-quiet small" onClick={onSignOut}>
              {t('signOut')}
            </button>
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
  const [phase, setPhase] = useState<PuchhoPhase>({ kind: 'idle' });
  const audioRef = useRef<HTMLAudioElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => () => abortRef.current?.abort(), []);

  const askAuthority = async () => {
    setPhase({ kind: 'authority_loading' });
    try {
      const data = await api.puchhoAuthority();
      setPhase({ kind: 'authority', data, audioFailed: false });
    } catch (e) {
      setPhase({ kind: 'error', message: describeError(e, 'hi') });
    }
  };

  useEffect(() => {
    if (phase.kind !== 'authority' || !phase.data.audioUrl) return;
    const el = audioRef.current;
    if (!el) return;
    el.play().catch(() => setPhase((p) => (p.kind === 'authority' ? { ...p, audioFailed: true } : p)));
  }, [phase]);

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
    setPhase({ kind: 'idle' });
  };

  const familyOk = phase.kind === 'family_result' && phase.result.outcome === 'yes' && phase.result.codeWordMatched !== false;

  return (
    <section className="card" aria-labelledby="madad-title">
      <h2 id="madad-title" style={{ fontSize: '1.2em' }}>
        <Bi k="madad" />
      </h2>
      <p className="muted" style={{ marginTop: 0 }}>
        <Bi k="madadSub" />
      </p>

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
          {phase.data.audioUrl && <audio ref={audioRef} src={phase.data.audioUrl} controls preload="auto" style={{ width: '100%' }} />}
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
        <div className={`card ${familyOk ? 'tone-ok' : 'tone-red'}`} role="status" aria-live="assertive">
          <p className="puchho-result">
            <Bi k={familyOk ? 'puchhoTrue' : 'puchhoNotTrue'} />
          </p>
          {!familyOk && guardianName && <p className="muted small">{t('familySeeing', { name: guardianName })}</p>}
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
