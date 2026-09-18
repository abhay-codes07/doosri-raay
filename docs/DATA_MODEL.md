# DynamoDB single table `doosriraay`

Keys: `PK` (S), `SK` (S). GSI1: `GSI1PK`/`GSI1SK` (used for `CIRCLE#<id>` open tasks by status and for user→circle lookups). TTL attribute: `ttl` (epoch seconds) on TASK, REPORT, SOS items.

| Item | PK | SK | Attributes |
|---|---|---|---|
| Profile | `USER#<sub>` | `PROFILE` | `sub, email, name, lang (hi/en), city, state, phone, role (parent/guardian1/guardian2/son), circleId, checkinHourIST, holidayMode, neighbour{name,phone,address}, codeWord, pushSub (JSON), createdAt, updatedAt` |
| Circle meta | `CIRCLE#<id>` | `META` | `circleId, name, inviteCode, createdBy, createdAt` ; `GSI1PK=INVITE#<code>`, `GSI1SK=CIRCLE#<id>` |
| Member | `CIRCLE#<id>` | `MEMBER#<sub>` | `sub, name, role, phone, joinedAt, activeWatchArn, activeLadderArn, ladderState (parent only)` |
| Check-in | `CIRCLE#<id>` | `CHECKIN#<YYYY-MM-DD>` | `ts, source (tile/sos), date` |
| SOS | `CIRCLE#<id>` | `SOS#<ts>` | `lat, lon, accuracy, ts, ladderExecutionArn, ttl` |
| Task | `CIRCLE#<id>` | `TASK#<ts>#<id>` | `taskId, kind, text, textHi, assigneeSub, assigneeName, status (open/done/expired), outcome, taskToken (never returned to clients), context (map), allowedOutcomes (list), createdAt, expiresAt, completedAt, completedBy, ttl` ; `GSI1PK=TASKID#<id>`, `GSI1SK=CIRCLE#<id>` (lookup by id) |
| Report | `CIRCLE#<id>` | `REPORT#<id>` | `reportId, status, input {objectKey|text}, verdict (map), modelId, error, createdAt, updatedAt, ttl (30 days)` ; `GSI1PK=REPORTID#<id>` |
| Case | `CIRCLE#<id>` | `CASE#<id>` | `caseId, status, victimName, state, incidentDate, narrativeHint, objectKeys, extracted, confirmedTxns, artifacts, ackNo, openTaskId, executionArn, createdAt, updatedAt` ; `GSI1PK=CASEID#<id>` |
| Quota | `QUOTA#<sub>` | `<YYYY-MM-DD>` | `count, ttl` (atomic `ADD count 1` with condition `count < DAILY_QUOTA`) |

Lookups by id (`/tasks/{id}`, `/reports/{id}`, `/cases/{id}`) go through GSI1 (`GSI1PK=TASKID#<id>` etc.), then the item's `circleId` is compared with the caller's.

## S3 bucket `UPLOAD_BUCKET`
- `circles/<circleId>/analyze/<uuid>.<ext>` and `circles/<circleId>/case/<uuid>.<ext>`: user screenshots (lifecycle expiry 7 days).
- `audio/i4c_hi.mp3`, `audio/i4c_en.mp3`: Polly output cache (no expiry).
- `photos/<circleId>/today.jpg`: family photo of the day for the Panchang tile (optional).
- Block public access on; SSE-S3; CORS allows only `APP_ORIGIN`.

## Environment variables (all Lambdas unless noted)
| Name | Meaning |
|---|---|
| `TABLE_NAME` | DynamoDB table |
| `UPLOAD_BUCKET` | S3 bucket |
| `APP_ORIGIN` | Amplify origin for CORS (e.g. `https://main.xxxx.amplifyapp.com`; `http://localhost:5173` in dev) |
| `BEDROCK_REGION` | `ap-south-1` |
| `MODEL_ID` | `global.anthropic.claude-sonnet-4-6` |
| `FALLBACK_MODEL_ID` | `global.anthropic.claude-haiku-4-5-20251001-v1:0` |
| `WATCH_SM_ARN`, `LADDER_SM_ARN`, `RECOVERY_SM_ARN` | state machines (api Lambda) |
| `CLASSIFY_FUNCTION_NAME` | for async invoke (api Lambda) |
| `DEMO_TIMEOUTS` | `1` → 45-second deadlines and rung timeouts |
| `DEMO_SEED_ENABLED` | `1` → `/demo/seed` enabled (default `0`; `/demo/reset` is enabled when this or `DEMO_TIMEOUTS` is `1`) |
| `UPLOAD_MAX_BYTES` | presigned POST cap, default `3500000` |
| `APP_ORIGINS` | comma-separated allowed origins (CORS); `APP_ORIGIN` is the first |
| `DAILY_QUOTA` | default `30` |
| `CHECKIN_DEADLINE_HOUR_DEFAULT` | default `11` (IST) |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY_PARAM`, `VAPID_SUBJECT` | Web Push; private key read from SSM SecureString at runtime |
| `POLLY_VOICE_ID` | default `Kajal` (neural, hi-IN), fallback `Aditi` |

## Timeouts (seconds)
| Name | Prod | Demo (`DEMO_TIMEOUTS=1`) |
|---|---|---|
| Watch deadline | next `checkinHourIST` IST | now + 45 |
| Ladder rung 1–3 | 900 | 45 |
| RecoveryCase ConfirmFields | 86400 | 120 |
| RecoveryCase Call1930 | 900 | 45 |
| RecoveryCase NCRPFiled | 86400 | 45 |
| RecoveryCase MRM | 604800 | 120 |

The api Lambda computes these and passes them in the execution input as `timeouts`; state machines use `TimeoutSecondsPath`.
