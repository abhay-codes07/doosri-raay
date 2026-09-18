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
- **Auth**: a custom Hindi-first sign-in / sign-up / confirm-code screen (`src/auth/AuthGate.tsx`) on
  `aws-amplify/auth`; no `@aws-amplify/ui-react`. Every route is lazy-loaded and wrapped in an error boundary
  that shows "Kuch gadbad hui, dobara kholein" with a reload button instead of a blank page.

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

Without the three required values the app renders a configuration notice instead of the sign-in screen.
All of these are read at build time (Vite inlines `import.meta.env.VITE_*`), so on Amplify Hosting they must be
set as app environment variables before the build runs. There is no `VITE_APP_ORIGINS`.

## Demo mode (`/demo`)

Judges sign in normally as **Priya** (guardian1) — that Amplify session drives the right pane ("Priya ka phone").
The left pane ("Papa ka phone") needs a second identity in the same browser: a small form takes Papa's e-mail and
password and calls the Cognito IDP endpoint directly (`InitiateAuth`, `USER_PASSWORD_AUTH`,
`src/lib/cognitoPasswordAuth.ts`). The returned ID token lives in React state only — never localStorage — and is
injected into the API client through `ApiTokenProvider` (`src/api/context.tsx`), so everything in the left pane
calls the API as Papa while the right pane keeps Priya's session. Reloading the page forgets Papa's token.

The badge at the top reads `GET /demo/config`; with `DEMO_TIMEOUTS=1` the watch deadline and ladder rungs are 45 s.
"Reset demo" calls `POST /demo/reset` as the guardian (stops running executions, closes open tasks, clears
today's check-in), then clears this browser's local state (check-in day marker, medicine ticks, report list,
previews) and remounts both panes. Both panes derive their element ids from `useId()`, so labels and file inputs
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
              validate.ts (reference/ack rules, upload limits), geo.ts (SOS position cache), medicines.ts,
              cognitoPasswordAuth.ts
  i18n/       strings.ts (every UI string, hi + en), LangContext.tsx (useT, <Bi/>)
  components/ TaskCard, VerdictCard, ScreenshotCheck, PushButton, Layout, ErrorBoundary, ui
  pages/      Home, Onboarding, Parent, Guardian, Settings, CaseNew, CaseDetail, Demo (all lazy-loaded)
  data/       thoughts.json (20 daily thoughts), states.ts
  sw.ts       service worker
  styles/     global.css (CSS variables, light + dark via prefers-color-scheme)
```

Bundle (`npm run build`): main chunk ≈ 357 kB (gzip ≈ 112 kB) plus per-route chunks of 0.5–18 kB and ≈ 11 kB of
CSS; the service worker precaches ≈ 445 KiB.

## Design rules enforced in code

- Three verdict states: `none` (grey, exact copy "Koi khatra nahi mila — phir bhi parivaar se poochhein."),
  `watching` (amber, "Dhyaan dein"), `likely` (red, "Yeh dhokha ho sakta hai"). The word "safe" appears nowhere.
- Model output (tactics, red flags, narratives) is rendered as plain text, never HTML.
- Guardians are notification-only: no screen gives them control of the parent's account.
- Parent mode: 20 px body, 52 px touch targets, Hindi first, English secondary.
- The family pact is a forced yes/no; "no" explains and waits, it never skips.
