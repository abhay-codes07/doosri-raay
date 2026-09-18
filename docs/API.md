# Doosri Raay — API contract (v1)

All routes are on one API Gateway HTTP API, behind a Cognito JWT authorizer. Every handler:

1. Reads `sub` from the JWT claims (`event.requestContext.authorizer.jwt.claims.sub`).
2. Loads `USER#<sub> / PROFILE` from DynamoDB to get `circleId` and `role`. **circleId is never taken from the request.**
3. For any item read by id, compares the item's `circleId` with the caller's; mismatch → `404 {"error":"not_found"}` (never 403, to avoid id oracles).
4. Returns JSON with `Content-Type: application/json`. Errors: `{"error": "<snake_case_code>", "message": "<human>"}`.

Rate limits: API stage throttle rate 5 rps / burst 10. LLM routes (`/analyze`, `/cases`, `/puchho`) also enforce a per-user daily quota (`DAILY_QUOTA`, default 30) → `429 {"error":"quota_exceeded"}`.

Times are ISO-8601 UTC strings. IDs are 32-char hex (uuid4).

## Onboarding

### `POST /profile`
Create or update the caller's profile.
```json
{"name":"Priya","lang":"hi","city":"Pune","state":"Maharashtra","phone":"+91...",
 "checkinHourIST":11,"holidayMode":false,
 "neighbour":{"name":"Sharma ji","phone":"+91...","address":"Flat 3B, ..."},
 "codeWord":"gulab jamun"}
```
All fields optional. `neighbour`, `checkinHourIST`, `holidayMode`, `codeWord` are meaningful on parents. Response `200 {profile}`.

### `GET /profile`
`200 {profile, circle: {circleId, members:[{sub,name,role,phone}]}}` (`circle` null if none).

### `POST /circles`
Caller becomes `guardian1` of a new circle. `200 {"circleId": "...", "inviteCode": "ABC123"}`. Invite code is 6 uppercase alphanumerics, stored on `CIRCLE#<id> / META`.

### `POST /circles/join`
```json
{"inviteCode":"ABC123","role":"parent"}
```
`role` ∈ `parent | guardian2 | son`. One parent per circle (`409 {"error":"role_taken"}`). On `parent` join, if profile has no `checkinHourIST` default 11. Starts the first `Watch` execution for the parent. `200 {circleId, role}`.

## Check-in and ladder (hero)

### `POST /checkin`
Body optional `{"source":"tile"|"sos"}` (default `tile`). Writes `CHECKIN#<YYYY-MM-DD>` (IST date), stops any running Ladder (`activeLadderArn`, sets `ladderState=ok`, closes ladder tasks), then starts the next `Watch` execution with input `{circleId, parentSub, deadline, sinceTs, startedAt, timeouts}` where `sinceTs` is this check-in's `ts` and deadline = tomorrow at `checkinHourIST` IST once today has a check-in (if `DEMO_TIMEOUTS=1`: now + 45 s). Joining a circle in demo mode does not start a Watch; the first tile open does. Idempotent per day (second call same day still refreshes `ts`, does not start another Watch if one is already running: stored `activeWatchArn` on the parent's MEMBER item is checked with `DescribeExecution`; if RUNNING, stop it and start a new one so the deadline moves forward). Only role `parent` may call; others `403`.
`200 {"date":"2026-09-18","nextDeadline":"..."}`.

### `POST /sos` (covert SOS)
```json
{"lat":18.52,"lon":73.85,"accuracy":30}
```
Parent only. Writes `CHECKIN` with `source=sos`? **No** — SOS is *not* a check-in. Writes `SOS#<ts>` item, creates a TASK of kind `sos` for each guardian ("Papa sent a silent SOS from <maps link> at <time>. Call now."), sends Web Push. Starts a `Ladder` execution immediately with `reason="sos"`. `202 {"ladderExecutionArn":"..."}`.

