# Doosri Raay — frontend

Vite + React 18 + TypeScript PWA. Two faces of one app:

- **Parent** (`/parent`): a Panchang tile — date, approximate tithi, weather, medicines (`{name, time}` rows),
  photo, a daily thought. Opening it *is* the daily check-in (`POST /checkin`, once per IST day). Nothing on this
  screen mentions scams, alerts, guardians or the ladder. Triple-tapping the date sends a covert SOS: the tile
  keeps a background `watchPosition` and posts the last known fix at once (accuracy `-1` if none), retrying up to
  three times with backoff; the only feedback is a 200 ms flicker. Location permission is asked once, during
  onboarding, never at SOS time. The "Madad" section holds the two Puchho buttons and the screenshot check.
- **Guardian** (`/guardian`): parent status (`GET /profile` polled every 5 s), open tasks (polled every 5 s)
  rendered per kind with their allowed outcomes as big buttons, recovery cases, recent checks, Web Push opt-in,
  link to Settings.
- **Settings** (`/settings`): holiday-mode toggle (parents; `POST /profile {holidayMode}`) and family photo
  upload (`POST /uploads` purpose `photo`, then `POST /profile {photoKey}`). `POST /profile` only edits the
  caller, so guardians see a note that holiday mode is switched from the parent's phone.
- **Recovery case** (`/case/new`, `/case/:id`): intake with up to 5 screenshots of ≤ 3.5 MB each (checked
  before upload), extracted transactions paired with their screenshot by `objectKey`, live reference validation
  (12-digit UPI/IMPS or 16–22 alphanumeric NEFT/RTGS with a rail label), an "Add manually" row editor when
  nothing was extracted, 1930 script, NCRP narrative, freeze letter, e-Zero FIR note and MRM checklist each with
  `Source: outlet, date` and a caveat.
- **Demo** (`/demo`): one browser, two phones (see below).
- **Judge path** (`/try`): public, no sign-up — signs in a built-in judge circle by itself and renders the split
  demo under a Judge FAQ (see below).
- **Sources verified**: a collapsible "स्रोत सत्यापन / Sources verified" card on the dashboard, the case page and
  the judge FAQ (`GET /sources`): every cited document with its SHA-256, size, fetch time and whether each
  quoted sentence was found. The e-Zero FIR / MRM / NCRP cards on a case link to the matching entry.
- **Auth**: a custom Hindi-first sign-in / sign-up / confirm-code screen (`src/auth/AuthGate.tsx`) on
  `aws-amplify/auth`; no `@aws-amplify/ui-react`. Every route is lazy-loaded and wrapped in an error boundary
  that shows "Kuch gadbad hui, dobara kholein" with a reload button instead of a blank page. A `401` from the
  API signs the user out to the auth screen with a Hindi notice; `429` reads "थोड़ा रुकें".
- **Pact gating**: a parent whose profile has no `pactAccepted: true` is sent from `/parent` to the pact step
  of onboarding; Settings shows the pact text behind "पढ़ें" and never offers a revoke.

## Run

```bash
cd frontend
npm install
cp .env.example .env.local   # fill in values from the infra outputs
npm run dev                  # http://localhost:5173
npm run build                # tsc -b && vite build → dist/
npm run lint                 # eslint
npm run preview              # serve dist/ locally (service worker + push need this or HTTPS)
```

## Deploy (Amplify Hosting)

The repo root has an `amplify.yml` (`appRoot: frontend`, `npm ci` → `npm run build`, artifacts from `dist/`,
`node_modules` cached). Connect the repo in the Amplify console, set the environment variables below on the
app, and add the SPA rewrite rule
`</^[^.]+$|\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json|webmanifest)$)([^.]+$)/>` → `/index.html`
(200). `APP_ORIGIN` on the backend must equal the deployed origin (CORS on the API and the upload bucket).
No `VITE_APP_ORIGINS` variable exists or is needed: the frontend never checks its own origin; CORS is decided
by the backend's `APP_ORIGIN`.

## Environment variables

