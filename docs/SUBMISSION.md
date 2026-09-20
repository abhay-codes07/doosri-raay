# Submission form answers: First Commit (Bharat Builds Tour, Event 01), 20 Sep 2026

Ready to paste into https://wemakedevs.org/aws/first-commit/submit. Placeholders in angle brackets are
filled by the team on submission day. One submission is judged for Build It, Ship It and Best UI together.

---

## Project name

**Doosri Raay** (दूसरी राय, "a second opinion")

## One-liner

A family app for digital-arrest scams where the adult child is the user, the parent's screen never shows a
warning, a missed morning check-in escalates through a Step Functions ladder to the family and a neighbour,
and after a loss the app runs the whole 1930 → NCRP → MRM recovery pipeline instead of showing a 1930 button.

## The idea

Isolation is the weapon; a second opinion is the antidote. A digital-arrest scam works by keeping an elderly
person on a video call, cut off from everyone who would say "that is not how the CBI works". Every scam app
we found assumes the victim can act: notice a warning, tap a button, paste a message. In the cases we
studied, nobody under a digital arrest did any of that. The people who stopped the scam were outsiders. So
Doosri Raay is the outsider: the family is the sensor, the family is the responder, and the parent is asked
for nothing under duress.

## The problem that made us build it

Indians lost **₹22,495 crore** to cyber fraud in 2025 (MHA). Senior citizens filed **1,03,488 complaints
worth ₹4,005 crore** (MHA reply in the Rajya Sabha, 5 Aug 2026, via ANI). Digital arrest alone accounts for
**2,97,727 complaints and ₹4,057.7 crore** since 2022 (government data reported by News18, Jul 2026).
Recovery is collapsing: Karnataka's recovery rate for digital-arrest losses fell from **5% to 2.2%** between
2025 and Jan–Feb 2026 (Times of India); Mumbai's 1930 helpline managed to put only **25.68%** of reported
money on hold (Rediff, 20 May 2026); nationally **₹10,700 crore is frozen against ₹323 crore refunded**
under the Money Restoration Module (Indian Express / Financial Express, Jul 2026, snippet-verified).

We read **25 documented Indian digital-arrest cases from 2025–26**. In every one, the save came from an
outsider: a bank manager (Pune ₹14 lakh, Nalgonda ₹18 lakh, Lucknow ₹1.5 crore), a relative (Bhopal,
Moradabad, Indore) or the police (Rajkot, a 112 call). Self-terminated cases ended only when the victim
happened to read a newspaper (Alwar, after 165 days). Victims' own words: "questioning authority felt more
dangerous than obeying it"; "we felt almost hypnotised" (Hindustan Times, Lucknow, Jan 2026). Two more
facts made a victim-side detector the wrong frame: 82% of Singapore's scam losses are self-authorised
transfers (Singapore Police Force, 2025) and security warnings habituate by the second exposure (Anderson et
al., CHI 2015). Sources are cited inline; a widely quoted "51% never report" figure is
deliberately left out because we could not verify it.

## What the project does

**Hero 1: the passive isolation ladder.** The parent's app is a genuinely useful Panchang tile: today's tithi
and date, the weather (Open-Meteo), medicine reminders, a daily thought and a family photo. Opening it is the
check-in (`POST /checkin`, once per IST day). If the tile is not opened by the parent's deadline **and** a
guardian's call goes unanswered (the two-signal rule), a Step Functions `Ladder` escalates guardian 1 →
guardian 2 → a named neighbour with a script and the address → 112 guidance. Zero victim action. No banner,
no score and no warning on the parent's screen at any point.

**Hero 2: the recovery case manager.** A guardian (or the parent) opens a case after a loss. A Strands agent
extracts UTR, amount, payee and time from screenshots; code validates every field (12-digit UTR regex, amount
range, parseable time, rail-aware references for UPI/IMPS and NEFT/RTGS) and the user confirms each one beside
the image. Fixed templates fill the 1930 script and the bank freeze letter; the model writes only the NCRP
narrative, enforced to ≥ 200 characters and the portal's character set and rejected if it carries any UTR
or amount that is not on the confirmed list. The case looks up the state's e-Zero FIR threshold and MRM
eligibility, each card showing its source and date, and runs as a long-lived Step Functions execution where
every human step is a `waitForTaskToken` callback with a deadline (24 h to confirm fields, 15 min for the
1930 call, 24 h to file on NCRP, 7 days for MRM) that escalates to a guardian. Nothing is filed on anyone's
behalf: there are no public APIs for 1930, NCRP or MRM, so the app gives `tel:1930`, portal deep links and
copy-to-clipboard, and says so.

