# Step Functions (Standard workflows)

All three are Standard (not Express) so executions are visible and long waits are allowed. Human steps use Lambda `.waitForTaskToken` via the `ladder-task` Lambda, which writes a TASK item with the token and (best-effort) sends Web Push. Timeouts come from `$.timeouts.*` via `TimeoutSecondsPath`; on `States.Timeout` the machine moves to the next rung.

## 1. `Watch` — per-parent daily deadline
Input:
```json
{"circleId":"...","parentSub":"...","deadline":"2026-09-19T05:30:00Z","startedAt":"...","sinceTs":"2026-09-18T18:30:00Z","timeouts":{"rung":900}}
```
States:
1. `WaitForDeadline` — `Wait`, `TimestampPath: $.deadline`.
2. `CheckCheckin` — Lambda `watch-check` with Payload `{circleId, parentSub, startedAt, sinceTs, deadline}` → `{"checkedIn": true|false, "holidayMode": bool}` (checked in if a CHECKIN item with `ts > sinceTs` exists — strictly later, so the check-in that armed the watch never satisfies it — or holidayMode). `sinceTs` is the ISO timestamp the check-in window opened at (the start of the parent's day, not the moment the execution was started); `startedAt` is still passed for older executions.
3. `Choice` — checkedIn or holidayMode → `Succeed` (`AllGood`); else `StartLadder`.
4. `StartLadder` — `arn:aws:states:::states:startExecution` (async, not `.sync`) of `Ladder` with `{"AWS_STEP_FUNCTIONS_STARTED_BY_EXECUTION_ID":"$$.Execution.Id","circleId","parentSub","reason":"missed_checkin","timeouts"}` → `Succeed`. Every ladder-task Payload in `Ladder` also carries `executionArn` (`$$.Execution.Id`) so the backend can store the running ladder ARN and `StopExecution` it when the parent checks in.

## 2. `Ladder` — outsider escalation
Input: `{"circleId","parentSub","reason":"missed_checkin"|"sos","timeouts":{"rung":900}}`
States:
1. `Rung1GuardianCall` — Lambda `ladder-task` `.waitForTaskToken`, `TimeoutSecondsPath: $.timeouts.rung`. Parameters: `{"kind":"guardian_call","rung":1,"assigneeRole":"guardian1","circleId.$","parentSub.$","reason.$","taskToken.$":"$$.Task.Token"}`. Output `{"outcome":"reached"|"no_answer"}`.
   - Catch `States.Timeout` → `Rung2GuardianCall` (with `ResultPath: $.rung1`).
   - Choice `Rung1Outcome`: `reached` → `Resolved`; `no_answer` → `MarkWatching` → `Rung2GuardianCall`.
2. `MarkWatching` — Lambda `ladder-status` sets a `WATCHING` flag task (informational, kind `emergency`? no: writes `STATUS` on parent MEMBER item: `ladderState=watching`).
3. `Rung2GuardianCall` — same as rung 1 with `assigneeRole: guardian2` (falls back to guardian1 if no guardian2). Timeout/no_answer → `Rung3Neighbour`; reached → `Resolved`.
4. `Rung3Neighbour` — kind `neighbour`, assignee guardian1, text includes neighbour name/phone/address and a script. Timeout/no_answer → `Rung4Emergency`; reached → `Resolved`.
5. `Rung4Emergency` — Lambda `ladder-task` **without** token wait: kind `emergency`, text: "Call 112. Say: elderly parent unreachable since HH:MM, address …". Sets `ladderState=escalated`. → `Escalated` (Succeed).
6. `Resolved` — Lambda `ladder-status` sets `ladderState=ok`, closes open ladder tasks → Succeed.

## 3. `RecoveryCase` — post-loss pipeline
Input: `{"circleId","caseId","timeouts":{"confirm":86400,"call1930":900,"ncrp":86400,"mrm":604800}}`
States:
1. `Extract` — Lambda `recovery-agent` (container image, Strands) with `{"action":"extract"}`. Writes `extracted` on the case. Retry 2x on `Bedrock*` errors. Catch all → `Failed` (sets status error).
2. `ConfirmFields` — `ladder-task` `.waitForTaskToken`, kind `confirm_fields`, `TimeoutSecondsPath: $.timeouts.confirm`. Output `{"outcome":"confirmed","txns":[...]}`. Timeout → `ConfirmFieldsReminder` (creates guardian task, then loops back to `ConfirmFields` once; second timeout → `Failed`).
3. `Build` — Lambda `recovery-agent` `{"action":"build"}`: templates + LLM narrative → `artifacts`; status `awaiting_1930`.
4. `Call1930` — `.waitForTaskToken`, kind `call_1930`, timeout `$.timeouts.call1930`. Outcome `done` → `NCRPFiled`; `later` or timeout → `Escalate1930` (task to guardian2, then `NCRPFiled`).
5. `NCRPFiled` — `.waitForTaskToken`, kind `ncrp_filed`, timeout `$.timeouts.ncrp`. Output `{"outcome":"filed","ackNo":"329..."}`. Timeout → `EscalateNCRP` (guardian task, loop back once).
6. `MRMDecision` — Lambda `recovery-agent` `{"action":"mrm"}` → `{"eligible":bool,"firRequired":bool,"checklist":[...]}` stored in `artifacts.mrm`.
7. `MRMChoice` — eligible → `MRMTask` (`.waitForTaskToken`, kind `mrm`, timeout `$.timeouts.mrm`, timeout is non-fatal → `Done`); else → `Done`.
8. `Done` — Lambda `recovery-agent` `{"action":"finalize"}` sets status `filed`.
9. `Failed` — Lambda sets status `error` with message.

## Lambda contracts

### `ladder-task` (Python)
Input (from any state):
```json
{"kind":"guardian_call","rung":1,"assigneeRole":"guardian1","circleId":"...","parentSub":"...","reason":"missed_checkin",
 "caseId":"...", "taskToken":"...", "wait": true}
```
Creates the TASK item (text generated from kind + circle data, Hindi and English), stores the token when `wait` is true, sends push to the assignee (and to all guardians for `emergency`/`sos`). Returns `{"taskId": "..."}`. When `wait` is false, the state uses plain `arn:aws:states:::lambda:invoke`.

### `watch-check`, `ladder-status`
Small DynamoDB helpers, see backend README.

### `recovery-agent` (container)
`{"action":"extract"|"build"|"mrm"|"finalize"|"fail","circleId","caseId","error"?}`. Uses Strands `Agent` with tools `extract_transactions`, `validate_fields`, `lookup_ezero_threshold`, `mrm_eligibility`, `draft_narrative`. Deterministic parts (validation, templates, thresholds, MRM rules) are plain Python and unit-tested; the LLM only sees images (marked untrusted) and writes the narrative.
