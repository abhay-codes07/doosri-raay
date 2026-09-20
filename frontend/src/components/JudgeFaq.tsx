import { useId, useState } from 'react';
import { useDemoConfig, waitSeconds, type WaitStep } from '../hooks/useDemoConfig';
import { formatDuration } from '../lib/dates';
import { siblingJudgeEmails, type JudgeConfig } from '../lib/judge';
import { SourcesPanel } from './SourcesPanel';

const TIMER_ROWS: ReadonlyArray<{ step: WaitStep; label: string; hi: string }> = [
  { step: 'watch', label: 'Watch (check-in deadline)', hi: 'पंचांग खुलने की प्रतीक्षा' },
  { step: 'rung', label: 'Each ladder rung', hi: 'हर कदम' },
  { step: 'confirm', label: 'Confirm transactions', hi: 'लेन-देन पक्का करना' },
  { step: 'call1930', label: '1930 call', hi: '1930 कॉल' },
  { step: 'ncrp', label: 'NCRP filing', hi: 'NCRP शिकायत' },
  { step: 'mrm', label: 'MRM refund step', hi: 'MRM रिफ़ंड' },
];

/**
 * Judge FAQ for /try: what is on screen, the live timers from GET /demo/config, the shared-circle
 * and quota notes, and a six-step click-through. English first (judges), Hindi glosses where cheap.
 */
export function JudgeFaq({ cfg }: { cfg: JudgeConfig }) {
  const uid = useId();
  const [open, setOpen] = useState(true);
  const config = useDemoConfig();
  const watch = waitSeconds(config, 'watch') ?? 45;
  const siblings = siblingJudgeEmails(cfg.email);
  const d = (s: number | null) => (s === null ? '—' : formatDuration(s, 'en'));

  return (
    <section className="card judge-faq" aria-labelledby={`${uid}-title`} lang="en">
      <button type="button" className="row spread sources-toggle" aria-expanded={open} aria-controls={`${uid}-body`} onClick={() => setOpen((v) => !v)}>
        <span>
          <h2 id={`${uid}-title`} style={{ fontSize: '1.2em', margin: 0 }}>
            Judge FAQ <span className="muted small" lang="hi">· जज के लिए</span>
          </h2>
          <span className="small muted">Read once, then follow the six steps. Nothing here needs an account.</span>
        </span>
        <span aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>

      <div id={`${uid}-body`} hidden={!open} className="stack mt">
        <div className="grid grid-2">
          <div>
            <h3>What you are looking at</h3>
            <p>
              One browser, two phones. <strong>Left: Papa's phone</strong> — a Hindi Panchang tile (date, tithi, weather,
              medicines, a family photo). It never mentions scams. <strong>Right: Priya's phone</strong> — the guardian
              dashboard: parent status, open tasks, recovery cases, message check.
            </p>
            <p>
              <strong>Opening Papa's tile is the check-in.</strong> Nothing to tap: the tile posts <code>POST /checkin</code>{' '}
              silently and a {watch} s watch starts. When it lapses with no new check-in, the ladder starts and a task appears
              on Priya's phone.
            </p>
            <p>
              <strong>Tap "Reset demo" first</strong> (top right). It stops any running watch or ladder, closes open tasks and
              clears today's check-in, so the left tile re-arms when it reloads.
            </p>
          </div>
          <div>
            <h3>Live timers</h3>
            <p className="small muted">
              From <code>GET /demo/config</code>
              {config ? (config.demoTimeouts ? ' — demo timings are on.' : ' — production timings (the demo will feel slow).') : ' — loading…'}
            </p>
            <table className="timers">
              <tbody>
                {TIMER_ROWS.map((row) => (
                  <tr key={row.step}>
                    <th scope="row">
                      {row.label} <span className="muted small" lang="hi">· {row.hi}</span>
                    </th>
                    <td>{d(waitSeconds(config, row.step))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="small muted">A waiting step that lapses stops that case ("रुक गया"). The case page shows the same timers next to each step.</p>
          </div>
        </div>

        <div>
          <h3>Six-step click-through</h3>
          <ol className="steps">
            <li>
              <strong>Reset demo</strong> (top right). Wait for the green "Demo reset done".
            </li>
            <li>
              <strong>Left phone loads Papa's Panchang.</strong> That is today's check-in. Read the tile: Hindi first, big type, nothing
              alarming. Triple-tap the date to send a <em>covert SOS</em> — the only feedback is a 200 ms flicker; a map-pin task lands on
              Priya's phone within seconds.
            </li>
            <li>
              <strong>Wait about {watch} s.</strong> The watch lapses, the ladder starts, and Priya's phone shows "Call Papa now" with a
              countdown. Tap <em>No answer</em> to walk the rungs: guardian 1 → guardian 2 → neighbour script → 112 script. Tap{' '}
              <em>Reached — all fine</em> at any rung to stop it.
            </li>
            <li>
              <strong>Left: "मदद" (Help).</strong> "Someone says they are police / CBI / bank" plays the I4C advice in Hindi (Polly). "Someone
              says my son / daughter is in trouble" asks the family: the son's phone is not on screen in this demo, so after a while Papa is
              told to hang up and call the family himself — Priya sees a notice either way.
            </li>
            <li>
              <strong>Right: "Check a message".</strong> Paste a scam SMS (e.g. "Your parcel is held at customs, pay ₹2,000 to release")
              and tap Check. Three states only: no threat found / take care / this could be a scam — with tactics and red flags. The word
              "safe" never appears.
            </li>
            <li>
              <strong>Right: "Open a case".</strong> Upload one or two UPI payment screenshots, confirm the rows the model read (fix any red
              field), then read the 1930 script, NCRP narrative, freeze letter, e-Zero FIR note and MRM checklist. Each rule cites a source;
              the "Sources verified" panel below shows the backend fetched and hashed that exact document.
            </li>
          </ol>
        </div>

        <div className="grid grid-2">
          <div className="alert">
            <strong>Shared judge circle.</strong> You are signed in as <code>{cfg.email}</code> (guardian "Priya") with{' '}
            <code>{cfg.parentEmail}</code> ("Papa") on the left. Every judge on this link shares this circle: a "Reset demo" here resets it for
            everyone.
            {siblings.length > 0 && (
              <>
                {' '}
                Two other judge circles exist for parallel judging: <code>{siblings.join('</code>, <code>')}</code> — same password, given
                in the submission form; sign in with them at <code>/signin</code> and open <code>/demo</code>.
              </>
            )}
          </div>
          <div className="alert">
            <strong>Quota.</strong> The model-backed calls (message check, case extraction, Puchho) have a daily per-account quota (30 by
            default). If you see "आज की सीमा पूरी हो गई" (daily limit reached), use one of the other judge circles. Polling, tasks,
            check-ins and SOS are not metered. Demo data only — no personal data is stored here.
          </div>
        </div>

        <SourcesPanel />
      </div>
    </section>
  );
}