### `GET /tasks`
Open tasks in the caller's circle (`status=open`), newest first, max 50.
```json
{"tasks":[{"taskId":"...","kind":"guardian_call","text":"Call Papa now ...","assigneeSub":"...","assigneeName":"Priya",
           "createdAt":"...","expiresAt":"...","status":"open","context":{"rung":1,"reason":"missed_checkin"},
           "allowedOutcomes":["reached","no_answer"]}]}
```
Kinds and allowed outcomes:
| kind | allowedOutcomes | produced by |
|---|---|---|
| `guardian_call` | `reached`, `no_answer` | Ladder rung 1–2 |
| `neighbour` | `reached`, `no_answer` | Ladder rung 3 |
| `emergency` | `done` | Ladder rung 4 (no token wait; informational, auto-closes) |
| `sos` | `done` | POST /sos |
| `confirm_fields` | `confirmed` (body carries `txns`) | RecoveryCase |
| `call_1930` | `done`, `later` | RecoveryCase |
| `ncrp_filed` | `filed` (body carries `ackNo`) | RecoveryCase |
| `mrm` | `done` | RecoveryCase |
| `puchho_family` | `yes`, `no` | POST /puchho kind=family (sent to `son`) |

### `POST /tasks/{taskId}/complete`
```json
{"outcome":"no_answer"}
```
or for `confirm_fields`: `{"outcome":"confirmed","txns":[{...}]}`; for `ncrp_filed`: `{"outcome":"filed","ackNo":"32901234567890"}`.
Validates outcome ∈ allowedOutcomes, `ackNo` matches `^\d{14}$` (a `warning` is returned if it does not start with 329, the prefix reported in the press), txns pass `validate_fields` (UPI/IMPS 12 digits or NEFT/RTGS 16–22 alphanumerics; invalid rows → `400 invalid_txns` listing the rows). For `confirm_fields`/`ncrp_filed` the confirmed txns / ackNo are persisted on the CASE first. Calls `SendTaskSuccess(taskToken, output={"outcome":..., "txns":..., "ackNo":...})` first, then marks the task `done`; any other Step Functions error → `502 step_functions_error` and the task stays open. If the task has no token (informational), just closes. Idempotent: completing a `done` task returns `200` without a second SendTaskSuccess. `200 {"taskId":..., "status":"done"}`.

## Classifier (minor tool)

