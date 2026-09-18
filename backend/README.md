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
| `api/handlers/circles.py` | `POST /circles` (caller becomes guardian1, 6-char invite code), `POST /circles/join` (`parent|guardian2|son`, `409 role_taken`; parent join defaults `checkinHourIST` and starts the first Watch) |
| `api/handlers/checkin.py` | `POST /checkin` (parent only): writes `CHECKIN#<IST date>`, stops a RUNNING Watch (`DescribeExecution`/`StopExecution`) and starts a new one, stores `activeWatchArn` on the MEMBER item |
| `api/handlers/sos.py` | `POST /sos` (parent only): `SOS#<ts>` item, a `sos` task per guardian + push, starts Ladder with `reason=sos` |
| `api/handlers/tasks.py` | `GET /tasks` (open, newest first, max 50, token never returned); `POST /tasks/{id}/complete` validates outcome / `ackNo ^329\d{11}$` / `txns` (`rules.validate_fields`), persists `confirmedTxns` / `ackNo` on the CASE, then `SendTaskSuccess` exactly once (idempotent) |
| `api/handlers/uploads.py` | `POST /uploads`: presigned **POST** with `content-length-range 0..5242880` and `starts-with $Content-Type image/`; key `circles/<circleId>/<purpose>/<uuid>.<ext>` |
| `api/handlers/analyze.py` | `POST /analyze`: quota, `REPORT#<id>` pending, async `Invoke(InvocationType=Event)` of the classify worker, `202` |
| `api/handlers/reports.py` | `GET /reports/{id}` via GSI1, cross-circle `-> 404` |
| `api/handlers/cases.py` | `POST /cases` (quota, `CASE#<id>`, starts RecoveryCase with `timeouts`), `GET /cases`, `GET /cases/{id}` |
| `api/handlers/puchho.py` | `POST /puchho` `authority` (Polly neural `POLLY_VOICE_ID` hi-IN, fallback Aditi standard, cached at `audio/i4c_<lang>.mp3`, presigned GET 1 h) / `family` (task `puchho_family` to the `son`, else all guardians, code-word challenge); `GET /puchho/{taskId}` |
| `api/handlers/push.py` | `GET /push/public-key`, `POST /push/subscribe` (stored on `PROFILE.pushSub`) |
| `api/handlers/demo.py` | `POST /demo/seed` (only when `DEMO_SEED_ENABLED=1`; body `{"members":[{"sub","role","name"}]}`; creates "Sharma family" with neighbour and code word `gulab jamun`), `GET /demo/config` |
| `classify_worker/classifier.py` | `classify(text=None, image_bytes=None, image_media_type=None, model_id=None, client=None) -> verdict` (pure; used by `eval/run_eval.py`). System prompt with 8 few-shots, forced tool use, temperature 0, `max_tokens` 600; code-side validation of enums/lengths, HTML stripped, the word "safe" replaced, invalid output `-> watching / model_output_invalid` |
| `classify_worker/app.py` | `classify_worker.app.handler({circleId, reportId})`: loads the report (and the S3 image), stores `verdict` + `modelId`, status `done|error` |
| `ladder/task.py` | `ladder.task.handler`: builds Hindi + English text from `texts.py` and circle data, resolves the assignee by role (guardian2 falls back to guardian1), stores the task token when `wait` is true, pushes (all guardians for `emergency`/`sos`); `reminder`/`escalation` flags create informational tasks; recovery kinds update the CASE `status`/`openTaskId`. Returns `{"taskId"}` |
| `ladder/watch_check.py` | `{circleId, parentSub, startedAt} -> {checkedIn, holidayMode}` |
| `ladder/status.py` | `{circleId, parentSub, ladderState, closeOpenTasks}` sets `ladderState` on the MEMBER item; closes open ladder tasks as `expired` when asked (default for `ok`) |
| `recovery_agent/rules.py` | Pure rules: `validate_fields`, `lookup_ezero_threshold`, `mrm_eligibility`, `ncrp_narrative_ok`, `sanitize_narrative` |
| `recovery_agent/templates.py` | `script_1930` (en + hi), `freeze_letter`, `ncrp_template_narrative`, `mrm_checklist` |
| `recovery_agent/agent.py` | Strands `Agent` with `@tool`s (`extract_transactions`, `validate_fields`, `lookup_ezero_threshold`, `mrm_eligibility`, `draft_narrative`); `run_extract`, `run_build`, `run_mrm` fall back to a deterministic path when Strands is missing or the agent fails |
| `recovery_agent/app.py` | `recovery_agent.app.handler({action: extract|build|mrm|finalize|fail, circleId, caseId, error?})`; `mrm` returns `{eligible, firRequired, checklist}` |
| `common/config.py` | env accessors (read at call time) |
| `common/aws.py` | lazy `lru_cache`d boto3 clients (`dynamodb_resource`, `s3_client`, `sfn_client`, `lambda_client`, `polly_client`, `ssm_client`, `bedrock_client`) + `reset()` |
| `common/http.py` | `ApiError`, `ok`, `error`, `parse_body`, CORS headers from `APP_ORIGIN`, Decimal-aware JSON |
| `common/auth.py` | `get_sub`, `load_profile`, `require_circle` (circleId **only** from PROFILE), `ensure_same_circle` (404, never 403) |
| `common/db.py` | table handle, put/get/query/update helpers, `new_id`, `now_iso`, `ist_date`, `ttl_after` |
| `common/quota.py` | `consume_quota(sub, limit)` - conditional `ADD count 1`, raises `QuotaExceeded` |
| `common/timeouts.py` | `compute_timeouts(demo)`, `next_deadline_iso(checkin_hour_ist, demo)` |
| `common/tasks.py` | `create_task`, `get_task_by_id`, `list_open_tasks`, `complete_task` (conditional open -> done), `close_open_tasks` |
| `common/push.py` | `send_push(profile, payload)` best-effort pywebpush (lazy import), VAPID private key from SSM (cached); never raises |
| `common/texts.py` | every user-facing string (Devanagari + English), I4C lines, `none` copy, task templates, `contains_safe_word` guard |
| `common/bedrock.py` | `converse_structured(...)` forced tool use, untrusted-data wrapping, fallback to `FALLBACK_MODEL_ID` on throttling / not ready / access denied |

