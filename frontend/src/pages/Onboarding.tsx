import { useId, useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useApi } from '../api/context';
import { describeError } from '../api/client';
import type { JoinRole, Medicine, ProfileInput, Role } from '../api/types';
import { Spinner } from '../components/ui';
import { INDIAN_STATES } from '../data/states';
import { Bi, useLang, useT } from '../i18n/LangContext';
import type { Lang } from '../i18n/strings';
import { normalizeMedicines } from '../lib/medicines';
import { KEYS, writeString } from '../lib/storage';
import { useSession } from '../session';

type Step = 'circle' | 'join' | 'created' | 'profile' | 'pact' | 'done';

export function OnboardingPage() {
  const api = useApi();
  const session = useSession();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { t } = useT();
  const { setLang } = useLang();
  const editing = params.get('edit') === '1';

  const [step, setStep] = useState<Step>(session.hasCircle ? 'profile' : 'circle');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inviteCode, setInviteCode] = useState('');
  const [joinRole, setJoinRole] = useState<JoinRole>('parent');
  const [createdCode, setCreatedCode] = useState<string | null>(null);
  const [role, setRole] = useState<Role | undefined>(session.profile?.role);

  const p = session.profile ?? {};
  const [name, setName] = useState(p.name ?? '');
  const [lang, setLangField] = useState<Lang>(p.lang ?? 'hi');
  const [city, setCity] = useState(p.city ?? '');
  const [stateName, setStateName] = useState(p.state ?? '');
  const [phone, setPhone] = useState(p.phone ?? '');
  const [checkinHour, setCheckinHour] = useState<number>(p.checkinHourIST ?? 11);
  const [nName, setNName] = useState(p.neighbour?.name ?? '');
  const [nPhone, setNPhone] = useState(p.neighbour?.phone ?? '');
  const [nAddress, setNAddress] = useState(p.neighbour?.address ?? '');
  const [codeWord, setCodeWord] = useState(p.codeWord ?? '');
  const [medicines, setMedicines] = useState<Medicine[]>(() => normalizeMedicines(p.medicines));
  const [pactAnswer, setPactAnswer] = useState<'yes' | 'no' | null>(null);

  const isParent = role === 'parent';

  const createCircle = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.createCircle();
      setCreatedCode(r.inviteCode);
      setRole('guardian1');
      setStep('created');
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  };

  const join = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.joinCircle(inviteCode, joinRole);
      setRole(r.role ?? joinRole);
      setStep('profile');
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };

  const saveProfile = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const input: ProfileInput = {
      name: name.trim(),
      lang,
      city: city.trim(),
      state: stateName,
      phone: phone.trim(),
    };
    if (isParent) {
      input.checkinHourIST = checkinHour;
      input.neighbour = { name: nName.trim(), phone: nPhone.trim(), address: nAddress.trim() };
      input.codeWord = codeWord.trim();
      input.medicines = medicines
        .map((m) => ({ name: m.name.trim(), time: m.time.trim() }))
        .filter((m) => m.name.length > 0);
    }
    try {
      await api.updateProfile(input);
      setLang(lang);
      setStep(editing ? 'done' : 'pact');
      if (editing) await session.reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };

  const acceptPact = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.updateProfile({ pactAccepted: true });
      writeString(KEYS.pact(session.sub), new Date().toISOString());
      await session.reload();
      setStep('done');
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-narrow" style={{ margin: '0 auto' }}>
      <h1 style={{ fontSize: '1.6em', marginBottom: 4 }}>
        <Bi k={editing ? 'editProfile' : 'onbTitle'} />
      </h1>
      {!editing && (
        <p className="muted" style={{ marginTop: 0 }}>
          {t('onbSubtitle')}
        </p>
      )}
      {error && (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      )}

      {step === 'circle' && (
        <div className="grid grid-2">
          <section className="card">
            <h2>{t('onbCreate')}</h2>
            <p className="muted">{t('onbCreateDesc')}</p>
            <button type="button" className="btn btn-primary btn-big btn-block" disabled={busy} onClick={createCircle}>
              {busy ? <Spinner label={t('creating')} /> : t('onbCreate')}
            </button>
          </section>
          <section className="card">
            <h2>{t('onbJoin')}</h2>
            <p className="muted">{t('onbJoinDesc')}</p>
            <button type="button" className="btn btn-big btn-block" disabled={busy} onClick={() => setStep('join')}>
              {t('onbJoin')}
            </button>
          </section>
        </div>
      )}

      {step === 'join' && (
        <form className="card" onSubmit={join}>
          <div className="field">
            <label htmlFor="invite">{t('inviteCode')}</label>
            <input
              id="invite"
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6))}
              autoComplete="off"
              autoCapitalize="characters"
              required
              minLength={6}
              maxLength={6}
              aria-describedby="invite-help"
              style={{ letterSpacing: '0.2em', fontSize: '1.3em', textAlign: 'center' }}
            />
            <span id="invite-help" className="help">
              {t('inviteCodeHelp')}
            </span>
          </div>
          <fieldset className="field" style={{ border: 0, padding: 0 }}>
            <legend className="label">{t('chooseRole')}</legend>
            {(
              [
                ['parent', 'roleParent', 'roleParentDesc'],
                ['guardian2', 'roleGuardian2', 'roleGuardian2Desc'],
                ['son', 'roleSon', 'roleSonDesc'],
              ] as const
            ).map(([value, k, dk]) => (
              <label key={value} className="check">
                <input type="radio" name="role" value={value} checked={joinRole === value} onChange={() => setJoinRole(value)} />
                <span>
                  <strong>{t(k)}</strong> <span className="muted small">{t(dk)}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <div className="row">
            <button type="submit" className="btn btn-primary btn-big" disabled={busy || inviteCode.length !== 6}>
              {busy ? <Spinner label={t('joining')} /> : t('onbJoin')}
            </button>
            <button type="button" className="btn btn-quiet" onClick={() => setStep('circle')}>
              {t('back')}
            </button>
          </div>
        </form>
      )}

      {step === 'created' && (
        <section className="card tone-accent">
          <h2>{t('inviteShare')}</h2>
          <p style={{ fontSize: '2.2em', letterSpacing: '0.25em', fontWeight: 700, margin: '8px 0', textAlign: 'center' }}>
            {createdCode}
          </p>
          <button type="button" className="btn btn-primary btn-big btn-block" onClick={() => setStep('profile')}>
            {t('next')}
          </button>
        </section>
      )}

      {step === 'profile' && (
        <form className="card" onSubmit={saveProfile}>
          <h2>{t('profileTitle')}</h2>
          {role && (
            <p className="badge">
              {role === 'parent' ? t('roleParent') : role === 'guardian2' ? t('roleGuardian2') : role === 'son' ? t('roleSon') : t('roleGuardian1')}
            </p>
          )}
          <div className="field">
            <label htmlFor="name">{t('name')}</label>
            <input id="name" value={name} onChange={(e) => setName(e.target.value)} required autoComplete="name" />
          </div>
          <div className="field">
            <label htmlFor="lang">{t('langLabel')}</label>
            <select id="lang" value={lang} onChange={(e) => setLangField(e.target.value === 'en' ? 'en' : 'hi')}>
              <option value="hi">{t('hindi')}</option>
              <option value="en">{t('english')}</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="city">{t('city')}</label>
            <input id="city" value={city} onChange={(e) => setCity(e.target.value)} autoComplete="address-level2" />
          </div>
          <div className="field">
            <label htmlFor="state">{t('stateLabel')}</label>
            <select id="state" value={stateName} onChange={(e) => setStateName(e.target.value)}>
              <option value="">—</option>
              {INDIAN_STATES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="phone">{t('phone')}</label>
            <input id="phone" value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" autoComplete="tel" placeholder="+91" />
          </div>

          {isParent && (
            <>
              <div className="field">
                <label htmlFor="hour">{t('checkinHour')}</label>
                <select id="hour" value={checkinHour} onChange={(e) => setCheckinHour(Number(e.target.value))}>
                  {Array.from({ length: 24 }, (_, h) => (
                    <option key={h} value={h}>
                      {String(h).padStart(2, '0')}:00
                    </option>
                  ))}
                </select>
              </div>
              <h3 style={{ marginTop: 20 }}>{t('neighbourTitle')}</h3>
              <div className="field">
                <label htmlFor="nname">{t('neighbourName')}</label>
                <input id="nname" value={nName} onChange={(e) => setNName(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="nphone">{t('neighbourPhone')}</label>
                <input id="nphone" value={nPhone} onChange={(e) => setNPhone(e.target.value)} inputMode="tel" placeholder="+91" />
              </div>
              <div className="field">
                <label htmlFor="naddr">{t('neighbourAddress')}</label>
                <textarea id="naddr" value={nAddress} onChange={(e) => setNAddress(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="cw">{t('codeWord')}</label>
                <input id="cw" value={codeWord} onChange={(e) => setCodeWord(e.target.value)} autoComplete="off" aria-describedby="cw-help" />
                <span id="cw-help" className="help">
                  {t('codeWordHelp')}
                </span>
              </div>
              <MedicineRows value={medicines} onChange={setMedicines} />
            </>
          )}
          <button type="submit" className="btn btn-primary btn-big btn-block" disabled={busy}>
            {busy ? <Spinner label={t('saving')} /> : t('next')}
          </button>
        </form>
      )}

      {step === 'pact' && (
        <section className="card" aria-labelledby="pact-title">
          <h2 id="pact-title">
            <Bi k="pactTitle" />
          </h2>
          <blockquote className="pre" style={{ fontSize: '1.15em' }}>
            <Bi k="pactText" />
          </blockquote>
          <p style={{ fontWeight: 600 }}>
            <Bi k="pactAsk" />
          </p>
          <div className="task-actions" role="group" aria-label={t('pactAsk')}>
            <button type="button" className="btn btn-ok btn-big" disabled={busy} onClick={() => { setPactAnswer('yes'); void acceptPact(); }}>
              <Bi k="pactYes" />
            </button>
            <button type="button" className="btn btn-big" disabled={busy} onClick={() => setPactAnswer('no')}>
              <Bi k="pactNo" />
            </button>
          </div>
          {pactAnswer === 'no' && (
            <p className="alert mt" role="alert">
              <Bi k="pactNoExplain" />
            </p>
          )}
          {busy && <Spinner label={t('saving')} />}
        </section>
      )}

      {step === 'done' && (
        <section className="card tone-ok">
          <h2>
            <Bi k="onbDone" />
          </h2>
          <button
            type="button"
            className="btn btn-primary btn-big btn-block"
            onClick={() => navigate(isParent ? '/parent' : '/guardian', { replace: true })}
          >
            <Bi k="goToApp" />
          </button>
        </section>
      )}
    </div>
  );
}

/** Row editor for daily medicines: each row is {name, time} as the API stores it. */
export function MedicineRows({ value, onChange }: { value: Medicine[]; onChange: (next: Medicine[]) => void }) {
  const { t } = useT();
  const baseId = useId();
  const update = (i: number, patch: Partial<Medicine>) => onChange(value.map((m, j) => (j === i ? { ...m, ...patch } : m)));
  return (
    <fieldset className="field" style={{ border: 0, padding: 0 }}>
      <legend className="label">{t('medicines')}</legend>
      <span className="help" id={`${baseId}-help`}>
        {t('medicinesHelp')}
      </span>
      {value.map((m, i) => (
        <div key={i} className="row med-row" style={{ alignItems: 'flex-end' }}>
          <div className="field grow" style={{ marginBottom: 0 }}>
            <label htmlFor={`${baseId}-name-${i}`}>{t('medName')}</label>
            <input
              id={`${baseId}-name-${i}`}
              value={m.name}
              maxLength={100}
              onChange={(e) => update(i, { name: e.target.value })}
              aria-describedby={`${baseId}-help`}
            />
          </div>
          <div className="field" style={{ marginBottom: 0, maxWidth: 140 }}>
            <label htmlFor={`${baseId}-time-${i}`}>{t('medTime')}</label>
            <input
              id={`${baseId}-time-${i}`}
              value={m.time}
              maxLength={20}
              placeholder={t('medTimePlaceholder')}
              onChange={(e) => update(i, { time: e.target.value })}
            />
          </div>
          <button
            type="button"
            className="btn btn-quiet"
            onClick={() => onChange(value.filter((_, j) => j !== i))}
            aria-label={`${t('remove')} ${m.name || String(i + 1)}`}
          >
            {t('remove')}
          </button>
        </div>
      ))}
      <div>
        <button type="button" className="btn" disabled={value.length >= 20} onClick={() => onChange([...value, { name: '', time: '' }])}>
          + {t('addMedicine')}
        </button>
      </div>
    </fieldset>
  );
}