### `POST /uploads`
```json
{"contentType":"image/png","purpose":"analyze"|"case"}
```
Returns a presigned **POST** (not PUT) restricted to `content-length-range 0..UPLOAD_MAX_BYTES` (default 3,500,000, below Bedrock's 3.75 MB per-image limit) and `Content-Type` starts-with `image/`. Key = `circles/<circleId>/<purpose>/<uuid>.<ext>`; `purpose: "photo"` → `photos/<circleId>/<uuid>.<ext>` (the only prefix accepted as `photoKey`).
`200 {"url":"https://...", "fields":{...}, "objectKey":"..."}`.

### `POST /analyze`
```json
{"objectKey":"circles/.../x.png"}   or   {"text":"Aapka parcel customs me pakda gaya..."}
```
Creates `REPORT#<id>` with `status=pending`, invokes `classify-worker` asynchronously (`InvocationType=Event`) with `{circleId, reportId}`. `202 {"reportId":"..."}`.

### `GET /reports/{reportId}`
```json
{"reportId":"...","status":"pending"|"done"|"error",
 "verdict":{"state":"none"|"watching"|"likely","scamType":"DIGITAL_ARREST",
            "tactics":["authority","secrecy"],"redFlags":["..."],"sayHi":"...","sayEn":"..."},
 "modelId":"global.anthropic.claude-sonnet-4-6","createdAt":"..."}
```
UI copy rule: for `state=none` the card reads **"Koi khatra nahi mila — phir bhi parivaar se poochhein."** The word "safe" never appears.

## Recovery case manager (hero)

### `POST /cases`
```json
{"objectKeys":["circles/.../a.png","circles/.../b.png"],"victimName":"Ramesh Kumar","state":"Maharashtra",
 "incidentDate":"2026-09-17","narrativeHint":"CBI video call, told to transfer for verification"}
```
Creates `CASE#<id>` (`status=open`), starts `RecoveryCase` execution with `{circleId, caseId, timeouts}`. `202 {"caseId":"...","executionArn":"..."}`.

### `GET /cases/{caseId}`
```json
{"caseId":"...","status":"open"|"awaiting_confirmation"|"building"|"awaiting_1930"|"awaiting_ncrp"|"mrm"|"filed"|"error",
 "state":"Maharashtra","victimName":"...","objectKeys":[...],
 "extracted":{"txns":[{"utr":"123456789012","amount":50000,"payee":"xyz@ybl","timestamp":"2026-09-17T10:30:00+05:30","app":"PhonePe","valid":true,"issues":[]}]},
 "confirmedTxns":[...],
 "artifacts":{"script1930":"...","ncrpNarrative":"...","ncrpNarrativeLength":214,"freezeLetter":"...",
              "ezeroFir":{"state":"Maharashtra","thresholdInr":null,"note":"...","sourceUrl":"..."},
              "mrm":{"eligible":true,"firRequired":false,"checklist":["PAN","..."],"portal":"https://mrm-ncrp.mha.gov.in"}},
 "ackNo":"329...", "openTaskId":"...", "createdAt":"...","updatedAt":"..."}
```

### `GET /cases`
List the circle's cases (id, status, victimName, createdAt).

## Puchho (ask the person)

### `POST /puchho`
```json
{"kind":"authority"}      → {"audioUrl":"https://presigned.../i4c_hi.mp3","textHi":"...","textEn":"..."} (Polly, cached in S3 at audio/i4c_<lang>.mp3)
{"kind":"family"}         → creates TASK kind=puchho_family for the circle's `son` (or all guardians if no son),
                            with the code-word challenge; sends push. 202 {"taskId":"..."}
```
Both also create an informational TASK for guardians ("Papa was told X at HH:MM") so the circle knows.

### `GET /puchho/{taskId}`
Parent polls: `{"status":"open"|"done","outcome":"yes"|"no"|null,"codeWordMatched":true|false|null}`. The son's completion body may include `{"codeWord":"..."}`; server compares to parent's `codeWord` (case-insensitive, trimmed) and stores `codeWordMatched`. Parent UI: "no" or mismatch → calm Hindi message: "Yeh call sach nahi hai. Phone kaat dein. Priya ko bata diya gaya hai."

## Web Push

### `GET /push/public-key` → `{"publicKey":"<VAPID base64url>"}`
### `POST /push/subscribe` → body is the browser `PushSubscription.toJSON()`; stored on `PROFILE.pushSub`. `200`.
Push payload: `{"title":"Doosri Raay","body":"<task text>","taskId":"...","url":"/guardian"}`. Sending is best-effort; failures are logged, never raised.

## Demo

### `POST /demo/seed` — **only when `DEMO_SEED_ENABLED=1`**, caller must be in the seeded circle or the circle doesn't exist yet. Creates circle "Sharma family" with parent Papa, guardian1 Priya, guardian2 Rahul, son Aman, neighbour, and returns the circleId. Cognito users are created by `scripts/seed.py` (admin API), not by this route.

### `GET /demo/config` → `{"demoTimeouts":true|false,"rungTimeoutSeconds":45,"watchDeadlineSeconds":45}`.

### `POST /demo/reset` — guardians only; available when `DEMO_SEED_ENABLED=1` or `DEMO_TIMEOUTS=1` (else 404). Stops the parent's running Watch and Ladder executions, closes every open task in the circle, sets `ladderState=ok`, deletes today's CHECKIN so the tile can re-arm. `200 {"ok":true,"stopped":[...],"closedTasks":n,"checkinCleared":bool}`.