## Environment variables

`TABLE_NAME`, `UPLOAD_BUCKET`, `APP_ORIGIN`, `BEDROCK_REGION`, `MODEL_ID`, `FALLBACK_MODEL_ID`, `WATCH_SM_ARN`,
`LADDER_SM_ARN`, `RECOVERY_SM_ARN`, `CLASSIFY_FUNCTION_NAME`, `DEMO_TIMEOUTS`, `DEMO_SEED_ENABLED`, `DAILY_QUOTA`
(30), `CHECKIN_DEADLINE_HOUR_DEFAULT` (11), `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY_PARAM` (SSM name, read with
`WithDecryption=True`), `VAPID_SUBJECT`, `POLLY_VOICE_ID` (Kajal). See `docs/DATA_MODEL.md` for meanings and
`infra/template.yaml` for which Lambda gets which.

## Local tests

```
pip install -r backend/requirements.txt "moto[dynamodb,s3]" pytest
python -m pytest -q            # from the repo root; tests/ adds backend/ to sys.path
```

Tests use moto for DynamoDB/S3 and small fakes (in `tests/conftest.py`) for Step Functions, Lambda, Polly and
Bedrock. No AWS credentials or network are needed. Strands is not installed for tests; the recovery agent's
deterministic path is what runs (`agent.STRANDS_AVAILABLE` is false).

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
- `verdict.modelId` is stripped from the report's `verdict` and stored as `REPORT.modelId`.
- Frontend conveniences: `GET /profile` adds `profile.photoUrl` (presigned GET, 1 h, when `photoKey` is set) and,
  on the parent member, `ladderState`, `lastCheckin`, `lastCheckinDate`, `watchDeadline`; `POST /profile` also
  accepts `pactAccepted` (bool). TASK `context` carries `rung`, `reason`, `since` (ISO), `caseId`, `neighbour` +
  `script`/`scriptHi` (neighbour rung), `mapsUrl`/`lat`/`lon`/`accuracy` (sos), `checklist` (mrm), `escalation`,
  `reminderFor`. `POST /sos` with `accuracy < 0` means "no location" (no maps link in the task text).