**Minor tool: the three-state checker.** Screenshot or pasted text → one Bedrock Converse call with forced
tool use → `none` / `watching` / `likely`, the tactic (authority, urgency, secrecy, payment switch,
verification account) and a two-line "what to say" in Hindi and English. It never says "safe".

**Also built.** *Puchho* ("ask the person"): two calm buttons in the parent tile's Madad section. "Someone says
they are police / CBI / bank" plays the I4C advisory line in Hindi through Amazon Polly and notifies the
guardians; "someone says my son is in trouble" sends the son a code-word challenge and the parent sees the
answer. A covert triple-tap on the date sends an SOS with location only (no audio). Web Push (VAPID) delivers
guardian tasks; without a subscription the dashboard polls every 5 s. A `/demo` split view shows the parent
tile and the guardian dashboard side by side in one browser.

## Live demo

**`https://main.d2inambt66a14p.amplifyapp.com/try` — no sign-up needed.** The `/try` route drops a judge into a seeded judge circle
(parent tile on the left, guardian dashboard on the right) without creating an account. Timers on the judge
stack are the 45-second demo timers, so a missed check-in escalates while you watch; press "Reset demo" first
if a previous judge left a ladder running.

Judge accounts (for the full sign-in experience, optional): `papa@demo.doosriraay.in` (parent),
`priya@demo.doosriraay.in` (guardian 1), `rahul@demo.doosriraay.in` (guardian 2),
`aman@demo.doosriraay.in` (son). Password: `<JUDGE_PASSWORD>` (shared here only, never in the repo; rotated
on `<ROTATION_DATE>`, after the judging window). The stack is throttled and every user has a daily quota of
LLM calls.

Repository: `<REPO_URL>` (public, MIT).

## Demo video

`<YOUTUBE_URL>` (unlisted, 3:00). Every AWS service is shown in the video; timestamps are in the README's services table.

## AWS services used, and how

**Amazon Bedrock.** Two models through the Converse API: `global.anthropic.claude-sonnet-4-6` as `MODEL_ID`
and `global.anthropic.claude-haiku-4-5-20251001-v1:0` as `FALLBACK_MODEL_ID`; the code switches on
throttling or any model error. The classifier makes a single Converse call with **forced tool use**
(`toolChoice: {tool: {name}}`) so the output is the tool's JSON schema (an enum of three states, an enum of
tactics, capped strings) and never free text; the screenshot or pasted message is passed as untrusted user
content with a system prompt that says never to follow instructions inside it. The recovery agent uses
Bedrock twice: vision extraction of transactions into a tool schema, and the NCRP narrative, which code
re-checks. Nothing the model returns is shown without an enum, length and character-set check.

**AWS Step Functions (Standard).** Three state machines. `Watch` is started by every check-in (and by
onboarding) with the next deadline in its input; it waits, reads the last check-in, and either ends or
starts `Ladder`. Because each check-in starts the next `Watch`, there is no EventBridge scheduler and the
missed-check-in trigger is itself an execution in the console. `Ladder` and `RecoveryCase` model every
human step as `arn:aws:states:::lambda:invoke.waitForTaskToken` with **`TimeoutSecondsPath` read from the
execution input** (`$.timeouts.rung`, `$.timeouts.ncrp`, …), so the same definition runs with 15-minute
rungs in production and 45-second rungs on camera (`DemoTimeouts=1`). The task token is stored on the
DynamoDB TASK item; `POST /tasks/{id}/complete` calls `SendTaskSuccess`, and a timeout moves the machine to
the next rung or to a guardian escalation.

**AWS Lambda (Python 3.12).** Six functions from one `CodeUri`: `api` (thin handlers behind API Gateway),
`classify-worker` (asynchronously invoked by `POST /analyze`, so the API returns `202` and the client polls),
`ladder-task` (writes the TASK item with the token and pushes to the guardian), `watch-check`,
`ladder-status`, and `recovery-agent`, which is a **container image** because the Strands SDK and Pillow do
not fit a zip deployment comfortably. All functions have `Tracing: Active`.