| Name | Required | Meaning |
|---|---|---|
| `VITE_API_URL` | yes | HTTP API base URL (no trailing slash) |
| `VITE_USER_POOL_ID` | yes | Cognito user pool id |
| `VITE_USER_POOL_CLIENT_ID` | yes | Cognito app client id (no secret; for `/demo` it must allow `ALLOW_USER_PASSWORD_AUTH`) |
| `VITE_REGION` | no | default `ap-south-1` |
| `VITE_VAPID_PUBLIC_KEY` | no | VAPID public key; if absent the app calls `GET /push/public-key` |
| `VITE_DEMO_PARENT_EMAIL` | no | prefills the parent e-mail on `/demo` (never a password) |
| `VITE_JUDGE_EMAIL` | for `/try` | shared judge **guardian** e-mail (seeded by `scripts/seed.py`) |
| `VITE_JUDGE_PASSWORD` | for `/try` | its password |
| `VITE_JUDGE_PARENT_EMAIL` | for `/try` | shared judge **parent** e-mail for the left pane |
| `VITE_JUDGE_PARENT_PASSWORD` | for `/try` | its password |

The four `VITE_JUDGE_*` values are inlined into the JavaScript bundle: anyone can read them from the built
site, so they must only ever be the seeded, personal-data-free demo accounts with a rotated password, never a
personal account. Leave them empty for personal or production builds; `/try` then shows a bilingual page
explaining how to get credentials, and `/` shows the normal sign-in screen.

Without the three required values the app renders a configuration notice instead of the sign-in screen.
All of these are read at build time (Vite inlines `import.meta.env.VITE_*`), so on Amplify Hosting they must be
set as app environment variables before the build runs. There is no `VITE_APP_ORIGINS`.

## Judge path (`/try`)

Organisers' rule: a live demo must be usable without signing up. `/try` is a public route (outside the auth
gate) that:

1. signs in the judge **guardian** (`VITE_JUDGE_EMAIL` / `VITE_JUDGE_PASSWORD`) through Amplify's `signIn`,
   so the normal session, dashboard and nav work for that account (an existing judge session is kept, any
   other account is signed out first);
2. signs in the judge **parent** (`VITE_JUDGE_PARENT_EMAIL` / `VITE_JUDGE_PARENT_PASSWORD`) with the direct
   Cognito `USER_PASSWORD_AUTH` flow into the left pane, exactly like `/demo`, but without a form;
3. renders a "Judge mode: shared demo account, no personal data" banner, the **Judge FAQ** (what is on screen,
   "opening Papa's tile is the check-in — wait ~45 s for the watch to expire", "tap Reset demo first", the
   live timers from `GET /demo/config`, the quota note, the shared-circle note naming the two other judge
   circles derived from the judge e-mail — `judge2@…`, `judge3@…` — and a six-step click-through), the
   "Sources verified" panel, then the split demo.

When the judge variables are present, an unauthenticated visit to `/` lands on `/try`, and the sign-in page
carries a "Judges: open /try" link; `/signin` always shows the normal form. A `401` on the judge session
re-runs the sign-in instead of showing a form.

## Demo mode (`/demo`)

Judges sign in normally as **Priya** (guardian1) — that Amplify session drives the right pane ("Priya ka phone").
The left pane ("Papa ka phone") needs a second identity in the same browser: a small form takes Papa's e-mail and
password and calls the Cognito IDP endpoint directly (`InitiateAuth`, `USER_PASSWORD_AUTH`,
`src/lib/cognitoPasswordAuth.ts`). The returned tokens live in React state only — never localStorage — and the
ID token is injected into the API client through `ApiTokenProvider` (`src/api/context.tsx`), so everything in
the left pane calls the API as Papa while the right pane keeps Priya's session. The refresh token renews the ID
token (`REFRESH_TOKEN_AUTH`) five minutes before it expires; a `401` on the left pane brings the form back
without touching Priya's session. Reloading the page forgets Papa's tokens.

