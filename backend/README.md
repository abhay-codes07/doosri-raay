# Doosri Raay backend

Python 3.12 Lambdas (zip: `api`, `classify-worker`, `ladder-*`; container: `recovery-agent`). One `CodeUri`
(`backend/`) is shared by every zip Lambda; the recovery agent is built from `recovery_agent/Dockerfile` with
Docker context `backend/`. Contracts: `docs/API.md`, `docs/DATA_MODEL.md`, `docs/STATE_MACHINES.md`, plus the
payload notes in `infra/README.md`.

## Modules

| Path | Handler / purpose |
|---|---|
| `api/app.py` | `api.app.handler` - router `(method, route) -> handler`; `ApiError -> JSON error`, `QuotaExceeded -> 429`, anything else `-> 500`; missing JWT claims `-> 401`; `OPTIONS -> 204` |
| `api/handlers/profile.py` | `POST/GET /profile` (allowlisted fields: name, lang, city, state, phone, checkinHourIST, holidayMode, neighbour{name,phone,address}, codeWord, medicines[{name,time}], photoKey) |
| `api/handlers/circles.py` | `POST /circles` (caller becomes guardian1, 6-char invite code), `POST /circles/join` (`parent|guardian2|son`, `409 role_taken`, `409 already_in_circle` when the caller is in any circle; an existing MEMBER item is never overwritten). Parent join defaults `checkinHourIST`; in prod it starts the first Watch with `sinceTs` = join time, with `DEMO_TIMEOUTS=1` nothing starts until the first tile open |
| `api/handlers/checkin.py` | `POST /checkin` (parent only): writes `CHECKIN#<IST date>`, stops the running Ladder (`activeLadderArn` on the MEMBER item, errors ignored; closes open ladder tasks, `ladderState=ok`), stops a RUNNING Watch and starts a new one with `sinceTs` = the check-in `ts` (watch-check only counts check-ins strictly after it) and deadline = **tomorrow's** `checkinHourIST` IST once today has a check-in (demo: now + 45 s); stores `activeWatchArn`, `watchDeadline`, `watchSinceTs`. Response adds `ladderStopped`. Also exports `stop_active_ladder` / `stop_execution_quietly` |
| `api/handlers/sos.py` | `POST /sos` (parent only): `SOS#<ts>` item, a `sos` task per guardian, stops any running Ladder, starts the new Ladder with `reason=sos`, stores `activeLadderArn` on the MEMBER item, and only then pushes (best effort, never fails the handler) |
| `api/handlers/tasks.py` | `GET /tasks` (open, newest first, max 50, token never returned; the parent role never sees the covert kinds `sos`/`guardian_call`/`neighbour`/`emergency`, Cedar `covert-hidden-from-parent`); `POST /tasks/{id}/complete` validates outcome / `ackNo ^\d{14}$` (a number not starting with 329 is accepted with `warning` in the response) / `txns` (`rules.validate_fields`; any invalid row -> 400 listing `Row n: issue`), then writes `confirmedTxns` / `ackNo` on the CASE (idempotent SET, so `Build` never reads an empty case), then `SendTaskSuccess`, then the conditional open->done update. `TaskTimedOut` -> the task closes as `expired` and the caller gets `409 task_expired`; `TaskDoesNotExist`/`InvalidToken` still mark done; any other Step Functions error -> 502 and the task stays open. Who may complete what comes from `common/authz/policies.cedar` (403 carries `reason` + `messageHi`). Idempotent. Creating a token task expires earlier open tasks of the same kind for the same case/parent |
| `api/handlers/uploads.py` | `POST /uploads`: presigned **POST** (regional virtual-hosted SigV4 URL; path-style on the LocalStack endpoint) with `content-length-range 0..UPLOAD_MAX_BYTES` (3,500,000: Bedrock caps images at 3.75 MB) and `starts-with $Content-Type image/`; key `circles/<circleId>/<purpose>/<uuid>.<ext>`, or `photos/<circleId>/<uuid>.<ext>` for `purpose=photo`; 60 per user per day (`QUOTA#<sub>` / `<date>#uploads`) |
| `api/handlers/analyze.py` | `POST /analyze`: quota, `REPORT#<id>` pending, async `Invoke(InvocationType=Event)` of the classify worker, `202` |
| `api/handlers/reports.py` | `GET /reports/{id}` via GSI1, cross-circle `-> 404`; `errorDetail` only when `DEMO_TIMEOUTS=1` |
| `api/handlers/cases.py` | `POST /cases` (quota weighted by the number of screenshots, `CASE#<id>`, starts RecoveryCase with `timeouts`), `GET /cases`, `GET /cases/{id}` (never return `executionArn`; expose `agentPath`) |
| `api/handlers/sources.py` | `GET /sources` (any circle member): the verified-sources manifest from S3 `sources/manifest.json`, else the bundled `common/sources_manifest.json` written by `scripts/verify_sources.py` |
| `api/handlers/puchho.py` | `POST /puchho` `authority` (quota; Polly neural `POLLY_VOICE_ID` hi-IN, fallback Aditi standard, cached at `audio/i4c_<lang>.mp3`, presigned GET 1 h) / `family` (no quota; task `puchho_family` to the `son`, else all guardians, code-word challenge; `codeWordMatched` is `null` when the parent has no code word); `GET /puchho/{taskId}` |
| `api/handlers/push.py` | `GET /push/public-key`, `POST /push/subscribe` (stored on `PROFILE.pushSub`) |
| `api/handlers/demo.py` | `POST /demo/seed` (only when `DEMO_SEED_ENABLED=1`; body `{"members":[{"sub","role","name"}]}`; creates "Sharma family" with neighbour "Verma ji" and code word `gulab jamun`; the caller must be one of the members AND, when the members already have a circle, already be in it (`403`); a profile that already has a circle is never upserted; `409 member_in_other_circle` if members belong to different circles; MEMBER items are never overwritten; a Watch starts only in prod mode). `POST /demo/reset` (guardians, Cedar `guardian-resets-demo`; demo stacks only): stops the parent's Watch and Ladder executions (SOS included), closes every open task, `ladderState=ok`, deletes today's CHECKIN -> `{ok:true}`. `GET /demo/config` -> `{demoTimeouts, rungTimeoutSeconds, watchDeadlineSeconds, confirmTimeoutSeconds, call1930TimeoutSeconds, ncrpTimeoutSeconds, mrmTimeoutSeconds, timeouts:{rung,confirm,call1930,ncrp,mrm,watch}, demoSeedEnabled, resetEnabled}` |
| `classify_worker/classifier.py` | `classify(text=None, image_bytes=None, image_media_type=None, model_id=None, client=None) -> verdict` (pure; used by `eval/run_eval.py`). System prompt with 16 few-shots taken from `patterns.json` (12 Indian pretexts + 2 benign + 1 softened + 1 `watching`), forced tool use, temperature 0, `max_tokens` 1024; code-side validation of enums/lengths, HTML stripped, the word "safe" replaced, invalid output `-> watching / model_output_invalid`. The verdict also carries `patternId`, `patternLabel` (en+hi), `patternRedFlags` and `explanations[]` (each an official quote with `source {outlet,date,url}`: the I4C advisory line for the matched pretext, "speak to your relatives", "report on 1930") from `lookup_patterns()` |
| `classify_worker/patterns.json` | The scam-pattern catalogue (rules as data): per pretext `id, scamType, label{en,hi}, tactics, redFlags, advisory{quote, source, caveat}, example`. Every quote is checked against the live source by `scripts/verify_sources.py` |
| `classify_worker/app.py` | `classify_worker.app.handler({circleId, reportId})`: loads the report (and the S3 image; objects over `UPLOAD_MAX_BYTES` are refused before Bedrock; `NoSuchKey` AND `AccessDenied`/403 on GetObject both mean `image_missing`, the worker has no `s3:ListBucket`), stores `verdict` + `modelId`, status `done|error`; never leaves `pending`: `error` is a short code (`image_too_large`, `image_missing`, `model_unavailable`, `report_not_found`, `internal`) with `errorDetail` |
| `ladder/task.py` | `ladder.task.handler`: builds Hindi + English text from `texts.py` and circle data, resolves the assignee by role (guardian2 falls back to guardian1), stores the task token when `wait` is true, `expiresAt` from the payload `timeouts`, pushes last (all guardians for `emergency`/`sos`); `executionArn` (`$$.Execution.Id`) on a ladder rung is stored as `activeLadderArn` + `activeLadderReason` on the parent's MEMBER item so `/checkin` and `/demo/reset` can stop it. **Rung 1 of a `missed_checkin` ladder first re-checks for a CHECKIN with `ts > member.watchSinceTs`; if found it answers its own token with `{"outcome":"reached"}` and creates no task** (`{"taskId": null, "resolved": true}`). The `emergency` rung never raises (`{"taskId": null, "error"}`). `reminder`/`escalation` flags create informational tasks; recovery kinds update the CASE `status`/`openTaskId`. Returns `{"taskId"}` |
| `ladder/watch_check.py` | `{circleId, parentSub, sinceTs (fallback startedAt), executionArn?} -> {checkedIn, holidayMode, superseded}`; a check-in counts only when `ts > sinceTs`; when `executionArn` differs from the parent's `activeWatchArn` the Watch was superseded and reports `checkedIn: true` (no Ladder) |
| `ladder/status.py` | `{circleId, parentSub, ladderState, closeOpenTasks}` sets `ladderState` on the MEMBER item (`ok` also clears `activeLadderArn`/`activeLadderReason`); closes open ladder tasks as `expired` when asked (default for `ok`) |
| `recovery_agent/rules_data.json` | **Rules as data.** Every legal/operational fact: e-Zero FIR thresholds per state (`operator`/`value`), the SC direction, MRM `noFirUpTo`/`firMandatoryAbove`/`ackRequired`, NCRP form rules and the 14-digit `329…` acknowledgement note. Each entry: `label {en,hi}`, `source {outlet,date,url}`, `quote` (the sentence as reported, verified by `scripts/verify_sources.py`), `caveat`. Nothing legal is hard-coded in Python (a test greps for it) |
| `recovery_agent/rules.py` | Loads `rules_data.json` at import and evaluates from it (`evaluate(entry, amount)`, `rule_entries()`); pure rules: `validate_fields` (three rails: UPI/IMPS `^\d{12}$`, NEFT/RTGS `^[A-Z0-9]{16,22}$` upper-cased, else `unknown`; every row gets `rail`; string fields capped at 200 chars; NaN/inf amounts are `amount_not_numeric`), `describe_issues`, `validate_ack`, `lookup_ezero_threshold(state, amount=None)` (`applies` when an amount is given), `mrm_eligibility`, `ncrp_facts` (each with `label`, `quote`, `source`, `caveat` and a `citations` block), `narrative_consistent`, `ncrp_narrative_ok`, `sanitize_narrative` |
| `recovery_agent/templates.py` | `script_1930` (en + hi), `freeze_letter`, `ncrp_template_narrative`, `mrm_checklist` |
| `recovery_agent/agent.py` | Strands `Agent` with `@tool`s (`extract_transactions`, `validate_fields`, `lookup_ezero_threshold`, `mrm_eligibility`, `draft_narrative`); `run_extract`, `run_build`, `run_mrm` fall back to a deterministic path when Strands is missing or the agent fails, and the CASE records `agentPath: strands|fallback`, `agentError`, `agentToolCalls`. Constraints: `extract_transactions` only reads keys in `case.objectKeys` (anything else returns `object_key_not_in_case`, no S3 call); `victimName`/`narrativeHint` are wrapped as `<untrusted_data>` in every prompt; a tool-call budget of 12 (`ToolBudgetExceeded`) and a sliding-window conversation manager bound the loop (Strands has no `max_iterations`). `run_build`/`run_mrm` use only `confirmedTxns` stored on the CASE (never the model's extraction); a model narrative with a foreign UTR/amount is replaced by the template. Artifacts carry `ezeroFir.source`, `mrm.source`, `ncrp.source` |
| `recovery_agent/app.py` | `recovery_agent.app.handler({action: extract|build|mrm|finalize|fail, circleId, caseId, error?})`; `mrm` returns `{eligible, firRequired, checklist}` |
| `common/config.py` | env accessors (read at call time), incl. `endpoint_url()` / `endpoint_url_for(service)`, `local_stub_sfn()`, `sam_local()`, `xray_enabled()` |
| `common/aws.py` | lazy `lru_cache`d boto3 clients (`dynamodb_resource`, `s3_client` with `signature_version=s3v4` + virtual addressing in `AWS_REGION`/`BEDROCK_REGION`/`ap-south-1`, `sfn_client`, `lambda_client`, `polly_client`, `ssm_client`, `bedrock_client` with `connect_timeout=5, read_timeout=45, retries max_attempts=1`) + `reset()`. `AWS_ENDPOINT_URL` (or `AWS_ENDPOINT_URL_S3` / `_DYNAMODB` / ...) redirects every client and switches S3 to path-style; `LOCAL_STUB_SFN=1` swaps the Step Functions client for `StubSfn` (fake ARNs, no AWS); `aws-xray-sdk` `patch_all()` runs once when `AWS_XRAY_DAEMON_ADDRESS` is set |
| `common/authz/` | **Authorization as policy.** `policies.cedar` (principal `Member{sub, role, circleId}`, actions `ViewCase, ViewReport, ViewTasks, CompleteTask, ResetDemo, ViewSources, UpdateParentSettings`, resources with `circleId, assigneeSub, kind, covert, status, ownerSub, ownerRole`): same-circle view; guardians complete any circle task, the son only his own; `@id("covert-hidden-from-parent")`, `@id("guardian-notification-only")`, `@id("cross-circle")`, `@id("task-not-open")` forbids. `is_authorized(principal, action, resource, context) -> (allowed, reason_id)` runs on `cedarpy` (Rust Cedar; py3.10-3.14 manylinux/win wheels) and falls back to a minimal evaluator of the same file if the wheel is missing (`ENGINE` says which); `require()` raises 403 with the `@id` and a bilingual message. Handlers still answer 404 for cross-circle ids first |
| `common/sources.py` | The official sources we cite (`OFFICIAL_SOURCES`) and `load_manifest()` (S3 `sources/manifest.json`, else the bundled `sources_manifest.json`) for `GET /sources` |
| `common/http.py` | `ApiError`, `ok`, `error`, `parse_body`, CORS headers from `APP_ORIGIN`, Decimal-aware JSON |
| `common/auth.py` | `get_sub`, `load_profile`, `require_circle` (circleId **only** from PROFILE), `ensure_same_circle` (404, never 403) |
| `common/db.py` | table handle, put/get/query/update helpers, `new_id`, `now_iso`, `ist_date`, `ttl_after` |
| `common/quota.py` | `consume_quota(sub, limit, weight=1, bucket=None)` - conditional `ADD count :weight` on `QUOTA#<sub>` / `<date>[#bucket]`, raises `QuotaExceeded`; buckets `uploads` (60/day) and `sos` (10/day) are separate from the model quota |
| `common/timeouts.py` | `compute_timeouts(demo)`, `next_deadline_iso(checkin_hour_ist, demo)` |
| `common/tasks.py` | `create_task`, `get_task_by_id`, `list_open_tasks`, `complete_task` (conditional open -> done), `close_open_tasks` |
| `common/push.py` | `send_push(profile, payload)` best-effort pywebpush (lazy import, `timeout=5`), `push_for_tasks`, VAPID private key from SSM (cached); never raises; handlers call it after every DynamoDB write / Step Functions call |
| `common/texts.py` | every user-facing string (Devanagari + English), I4C lines, `none` copy, task templates, `contains_safe_word` guard |
| `common/bedrock.py` | `converse_structured(...)` forced tool use, untrusted-data wrapping, fallback to `FALLBACK_MODEL_ID` on ANY botocore `ClientError` (wrong model id, throttling, access denied, not ready…) and on read timeouts / endpoint connection errors, EXCEPT a `ValidationException` about our own input (image too large / wrong format / input too long: `is_input_validation_error`), which fails on every model and is raised at once; logs which model answered; `error_code(exc)` |

## Environment variables

`TABLE_NAME`, `UPLOAD_BUCKET`, `APP_ORIGIN`, `BEDROCK_REGION`, `MODEL_ID`, `FALLBACK_MODEL_ID`, `WATCH_SM_ARN`,
`LADDER_SM_ARN`, `RECOVERY_SM_ARN`, `CLASSIFY_FUNCTION_NAME`, `DEMO_TIMEOUTS`, `DEMO_SEED_ENABLED`, `DAILY_QUOTA`
(30), `CHECKIN_DEADLINE_HOUR_DEFAULT` (11), `UPLOAD_MAX_BYTES` (3500000), `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY_PARAM` (SSM name, read with
`WithDecryption=True`), `VAPID_SUBJECT`, `POLLY_VOICE_ID` (Kajal). `POST /demo/reset` exists when `DEMO_SEED_ENABLED=1` or `DEMO_TIMEOUTS=1`. See `docs/DATA_MODEL.md` for meanings and
`infra/template.yaml` for which Lambda gets which.

Local mode only (never set in the cloud; empty = off): `AWS_ENDPOINT_URL` (LocalStack; also `AWS_ENDPOINT_URL_S3` /
`AWS_ENDPOINT_URL_DYNAMODB` per service), `LOCAL_STUB_SFN` (ApiFunction: fake Step Functions ARNs, no timers),
`AWS_SAM_LOCAL` (set by `sam local`: `get_sub` reads `sub`/`email` from the UNVERIFIED bearer token, or the
`x-dev-sub` header, because sam local does not run the JWT authorizer). Observability: `AWS_XRAY_DAEMON_ADDRESS`
(set by Lambda when tracing is on) turns on `aws-xray-sdk` `patch_all()`.

Demo timeouts (`DEMO_TIMEOUTS=1`): rung 45 s, Watch 45 s, confirm 900 s, call1930 90 s, ncrp 120 s, mrm 120 s
(`GET /demo/config` returns them all).

## Local tests

```
pip install -r backend/requirements.txt "moto[dynamodb,s3]" pytest
python -m pytest -q            # from the repo root; tests/ adds backend/ to sys.path
```

Tests use moto for DynamoDB/S3 and small fakes (in `tests/conftest.py`) for Step Functions, Lambda, Polly and
Bedrock. No AWS credentials or network are needed. With Strands installed the agent is constructed and fails on
moto's Bedrock, so the deterministic path is what runs either way (the CASE records `agentPath: fallback` and
the reason). `cedarpy` is optional for tests: without it the authz fallback evaluator runs the same policy table.