**Amazon API Gateway (HTTP API).** Every route sits behind a Cognito **JWT authorizer**
(`IdentitySource: $request.header.Authorization`, audience = the user-pool client). Handlers take the caller's
`sub` from the authorizer claims and derive the circle from the caller's own profile item; `circleId` never
comes from the request body or path. Stage throttling (20 rps, burst 50) and a per-user daily LLM quota are
the cost guards. CORS is limited to the `AppOrigins` parameter.

**Amazon Cognito.** One user pool and one app client (USER_PASSWORD_AUTH for the seeded demo identities, SRP
through Amplify for real users). The frontend sends the **ID token**, which is what the HTTP API JWT
authorizer validates against the client id. The `/demo` split view signs the parent in as a second identity
with the token kept in memory only.

**Amazon DynamoDB.** One table (`doosriraay`), single-table design: `USER#<sub>/PROFILE`,
`CIRCLE#<id>/MEMBER#…`, `CHECKIN#<date>`, `TASK#<ts>#<id>` (carrying the Step Functions task token, the
deadline and a TTL), `REPORT#`, `CASE#`, and `QUOTA#<sub>/<date>`. TTL on tasks, reports and SOS items;
point-in-time recovery on. Every read handler compares the item's `circleId` with the caller's and returns
404 on mismatch.

**Amazon S3.** One private bucket for screenshots and family photos: uploads go through a **presigned POST**
whose policy has `content-length-range` (0 to `UploadMaxBytes`, 3.5 MB) and `starts-with $Content-Type
image/`; SSE-S3, Block Public Access on all four settings, CORS to the app origins, a 7-day lifecycle rule on
uploads. The Polly clip for Puchho is synthesised once and cached in the same bucket under `audio/`, served
by a short presigned GET. The family photo is served by a 1-hour presigned URL.

**Amazon Polly.** `SynthesizeSpeech` (neural Hindi voice, `PollyVoiceId` parameter, `Aditi` standard as the
fallback) renders the I4C advisory line for the "someone says they are police" button; the API Lambda's IAM
policy has a single statement for it (`PollyPuchhoClip`). This is the only place voice is used.

**AWS Amplify Hosting.** Serves the Vite PWA (parent tile, guardian dashboard, `/demo`, `/try`) from the
repo's `frontend/` with `amplify.yml`; an SPA rewrite rule sends every path to `index.html`, and `VITE_*`
variables come from the stack outputs.

**AWS Systems Manager Parameter Store.** The VAPID private key for Web Push is a **SecureString** at
`/doosriraay/<stack>/vapid-private-key`, read with `WithDecryption=True`. CloudFormation cannot create a
SecureString, so the stack creates a placeholder and `make set-vapid` overwrites it.

**Amazon ECR.** Holds the `recovery-agent` container image; `sam build` builds it from
`backend/recovery_agent/Dockerfile` (linux/amd64, BuildKit attestations disabled so Lambda accepts the
manifest) and `sam deploy` pushes it to the managed repository.

**AWS Budgets.** Two monthly ACTUAL-cost budgets at USD 20 and USD 50 with e-mail alerts, created only when
the `BudgetEmail` parameter is set. With the JWT authorizer, the throttle and the daily quota this is the
last line against a public demo running up a bill.

**Amazon CloudWatch Logs.** An explicit 14-day log group for every function and for each state machine
(logging level ERROR, execution data off, so task tokens and transactions are never logged), plus the HTTP
API access log.

**AWS X-Ray.** `Tracing: Active` on every function through the SAM Globals, so the API → Lambda hop is traced.
Downstream calls (DynamoDB, Bedrock) are traced only if the X-Ray SDK is installed in the backend
(`aws-xray-sdk` in `backend/requirements.txt`); see the feedback below.

That is nine services doing product work (Bedrock, Step Functions, Lambda, API Gateway, Cognito, DynamoDB, S3,
Polly, Amplify Hosting) and five for operations (SSM, ECR, Budgets, CloudWatch Logs, X-Ray).

## Feedback on AWS services (honest, from this build)

