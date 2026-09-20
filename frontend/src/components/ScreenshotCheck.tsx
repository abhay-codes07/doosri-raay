import { useEffect, useId, useRef, useState } from 'react';
import { useApi, useApiIdentity } from '../api/context';
import { describeError, isAbort } from '../api/client';
import type { Report } from '../api/types';
import { Bi, useT } from '../i18n/LangContext';
import { rememberReport, savePreview } from '../lib/storage';
import { ACCEPT_IMAGES, MAX_UPLOAD_BYTES, MAX_UPLOAD_LABEL, fileToPreview, formatBytes, isImageFile } from '../lib/validate';
import { VerdictCard } from './VerdictCard';
import { Spinner } from './ui';

type Phase = 'idle' | 'uploading' | 'checking' | 'done' | 'error';

/**
 * Minor tool: screenshot or pasted text → POST /uploads → POST /analyze → poll → three-state verdict.
 * Rendered in parent mode (Hindi first) or compact guardian mode.
 */
export function ScreenshotCheck({
  parentMode = false,
  familyName,
  familyPhone,
}: {
  parentMode?: boolean;
  /** Family member offered as a tel: link under the verdict. */
  familyName?: string;
  familyPhone?: string;
}) {
  const api = useApi();
  const identity = useApiIdentity();
  const { t, lang } = useT();
  const uid = useId();
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const reset = () => {
    abortRef.current?.abort();
    setFile(null);
    setText('');
    setPhase('idle');
    setError(null);
    setReport(null);
    if (fileInput.current) fileInput.current.value = '';
  };

  const onFile = (f: File | null) => {
    setError(null);
    if (!f) {
      setFile(null);
      return;
    }
    if (!isImageFile(f)) {
      setError(t('notImage'));
      return;
    }
    if (f.size > MAX_UPLOAD_BYTES) {
      setError(`${f.name} (${formatBytes(f.size)}): ${t('tooLarge', { max: MAX_UPLOAD_LABEL })}`);
      return;
    }
    setFile(f);
  };

  const run = async () => {
    setError(null);
    setReport(null);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      let reportId: string;
      let label: string;
      if (file) {
        setPhase('uploading');
        const objectKey = await api.uploadFile(file, 'analyze');
        try {
          savePreview(objectKey, await fileToPreview(file, 320));
        } catch {
          /* preview optional */
        }
        setPhase('checking');
        reportId = (await api.analyze({ objectKey })).reportId;
        label = file.name;
      } else if (text.trim()) {
        setPhase('checking');
        reportId = (await api.analyze({ text: text.trim() })).reportId;
        label = text.trim().slice(0, 60);
      } else {
        setPhase('idle');
        return;
      }
      rememberReport(identity, { reportId, createdAt: new Date().toISOString(), label });
      const r = await api.pollReport(reportId, { signal: ctrl.signal });
      if (r.status === 'error') {
        setError(r.error ?? t('error'));
        setPhase('error');
        return;
      }
      setReport(r);
      setPhase('done');
    } catch (e) {
      if (isAbort(e)) return;
      const msg = describeError(e, lang);
      setError(msg === 'Report still pending after 30 s' ? t('checkTimeout') : msg);
      setPhase('error');
    }
  };

  const busy = phase === 'uploading' || phase === 'checking';
  const canRun = !busy && (file !== null || text.trim().length > 0);

  return (
    <section className="card" aria-labelledby={`${uid}-title`}>
      <h2 id={`${uid}-title`} style={{ fontSize: parentMode ? '1.2em' : '1.05em' }}>
        {parentMode ? <Bi k="screenshotCheck" /> : t('screenshotCheck')}
      </h2>
      <p className="muted" style={{ marginTop: 0 }}>
        {parentMode ? <Bi k="screenshotCheckSub" /> : t('screenshotCheckSub')}
      </p>

      {report?.verdict && phase === 'done' ? (
        <div className="stack">
          <VerdictCard verdict={report.verdict} familyName={familyName} familyPhone={familyPhone} parentMode={parentMode} />
          <button type="button" className="btn" onClick={reset}>
            {parentMode ? <Bi k="close" /> : t('close')}
          </button>
        </div>
      ) : (
        <div className="stack">
          <div className="field">
            <label htmlFor={`${uid}-file`}>{parentMode ? <Bi k="uploadImage" /> : t('uploadImage')}</label>
            <input
              id={`${uid}-file`}
              ref={fileInput}
              type="file"
              accept={ACCEPT_IMAGES}
              disabled={busy}
              onChange={(e) => onFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="field">
            <label htmlFor={`${uid}-text`}>{parentMode ? <Bi k="pasteText" /> : t('pasteText')}</label>
            <textarea
              id={`${uid}-text`}
              value={text}
              disabled={busy || file !== null}
              onChange={(e) => setText(e.target.value)}
              maxLength={4000}
            />
          </div>
          {error && (
            <p className="alert alert-error" role="alert">
              {error}
            </p>
          )}
          <div className="row">
            <button type="button" className="btn btn-primary btn-big" disabled={!canRun} onClick={run}>
              {busy ? <Spinner label={phase === 'uploading' ? t('uploading') : t('checking')} /> : parentMode ? <Bi k="checkNow" /> : t('checkNow')}
            </button>
            {(file || text) && !busy && (
              <button type="button" className="btn btn-quiet" onClick={reset}>
                {t('cancel')}
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