## Whole stack locally (LocalStack + sam local)

`infra/README.md` "Run it locally" has the full recipe (`make local-up`, `make local-bootstrap`, `make local-api`).
The backend side:

- `scripts/localstack_bootstrap.py` reads only the environment (`AWS_ENDPOINT_URL` default
  `http://localhost:4566`, `TABLE_NAME`, `UPLOAD_BUCKET`, `AWS_DEFAULT_REGION`) and creates the table (PK/SK, GSI1
  with projection ALL, TTL on `ttl`) and the bucket (with CORS for the Vite origins). Idempotent.
- `scripts/local_env.example` lists the host-side variables (`set -a; source scripts/local_env.example; set +a`);
  `sam local start-api` takes its per-function variables from `infra/local-env.json`.
- With `AWS_ENDPOINT_URL` set the S3 client is path-style, so presigned POST URLs look like
  `http://localstack:4566/doosriraay-local` (add `127.0.0.1 localstack` to your hosts file for the browser).
- `LOCAL_STUB_SFN=1`: `/checkin`, `/sos` and `/cases` record a fake execution ARN on the item and answer as usual
  (200 / 202); no rung, timer or 1930 task ever fires locally. Bedrock, Polly and Step Functions need the cloud.

## Documents you can prove

`python scripts/verify_sources.py` (needs `pypdf`; `truststore` recommended on Windows/macOS so the NIC-signed
`*.gov.in` certificates verify through the system store) downloads every official source in
`common/sources.py` plus every `source.url` cited in `recovery_agent/rules_data.json` and
`classify_worker/patterns.json`, fails closed on HTTP errors / wrong content type / a PDF without `%PDF`,
records `{url, sha256, bytes, contentType, fetchedAt, fetched, quotes[{quoteFound}]}`, checks every quote against
the fetched text (whitespace- and quote-mark-insensitive; PDFs through pypdf), prints the one-screen summary
("Verified N official sources and M rule citations") and writes `docs/sources-manifest.json` and the bundled
`common/sources_manifest.json`. `--s3` also uploads `sources/<sha256>.<ext>` and `sources/manifest.json`
(needs credentials and `UPLOAD_BUCKET`). Outlets that block scripts are kept with `fetched: false`.

