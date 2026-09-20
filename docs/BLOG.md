# We built the outsider: why our scam project has no scam warning on the parent's screen

*Draft for the WeMakeDevs blog, First Commit (Bharat Builds Tour, Event 01), 20 Sep 2026. Before publishing,
confirm against the repo that `policies.cedar`, `docs/sources-manifest.json`, the `/sources` panel and `/try`
have landed; they were still in progress when this draft was written.*

Doosri Raay (दूसरी राय, "a second opinion") is a family app for digital-arrest scams. The strange thing about
it, for a scam project, is that the elderly parent's screen never shows a warning, a score or the word "scam".
Here is why, what AWS taught us in three days, and what we did not build.

## The problem, in numbers we could source

Indians lost ₹22,495 crore to cyber fraud in 2025 (MHA). Senior citizens filed 1,03,488 complaints worth
₹4,005 crore (MHA reply in the Rajya Sabha, 5 Aug 2026). "Digital arrest", where a caller in a police or CBI
costume keeps a person on a video call for hours or days until they transfer their savings for
"verification", accounts for 2,97,727 complaints and ₹4,057.7 crore since 2022 (government data via News18,
July 2026). Recovery is the part nobody talks about: Karnataka's recovery rate fell from 5% in 2025 to 2.2%
in early 2026 (Times of India); nationally ₹10,700 crore sits frozen against ₹323 crore refunded (Indian
Express).

## The pivot, with evidence

Our first plan was the usual one: listen to the call, detect the script, show a red "SCAM DETECTED"
overlay, alert the family, link to 1930. Three findings made us throw it out.

First, the victim authorises the payment. 82% of Singapore's scam losses are self-authorised transfers
(Singapore Police Force, 2025), and Indian digital-arrest money moves by RTGS/NEFT to fresh mule accounts,
so payee-risk checks like PhonePe Protect do not fire. Second, warnings habituate and the scammer simply says
"ignore that" (Anderson et al., CHI 2015; Akhawe and Felt, USENIX Security 2013). Third, and this decided it:
we read 25 documented Indian digital-arrest cases from 2025–26, and in every single one the save came from an
outsider. A bank manager in Pune, Nalgonda, Lucknow; a daughter in Bhopal and Moradabad; a 112 call in
Rajkot. Victims described themselves as "almost hypnotised" (Hindustan Times, Lucknow, Jan 2026). Nobody
under a digital arrest opens a scam checker.

So we built the outsider. The adult child is the user. The parent's app is a genuinely useful Panchang tile:
today's tithi, the weather, "Amlodipine 08:00 · Metformin 20:00", a family photo. Opening it in the morning
is the check-in. If it is not opened by the parent's deadline and a guardian's call goes unanswered (two
signals, never one), a Step Functions ladder escalates: guardian 1, guardian 2, a named neighbour with a
script and the address, then 112 guidance. The parent does nothing. Nothing appears on their screen.

After a loss, the same app runs the whole recovery pipeline instead of showing a 1930 button: screenshots go
to a Strands agent whose tools are plain code, every UTR and amount is validated by regex and confirmed by a
human beside the image, the 1930 script and the bank letter are fixed templates, the model writes only the
NCRP narrative and code re-checks it for foreign references, and the case looks up the state's e-Zero FIR
threshold and the Money Restoration Module rules. Each human step is a `waitForTaskToken` state with a
deadline that escalates to a guardian.

## Three things AWS taught us

**Step Functions is the product, not the plumbing.** We had planned an EventBridge scheduler for the daily
deadline. Instead each check-in starts a `Watch` execution that waits until tomorrow's deadline and then
either ends or starts the `Ladder`. The missed-check-in trigger is itself an execution you can watch in the
console, which turned out to be the best demo visual we have. The pattern that carried both heroes is
`.waitForTaskToken` with `TimeoutSecondsPath` read from the execution input, so the same definition runs
with 15-minute rungs in production and 45-second rungs on camera. That combination is underdocumented; we
found it in the ASL reference, not a tutorial.