1. **Bedrock from Mumbai means global inference profiles.** Claude Haiku 4.5 and Sonnet 4.6 are reachable from
   `ap-south-1` only through `global.anthropic.*` profile ids, and the IAM policy needs the profile *and* the
   underlying foundation-model ARNs in every region the profile can route to. "Everything runs in ap-south-1" is
   true of our stack, not of where inference runs; the docs should say this on the model page, not in a
   footnote. Amazon Nova 2 Sonic (which we wanted for the Hindi voice line) is not available in ap-south-1 at
   all, which is why Puchho uses Polly.
2. **Bedrock is not in the Free tier.** A student account needs the Paid plan enabled before the first Converse
   call succeeds; the error you get until then is not obviously a billing error. A one-line banner in the Bedrock
   console would save every hackathon team an hour.
3. **Strands does not fit a zip Lambda comfortably.** With boto3 and Pillow the bundle blows past the size where
   cold starts and layer limits stop being fun, so the recovery agent became a container image. That is fine, but
   it means ECR, Docker on every laptop, and `--platform linux/amd64` plus `BUILDX_NO_DEFAULT_ATTESTATIONS=1`
   (Lambda rejects the multi-manifest OCI index BuildKit produces by default). None of this is in the Strands
   Lambda guide.
4. **`sam deploy --template infra/template.yaml` is a trap.** Passing the source template makes SAM skip the
   built template, so the container function has no `ImageUri` and the deploy fails with an unhelpful message.
   Drop `--template` on deploy. SAM could warn when a `PackageType: Image` function is deployed from an unbuilt
   template.
5. **The HTTP API JWT authorizer wants the ID token.** The Cognito access token has no `aud` claim, so every
   route returns 401 until you send the ID token instead. Amplify's `fetchAuthSession()` hands you both and
   nothing says which one the authorizer expects.
6. **SES stays sandboxed for a hackathon.** Production access takes a review we could not wait for, so e-mail
   notifications were dropped for in-app tasks and Web Push.
7. **SNS SMS in India needs DLT registration.** Transactional SMS to Indian numbers requires a registered
   sender id and templates on a DLT platform; that is a regulatory fact, not an AWS fault, but the SNS console
   could say it before you spend an evening on it. We ship no SMS.
8. **Amplify Hosting needs an SPA rewrite rule.** Deep links such as `/case/<id>` 404 until the
   `</^[^.]+$|\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json|webp)$)([^.]+$)/>` → `/index.html`
   200 rewrite is added; the Vite preset should add it by default.
9. **LocalStack community edition has no Step Functions or Bedrock.** DynamoDB, S3, SSM and Lambda run locally;
   the state machines and the model do not, so the "whole stack locally" is honest only with a stub for the
   classifier and the state machines left in the cloud. A local Step Functions emulator in the community tier
   would make the SAM + LocalStack story complete.
10. **The Step Functions console is the best demo visual we have.** Watching `Watch` expire, `StartLadder`
    fire and `Ladder` sit in `Rung1GuardianCall` waiting for a human is the whole product in one screen.
11. **`waitForTaskToken` + `TimeoutSecondsPath` is underdocumented.** It is exactly the pattern for "a human
    has N minutes before we escalate" with a per-environment N, and we found it in the ASL reference, not in a
    tutorial or a Workflow Studio template.
12. **X-Ray without the SDK is one node.** `Tracing: Active` traces the API → Lambda hop only; the DynamoDB,
    Bedrock and Step Functions segments need `aws-xray-sdk` patching in code. The console's empty trace map
    could say so.

## Build It stack usage

- **Strands Agents SDK** for the recovery agent's tool loop; the tools (`extract_transactions`,
  `validate_fields`, `lookup_ezero_threshold`, `mrm_eligibility`, `draft_narrative`) are plain functions, and
  a deterministic path runs the same functions in order when Strands is not installed or the agent fails.
- **AWS SAM** for the whole stack (`infra/template.yaml`: table, bucket, user pool, HTTP API, six functions,
  three state machines, log groups, budgets; `make validate` runs `sam validate --lint` and an ASL check).
- **LocalStack + SAM local** for local mode (`docker-compose.yml`, `make local-*`): see the README's
  "Running it locally" section for exactly what runs locally and what does not.
- **Cedar** for authorization: which role may complete which task kind, open or read a case, upload a photo
  or reset the demo as a policy set in `backend/common/authz/policies.cedar`, evaluated inside the API
  Lambda with the caller's role and circle as the principal (`cedarpy`, the Rust engine, with a fallback
  evaluator of the same file); `forbid` rules carry `@id`s that become bilingual 403 messages, and a 16-row
  policy table is tested against both engines.

