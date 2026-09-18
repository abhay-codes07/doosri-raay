import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useApi } from '../api/context';
import { describeError } from '../api/client';
import { Spinner } from '../components/ui';
import { INDIAN_STATES } from '../data/states';
import { useT } from '../i18n/LangContext';
import { istDateString } from '../lib/dates';
import { savePreview } from '../lib/storage';
import { MAX_UPLOAD_BYTES, fileToPreview, isImageFile } from '../lib/validate';
import { useSession } from '../session';

interface Picked {
  file: File;
  preview: string;
}

export function CaseNewPage() {
  const api = useApi();
  const navigate = useNavigate();
  const session = useSession();
  const { t, lang } = useT();
  const [victimName, setVictimName] = useState(session.parent?.name ?? '');
  const [stateName, setStateName] = useState(session.profile?.state ?? '');
  const [incidentDate, setIncidentDate] = useState(istDateString());
  const [hint, setHint] = useState('');
  const [picked, setPicked] = useState<Picked[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const addFiles = async (files: FileList | null) => {
    if (!files) return;
    setError(null);
    const next: Picked[] = [];
    for (const f of Array.from(files)) {
      if (!isImageFile(f)) {
        setError(t('notImage'));
        continue;
      }
      if (f.size > MAX_UPLOAD_BYTES) {
        setError(t('tooLarge'));
        continue;
      }
      let preview: string;
      try {
        preview = await fileToPreview(f);
      } catch {
        preview = '';
      }
      next.push({ file: f, preview });
    }
    setPicked((cur) => [...cur, ...next].slice(0, 8));
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!victimName.trim()) {
      setError(t('needName'));
      return;
    }
    if (!stateName) {
      setError(t('needState'));
      return;
    }
    if (picked.length === 0) {
      setError(t('needImages'));
      return;
    }
    setBusy(true);
    try {
      const objectKeys: string[] = [];
      for (let i = 0; i < picked.length; i += 1) {
        setProgress(`${t('uploading')} ${i + 1}/${picked.length}`);
        const key = await api.uploadFile(picked[i].file, 'case');
        if (picked[i].preview) savePreview(key, picked[i].preview);
        objectKeys.push(key);
      }
      setProgress(t('creating'));
      const r = await api.createCase({
        objectKeys,
        victimName: victimName.trim(),
        state: stateName,
        incidentDate,
        narrativeHint: hint.trim() || undefined,
      });
      navigate(`/case/${r.caseId}`, { replace: true });
    } catch (err) {
      setError(describeError(err, lang));
      setBusy(false);
      setProgress(null);
    }
  };

  return (
    <div className="page-narrow" style={{ margin: '0 auto' }}>
      <p>
        <Link to="/guardian">← {t('back')}</Link>
      </p>
      <h1 style={{ fontSize: '1.5em', marginBottom: 4 }}>{t('caseNewTitle')}</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        {t('caseNewSub')}
      </p>
      <form className="card" onSubmit={submit}>
        <div className="field">
          <label htmlFor="victim">{t('victimName')}</label>
          <input id="victim" value={victimName} onChange={(e) => setVictimName(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="cstate">{t('stateLabel')}</label>
          <select id="cstate" value={stateName} onChange={(e) => setStateName(e.target.value)} required>
            <option value="">—</option>
            {INDIAN_STATES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="idate">{t('incidentDate')}</label>
          <input id="idate" type="date" value={incidentDate} max={istDateString()} onChange={(e) => setIncidentDate(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="hint">
            {t('hint')} <span className="muted small">({t('optional')})</span>
          </label>
          <textarea id="hint" value={hint} onChange={(e) => setHint(e.target.value)} placeholder={t('hintPlaceholder')} maxLength={1000} />
        </div>
        <div className="field">
          <label htmlFor="shots">{t('screenshots')}</label>
          <input id="shots" type="file" accept="image/*" multiple disabled={busy} onChange={(e) => void addFiles(e.target.files)} />
          <span className="help">{t('addImages')} · ≤ 5 MB</span>
        </div>
        {picked.length > 0 && (
          <div className="thumb-grid" style={{ marginBottom: 14 }}>
            {picked.map((p, i) => (
              <figure key={`${p.file.name}-${i}`}>
                {p.preview ? <img src={p.preview} alt={p.file.name} /> : <div className="placeholder">{p.file.name}</div>}
                <button
                  type="button"
                  className="btn btn-quiet small"
                  disabled={busy}
                  onClick={() => setPicked((cur) => cur.filter((_, j) => j !== i))}
                  aria-label={`${t('remove')} ${p.file.name}`}
                >
                  {t('remove')}
                </button>
              </figure>
            ))}
          </div>
        )}
        {error && (
          <p className="alert alert-error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="btn btn-primary btn-big btn-block" disabled={busy}>
          {busy ? <Spinner label={progress ?? t('creating')} /> : t('createCase')}
        </button>
      </form>
    </div>
  );
}