## Seeding for judges

`scripts/seed.py --user-pool-id ... --client-id ... --api-url ... [--judge-circles N]` (default 3) creates the
Sharma family plus "Judge family 1..N": `judgeN@demo.doosriraay.in` (guardian1, the judge's login),
`judgeN-papa@`, `judgeN-guardian2@`, `judgeN-son@`; every parent gets `pactAccepted: true`, the code word,
neighbour "Verma ji", four medicines and `checkinHourIST` 11 (same values as `POST /demo/seed`). It prints one
table and the password once. After judging: `scripts/seed.py ... --rotate` sets a new password on every
demo/judge user.

## Container image

```
cd backend && docker build -f recovery_agent/Dockerfile -t doosriraay-recovery-agent .
```

## Notes

- Kinds `info` (guardian notice for Puchho) and `reminder` (ConfirmFields reminder) are informational extras with
  `allowedOutcomes: ["done"]` and no task token; escalation copies of `call_1930` / `ncrp_filed` for guardian2 also
  only accept `done`.
- `POST /tasks/{id}/complete`: the assignee or any guardian of the circle may complete a task; the son can only
  complete tasks assigned to him.
- Watch execution input: `{circleId, parentSub, deadline, sinceTs, startedAt, timeouts}` (`startedAt` == `sinceTs`,
  kept for the ASL's `CheckCheckin` payload). Ladder-task payloads may carry `executionArn` (`$$.Execution.Id`).
- MEMBER (parent) extras: `activeWatchArn`, `watchDeadline`, `watchSinceTs`, `activeLadderArn`, `activeLadderReason`
  (`missed_checkin` | `sos`; a check-in never stops an `sos` ladder), `ladderState`, `lastSosAt`.
- CASE extras: `agentPath` (`strands` | `fallback`), `agentError`, `agentToolCalls`; `executionArn` is stored but
  never returned by `GET /cases*`.
- `POST /profile` by a parent that turns `holidayMode` off or changes `checkinHourIST` re-arms the Watch (response
  adds `watchRearmed: true`); on demo stacks only when a Watch is already running.
- Error bodies may carry `reason` (a Cedar `@id` or `task-expired`) and `messageHi`.
- `verdict.modelId` is stripped from the report's `verdict` and stored as `REPORT.modelId`.
- Frontend conveniences: `GET /profile` adds `profile.photoUrl` (presigned GET, 1 h, when `photoKey` is set) and,
  on the parent member, `ladderState`, `lastCheckin`, `lastCheckinDate`, `watchDeadline`; `POST /profile` also
  accepts `pactAccepted` (bool). TASK `context` carries `rung`, `reason`, `since` (ISO), `caseId`, `neighbour` +
  `script`/`scriptHi` (neighbour rung), `mapsUrl`/`lat`/`lon`/`accuracy` (sos), `checklist` (mrm), `escalation`,
  `reminderFor`. `POST /sos` with `accuracy < 0` means "no location" (no maps link in the task text).