The badge at the top reads `GET /demo/config`; with `DEMO_TIMEOUTS=1` the watch deadline and ladder rungs are 45 s.
"Reset demo" calls `POST /demo/reset` as the guardian (stops running executions, closes open tasks, clears
today's check-in), then clears this browser's local state for the two identities on screen (check-in day
marker, medicine ticks, report list, pending SOS, push flag — `dr:<sub>:*`; language and weather caches stay)
and remounts both panes. The tile also trusts the server's `lastCheckinDate` over the local marker, so a reset
from another browser re-arms it on the next load. Both panes derive their element ids from `useId()`, so labels and file inputs
never collide across the two phones.

Demo flow: open `/demo`, sign in Papa on the left (the tile posts a check-in, which starts a 45 s Watch); do
nothing; after the deadline the ladder starts and "Call Papa now" appears on the right; tap "No answer" to walk the
rungs. Then use the Madad buttons on the left, the screenshot check, and "Open a case" on the right.

## Web Push

`src/sw.ts` (vite-plugin-pwa, `injectManifest`) precaches the app and handles `push` / `notificationclick`.
"Enable alerts on this phone" on the guardian dashboard requests permission, subscribes with the VAPID key and
posts the subscription to `POST /push/subscribe`. On iOS Safari (not installed) or browsers without Push the
dashboard says "Is phone par background alerts uplabdh nahi; app khula rakhein." and keeps polling in the
foreground. Service workers need HTTPS or `localhost`.

## Structure

```
src/
  api/        client.ts (fetch wrapper, typed routes, poll helpers), context.tsx (token override), types.ts
  auth/       AuthGate.tsx (custom sign-in / sign-up / confirm on aws-amplify/auth)
  lib/        panchang.ts (Meeus-style tithi), weather.ts (Open-Meteo), push.ts, storage.ts, dates.ts,
              validate.ts (reference/txn/ack rules, upload limits), geo.ts (SOS position cache), medicines.ts,
              cognitoPasswordAuth.ts (password + refresh flows), judge.ts (/try config), sources.ts, activity.ts
  hooks/      useProfile.ts (useProfile, usePoll), useDemoConfig.ts (timers), useSources.ts
  i18n/       strings.ts (every UI string, hi + en), LangContext.tsx (useT, <Bi/>)
  components/ TaskCard, VerdictCard, ScreenshotCheck, PushButton, Layout, ErrorBoundary, ui, SourcesPanel,
              JudgeFaq, ProgressBar
  pages/      Home, Onboarding, Parent, Guardian, Settings, CaseNew, CaseDetail, Demo, Try (all lazy-loaded)
  AppShell.tsx providers shared by the gated app and /try (identity, language, session)
  data/       thoughts.json (20 daily thoughts), states.ts
  sw.ts       service worker
  styles/     global.css (CSS variables, light + dark via prefers-color-scheme)
```

Bundle (`npm run build`): main chunk ≈ 371 kB (gzip ≈ 116 kB) plus per-route chunks of 0.5–19 kB and ≈ 14 kB of
CSS; the service worker precaches ≈ 481 KiB (24 entries).

## Third-party notices

- Weather on the Panchang tile comes from [Open-Meteo](https://open-meteo.com/) (CC BY 4.0); the tile shows
  "मौसम: Open-Meteo.com (CC BY 4.0)" under the weather card.
- `index.html` loads Noto Sans Devanagari from Google Fonts with `font-display: swap`; the CSS keeps the
  system font stack as fallback, so the app renders without the network (the font is not precached).

## Design rules enforced in code

- Three verdict states: `none` (grey, exact copy "Koi khatra nahi mila — phir bhi parivaar se poochhein."),
  `watching` (amber, "Dhyaan dein"), `likely` (red, "Yeh dhokha ho sakta hai"). The word "safe" appears nowhere.
- Model output (tactics, red flags, narratives) is rendered as plain text, never HTML.
- Guardians are notification-only: no screen gives them control of the parent's account.
- Parent mode: 20 px body, 52 px touch targets, Hindi first, English secondary.
- The family pact is a forced yes/no; "no" explains and waits, it never skips.
