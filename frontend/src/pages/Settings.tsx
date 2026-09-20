import { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApi } from '../api/context';
import { describeError } from '../api/client';
import { Spinner } from '../components/ui';
import { Bi, useT } from '../i18n/LangContext';
import { ACCEPT_IMAGES, MAX_UPLOAD_BYTES, MAX_UPLOAD_LABEL, fileToPreview, formatBytes, isImageFile } from '../lib/validate';
import { useSession } from '../session';

/**
 * Small settings screen for the signed-in account: holiday mode (parents only; it pauses the
 * daily check-in watch) and the family photo shown on the Panchang tile. Both go through
 * POST /profile, which only ever edits the caller's own profile: a guardian cannot change the
 * parent's settings from here (guardians are notification-only).
 */
export function SettingsPage() {
  const api = useApi();
  const session = useSession();
  const { t } = useT();
  const uid = useId();
  const profile = session.profile ?? {};
  const isParent = session.isParent;

  const [holiday, setHoliday] = useState<boolean>(Boolean(profile.holidayMode));
  const [holidayBusy, setHolidayBusy] = useState(false);
  const [holidayMsg, setHolidayMsg] = useState<string | null>(null);

  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [photoBusy, setPhotoBusy] = useState<'uploading' | 'saving' | null>(null);
  const [photoMsg, setPhotoMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggleHoliday = async (next: boolean) => {
    setHoliday(next);
    setHolidayBusy(true);
    setHolidayMsg(null);
    setError(null);
    try {
      await api.updateProfile({ holidayMode: next });
      await session.reload();
      setHolidayMsg(next ? t('holidayOn') : t('holidayOff'));
    } catch (e) {
      setHoliday(!next);
      setError(describeError(e));
    } finally {
      setHolidayBusy(false);
    }
  };

  const pickPhoto = async (f: File | null) => {
    setError(null);
    setPhotoMsg(null);
    setPhotoFile(null);
    setPhotoPreview(null);
    if (!f) return;
    if (!isImageFile(f)) {
      setError(`${f.name}: ${t('notImage')}`);
      return;
    }
    if (f.size > MAX_UPLOAD_BYTES) {
      setError(`${f.name} (${formatBytes(f.size)}): ${t('tooLarge', { max: MAX_UPLOAD_LABEL })}`);
      return;
    }
    setPhotoFile(f);
    try {
      setPhotoPreview(await fileToPreview(f, 640));
    } catch {
      setPhotoPreview(null);
    }
  };

  const savePhoto = async () => {
    if (!photoFile) return;
    setError(null);
    setPhotoMsg(null);
    try {
      setPhotoBusy('uploading');
      const photoKey = await api.uploadFile(photoFile, 'photo');
      setPhotoBusy('saving');
      await api.updateProfile({ photoKey });
      await session.reload();
      setPhotoFile(null);
      setPhotoMsg(t('photoSaved'));
    } catch (e) {
      setError(describeError(e));
    } finally {
      setPhotoBusy(null);
    }
  };

  return (
    <div className="page-narrow" style={{ margin: '0 auto' }}>
      <p>
        <Link to={isParent ? '/parent' : '/guardian'}>← {t('back')}</Link>
      </p>
      <h1 style={{ fontSize: '1.5em', marginBottom: 4 }}>
        <Bi k="settingsTitle" />
      </h1>
      <p className="muted" style={{ marginTop: 0 }}>
        {profile.name ? `${profile.name} · ` : ''}
        {isParent ? t('roleParent') : t('settingsForYou')}
      </p>

      {error && (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      )}

      {/* Holiday mode */}
      <section className="card" aria-labelledby={`${uid}-holiday`}>
        <h2 id={`${uid}-holiday`}>
          <Bi k="holidayMode" />
        </h2>
        <p className="muted" style={{ marginTop: 0 }}>
          <Bi k="holidayModeHelp" />
        </p>
        {isParent ? (
          <>
            <label className="check" style={{ fontSize: '1.1em' }}>
              <input type="checkbox" checked={holiday} disabled={holidayBusy} onChange={(e) => void toggleHoliday(e.target.checked)} />
              <span>
                <Bi k={holiday ? 'holidayOnLabel' : 'holidayOffLabel'} />
              </span>
            </label>
            {holidayBusy && <Spinner label={t('saving')} />}
            {holidayMsg && (
              <p className="badge badge-ok" role="status">
                {holidayMsg}
              </p>
            )}
          </>
        ) : (
          <p className="alert" role="note">
            <Bi k="holidayParentOnly" />
          </p>
        )}
      </section>

      {/* Family photo */}
      <section className="card" aria-labelledby={`${uid}-photo`}>
        <h2 id={`${uid}-photo`}>
          <Bi k="familyPhoto" />
        </h2>
        <p className="muted" style={{ marginTop: 0 }}>
          <Bi k="familyPhotoHelp" />
        </p>
        {(photoPreview ?? profile.photoUrl) && (
          <img className="photo" src={photoPreview ?? profile.photoUrl} alt={t('familyPhoto')} style={{ marginBottom: 12 }} />
        )}
        <div className="field">
          <label htmlFor={`${uid}-file`}>{t('choosePhoto')}</label>
          <input
            id={`${uid}-file`}
            type="file"
            accept={ACCEPT_IMAGES}
            disabled={photoBusy !== null}
            onChange={(e) => void pickPhoto(e.target.files?.[0] ?? null)}
          />
          <span className="help">≤ {MAX_UPLOAD_LABEL}</span>
        </div>
        <div className="row">
          <button type="button" className="btn btn-primary btn-big" disabled={!photoFile || photoBusy !== null} onClick={() => void savePhoto()}>
            {photoBusy === 'uploading' ? <Spinner label={t('uploading')} /> : photoBusy === 'saving' ? <Spinner label={t('saving')} /> : t('savePhoto')}
          </button>
          {photoMsg && (
            <span className="badge badge-ok" role="status">
              {photoMsg}
            </span>
          )}
        </div>
      </section>

      <p>
        <Link className="btn" to="/onboarding?edit=1">
          {t('editProfile')}
        </Link>
      </p>
    </div>
  );
}