**Bedrock from Mumbai means global inference profiles and a Paid plan.** Claude Haiku 4.5 and Sonnet 4.6 are
reachable from ap-south-1 only through `global.anthropic.*` profile ids, so "everything in ap-south-1" is
true of the stack but not of where inference runs, and we say so. Bedrock is not in the Free tier, so a
student account needs the Paid plan before the first Converse call. Forced tool use (`toolChoice`) gave us
structured output without a parser; an enum of three states and a length cap did more for safety than any
prompt sentence.

**Packaging and auth details eat hours.** The Strands SDK does not fit a zip Lambda comfortably, so the
recovery agent is a container image through ECR. `sam deploy --template infra/template.yaml` silently uses
the source template and fails on the missing `ImageUri`; drop the flag. The HTTP API JWT authorizer wants the
Cognito ID token, not the access token. Amplify Hosting needs an SPA rewrite rule or deep links 404. A VAPID
key in an SSM SecureString cannot be created by CloudFormation, so there is a `make set-vapid`.

## The organisers' five techniques, and where they are in the repo

- **Rules as data.** The e-Zero FIR thresholds, MRM eligibility rules and the classifier's keyword patterns
  live in JSON files (`backend/recovery_agent/rules_data.json`, `backend/classify_worker/patterns.json`)
  that code loads and the verifier reads.
- **Documents you can prove.** Every fact card in the app shows a "Source: outlet, date" line. The sources
  are snapshotted and hashed into `docs/sources-manifest.json`; `scripts/verify_sources.py` re-verifies
  them and the app's `/sources` panel shows the same hashes.
- **Authorization as policy.** Which role may complete which task, open a case or reset the demo is a Cedar
  policy set (`backend/common/authz/policies.cedar`) evaluated in the API Lambda, with the circle taken from
  the caller's profile and never from the request.
- **A constrained, checked model.** Three states, never "safe"; forced tool use; enum and length checks in
  code; the NCRP narrative rejected if it carries a UTR or amount that is not in the confirmed list.
- **The whole stack locally.** `docker-compose.yml` starts LocalStack (S3 and DynamoDB) and `sam local`
  runs the API against it (`make local-up`, `local-bootstrap`, `local-api`). LocalStack's community edition
  has no Step Functions, Bedrock or Polly, so a stub records a state-machine start instead of calling it and
  anything with a timer or a model needs the cloud stack; the README says exactly which routes work locally.

## What we did not build, and why

No in-call listening or voice-clone detection: Android blocks in-call audio for third-party apps, and
in-the-wild deepfake detection loses about 48% AUC (Deepfake-Eval-2024). No red overlay. No "agent calls the
guardian": a PWA cannot place calls, so the guardian gets a task and calls. No ambient audio on the covert
SOS: the microphone indicator breaks covertness. No mock UPI freeze: a real hold is a bank function, a mock
one is theatre. No auto-filing on NCRP or 1930: there are no public APIs, so we ship deep links and a script,
and say so.

## Where the evaluation stands

The repo has a 70-item hand-written Hindi, Hinglish and English test set (21 benign controls, 14 softened
adversarial scams, 2 prompt-injection probes) and a harness (`eval/run_eval.py`) that reports per-pretext
precision and recall against Bedrock. That run has not been executed at the time of writing, so we claim no
accuracy number. A three-state output is the design response to the published pattern (LLM scam detectors at
~1.0 recall and 0.70–0.77 precision on hard data): "watching" is where the precision lives.

## A necessary disclaimer

Doosri Raay is a family tool built in three days by students, not a government service, and it is not
affiliated with I4C, 1930 or cybercrime.gov.in. Anything it tells you, from a threshold to a checker verdict,
must be verified with the 1930 helpline or on cybercrime.gov.in before you act on it. If money has moved, call
1930 first.

The code is MIT-licensed at `https://github.com/abhay-codes07/doosri-raay`; the live demo needs no sign-up at `<AMPLIFY_URL>/try`.