## Team

| Role | Name | What they did (from the git history) |
|---|---|---|
| Frontend (PWA) | Rajat Nagda | Vite + React PWA with a custom bilingual (Hindi/English) auth flow, the parent Panchang tile with check-in, Puchho and covert SOS, the guardian dashboard with task cards and the ladder status poll, case intake (5 screenshots, 3.5 MB cap, rows paired to images, manual rows), case detail with source lines under the e-Zero FIR / MRM / NCRP cards and the 14-digit ack rule, Settings with photo upload and holiday mode, the `/demo` split view and `/try`, the service worker and Web Push button, `amplify.yml`. |
| Backend and model | Abhay Singh | API handlers (profile, circles, check-in, SOS, tasks, uploads, analyze/reports, cases, puchho, push, demo, sources), the classifier worker (Converse with forced tool use, untrusted-input wrapping, enum checks), the Strands recovery agent with plain-code tools and the deterministic fallback, the NCRP narrative re-check for foreign UTRs and amounts, rail-aware reference validation, the Polly clip cache, Web Push, the 70-item eval set and harness, the tests. |
| Infrastructure and Step Functions | Abhay Singh | The SAM template (table, hardened bucket and presigned POST policy, Cognito, HTTP API with JWT authorizer and throttle, six functions, container image for the agent, log groups, Budgets, SSM parameter), the `Watch`, `Ladder` and `RecoveryCase` definitions with `waitForTaskToken` and `TimeoutSecondsPath`, the Makefile (`deploy`, `image-check`, `outputs`, `env`, `seed`, `set-vapid`), the LocalStack local mode, the first-deploy checklist. |
| Product, demo and research | Rajat Nagda | The 25-case and 50-study research and the pivot, the sourced problem numbers, prior-art review, the build plan and the API / data-model / state-machine contracts, the seed script and synthetic screenshots, the demo shot list and pre-flight, the README, this submission, the blog draft and the family pact card. |

Student verification on AWS Builder Center for every teammate: `<BUILDER_CENTER_LINKS>`.

## AI tools disclosure

Claude Code (Claude Fable 5.1, Anthropic) was used for research synthesis, architecture and code generation
across the repo and ran the local tests and builds on our machines; it never had AWS credentials. All AWS
deployment, the eval run against Bedrock, the demo recording and the Hindi copy review are by the team. Runtime
models are Claude Sonnet 4.6 and Haiku 4.5 on Amazon Bedrock. Full table: `docs/AI_TOOLS.md`.

## What we learned

- **The pivot:** a victim-side detector is the wrong frame for digital arrest; the family is the sensor and the
  responder. Build the outsider.
- **Forced tool use is structured output.** One Converse call with `toolChoice` pinned to a tool schema replaces
  a parser, a retry loop and most of the prompt.
- **Humans are `waitForTaskToken` states.** A guardian with 15 minutes to answer is a state with a timeout, and
  the escalation is a transition.
- **A self-renewing `Watch` replaces a scheduler.** Each check-in starts the next execution; the trigger is
  visible in the console and there is nothing to reconcile.
- **Strands is optional at runtime.** The tools are plain functions, so the same pipeline runs without the
  agent, and the narrative is re-checked by code whichever path produced it.
- **Say what does not ship.** The judges' time is better spent on what works than on discovering what does not.

## What does not ship, and why

No in-call listening, audio transcription or voice-clone detection (Android blocks in-call audio for
third-party apps; in-the-wild deepfake-audio detection loses ~48% AUC). No red overlay warnings (they
habituate and the scammer tells the victim to ignore them). No "agent conferences a guardian" (a PWA cannot
place calls). No ambient audio on SOS (the mic indicator breaks covertness). No mock UPI freeze (a real hold is
a bank function). No hotspot map, no SES e-mail, no SMS. Not built yet: in-app pact revocation, a check-in
history view, a Chakshu step. Background Web Push is best-effort and the guardian view is shown in the
foreground when it does not deliver. The classifier eval against Bedrock has not been run at the time of
writing, so no accuracy number is claimed.

## Disclaimer

Doosri Raay is not a government service and is not affiliated with I4C, 1930 or cybercrime.gov.in. Anything it
shows must be verified with the 1930 helpline or on cybercrime.gov.in before acting on it.
