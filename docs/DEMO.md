# Demo script (3:00) and pre-flight checklist

Authoritative script: `docs/BUILD_PLAN.md` section 9 (this file supersedes its timings, because the console
tour now covers every service the stack uses). Record with OBS in a single browser window: left pane parent
tile (seeded "Papa"), right pane guardian dashboard (seeded "Priya"), the Step Functions console and one
DynamoDB item in separate tabs. Voiceover after, cut to 3:00.

## Shot list

| # | Time | Shot | On screen | Voice | Console / notes |
|---|---|---|---|---|---|
| 1 | 0:00–0:18 | Hook slide | Sourced numbers, one per line with the source: ₹22,495 cr lost to cyber fraud in 2025 (MHA); 1,03,488 senior-citizen complaints, ₹4,005 cr (MHA reply in Rajya Sabha, 5 Aug 2026); digital arrest 2,97,727 complaints / ₹4,057 cr since 2022 (govt data via News18, Jul 2026); Karnataka recovery 5% → 2.2% (TOI, Mar 2026). Then a **generic mock** "SCAM DETECTED" red overlay, ours, not another team's. | "Every scam app assumes the victim can act. In the cases we studied, every save came from an outsider. Doosri Raay is the outsider." | Do not show "51% never report". Overlay is a mock we drew. |
| 2 | 0:18–0:33 | Parent tile | Left pane: Papa's Panchang tile: tithi and date, weather, "Amlodipine 08:00 · Metformin 20:00", the family photo (uploaded from `/settings` before recording). Cursor opens it once. | "Papa opens this every morning for the tithi and his medicines. Opening it is the check-in. Nothing else is asked of him, ever." | **Amplify Hosting**: URL visible in the address bar. |
| 3 | 0:33–1:03 | Watch → Ladder | Tab: Step Functions `Watch` execution passes its 45 s demo deadline, `StartLadder`, `Ladder` execution opens at `Rung1GuardianCall`. Right pane: Priya's task "Call Papa now". She taps **No answer**. Rung 2 goes to Rahul; rung 3 shows the neighbour script with Sharma ji's address. Cut to the DynamoDB TASK item for 2 s. | "Today he didn't open it. The watch expires, the ladder starts. Priya calls, no answer, that is the second signal. The neighbour gets a script. Papa's screen never changed, and nothing was recorded." | **Step Functions** at 0:33; **DynamoDB** at 0:48. Left pane must stay unchanged on camera. |
| 4 | 1:03–1:15 | Classifier card | Guardian view: forward the `whatsapp_cbi.png` screenshot → card in **watching/likely** state with tactics listed. Then paste the benign bank OTP → "Koi khatra nahi mila — phir bhi parivaar se poochhein." | "The checker is a minor tool. It never says safe." | The word "safe" must not be on screen. |
| 5 | 1:15–1:27 | Puchho | Papa taps "koi kehta hai CBI/police/TRAI hai" → the Polly Hindi clip of the I4C line plays; Priya's dashboard shows the notification task. | "If someone claims to be the police, Papa can hear the official line and his daughter knows in the same second." | **Amazon Polly** (`POST /puchho`). If audio fails on the recording machine the card still shows the text; say so. |
| 6 | 1:27–2:12 | Recovery case | Priya opens a case for Papa. Uploads `upi_success_1.png` and `upi_success_2.png`. Extracted fields appear beside each image; one UTR flagged invalid, she corrects it and confirms. 1930 script card. NCRP narrative with character count ≥ 200. e-Zero FIR threshold for Maharashtra ("check with 1930"). MRM checklist. Tab: `RecoveryCase` execution waiting at `NCRPFiled`; the 45 s demo timer expires → guardian task appears on the dashboard. | "After a loss, everyone else gives a 1930 button. We run the whole pipeline: extraction validated in code, the NCRP form's real rules, the state's e-Zero FIR threshold, and the refund module most victims never reach. Every step is a callback with a deadline." | **S3** upload at 1:45, **Lambda** at 1:50, **Bedrock** model id at 1:55, **Step Functions** again at 2:05. |
| 7 | 2:12–2:48 | Console tour, 3 s each (12 shots) | 2:12 Amplify app page → 2:15 Cognito user pool with the four seeded users → 2:18 API Gateway routes with the JWT authorizer and the 5 rps throttle → 2:21 Lambda function list (`api`, `classify-worker`, `ladder-task`, `watch-check`, `ladder-status`, `recovery-agent`) → 2:24 Lambda env showing `MODEL_ID=global.anthropic.claude-sonnet-4-6` and the fallback → 2:27 S3 bucket with Block Public Access on and the 7-day lifecycle rule → 2:30 ECR repository holding the `recovery-agent` image → 2:33 SSM Parameter Store `/doosriraay/<stack>/vapid-private-key` (SecureString, value hidden) → 2:36 CloudWatch Logs: the `api` function log group and the `RecoveryCase` state-machine log group → 2:39 X-Ray trace map for `POST /analyze` → 2:42 AWS Budgets: the USD 20 and USD 50 alarms → 2:45 the `api` function's IAM policy statement `PollyPuchhoClip` (Polly has no per-resource console object). | "Fourteen AWS services, and you saw the ones that matter doing work: hosting, identity, the API, the Lambdas, Bedrock, the bucket, the container registry, the secret store, logs, traces, the cost alarm and the voice." | Every service in the README table appears here or earlier. Keep each shot to 3 s; zoom 110%. |
| 8 | 2:48–3:00 | Close | Eval status slide: "70-item test set, harness `eval/run_eval.py`, run against Bedrock" and the summary row from `eval/results.md` **only if the model run has been executed**; otherwise the slide says "eval pending: numbers produced by the harness after deployment". Prior-art slide: Kavach, Rakshak, SwarVed AI and the four things we chose to do differently. Roadmap: bank-counter copilot, Khyaal/Emoha distribution. | "A seventy-item Hindi and English test set with benign controls, run through an evaluation harness against Bedrock; the numbers are in the README. What we learned: build the outsider." | End card: repo URL, live URL. If the eval has not run, change the voice line to "...the harness and the test set are in the repo". |

Voice total is about 140 words per minute; rehearse twice on Sunday morning, then record.

## Pre-flight checklist (run in order, tick each)

Environment
- [ ] `make deploy` finished green on the demo stack with `DemoTimeouts=1` (`GET /demo/config` returns `"demoTimeouts": true`, 45 s rungs).
- [ ] `MODEL_ID` is `global.anthropic.claude-sonnet-4-6`; the Haiku fallback smoke-tested from ap-south-1 today.
- [ ] Amplify Hosting shows the latest build; `/demo` route loads at the live URL.
- [ ] `BudgetEmail` was set on deploy and the SNS e-mail subscription confirmed (otherwise there is no cost alarm to show at 2:42).

Seed
- [ ] `make seed` (or `python scripts/seed.py --user-pool-id ... --client-id ... --api-url ...`) ran; summary table shows all four users and the circle; password stored in the team vault, not in the repo.
- [ ] **`DemoSeedEnabled=0` after seeding**: if `POST /demo/seed` was ever enabled, redeploy with `make deploy PARAMS='DemoSeedEnabled=0'` and confirm `POST /demo/seed` no longer serves before recording.
- [ ] Papa's profile has the neighbour, code word, medicines and `checkinHourIST=11`; a family photo uploaded from `/settings` (signed in as Papa) and holiday mode **off**.
- [ ] **Run `POST /demo/reset` from the guardian pane (the "Reset demo" button on `/demo`, signed in as Priya) before recording**: it stops leftover `Watch`/`Ladder`/`RecoveryCase` executions, closes open demo tasks and clears this browser's local state, so the dashboard starts clean. Confirm in the Step Functions console that no execution is still `Running`.
- [ ] `scripts/seed_demo_screenshots/*.png` on the recording machine (two UPI receipts, WhatsApp CBI, courier SMS, KYC SMS, genuine OTP, injection probe).

Tabs open, in this order
- [ ] Tab 1: `/demo` split view, logged in as Papa (left) and Priya (right).
- [ ] Tab 2: Step Functions console, state machines list (`Watch`, `Ladder`, `RecoveryCase`), region ap-south-1.
- [ ] Tab 3: DynamoDB `doosriraay` table, item explorer filtered on the demo `CIRCLE#` PK.
- [ ] Tabs 4–15, in shot-7 order: Amplify app, Cognito user pool users, API Gateway routes + authorizer, Lambda list, Lambda env (`classify-worker`), S3 bucket permissions + lifecycle, ECR repository, SSM Parameter Store entry, CloudWatch Logs (`api` function log group and the `RecoveryCase` state-machine log group), X-Ray trace map, AWS Budgets, IAM policy of the `api` function (statement `PollyPuchhoClip`).
- [ ] Browser zoom 110%, bookmarks bar hidden, notifications off, account emails other than the demo ones hidden, account id blurred in post if it is visible in the ECR/SSM ARNs.

Push
- [ ] Web Push (VAPID) works on the recording machine's Chrome **or** the guardian view is in the foreground and the voiceover says "push or foreground" as written. Do not claim background buzzing if it is not working on the day.

Content
- [ ] Hook slide numbers match README's table exactly (sources on screen).
- [ ] The word "safe" appears nowhere in the UI (`pytest tests -k safe` green).
- [ ] The "SCAM DETECTED" overlay in shot 1 is our own mock.
- [ ] The eval slide (shot 8) matches `eval/results.md`: if that file is still the placeholder, the slide says "eval pending" and shows no numbers.
- [ ] Hindi copy reviewed by a native speaker.

Timing rehearsal
- [ ] Watch deadline (45 s) started *before* recording shot 2 so the ladder fires during shot 3.
- [ ] Case opened *before* shot 6 begins so `Extract` has finished (container cold start).
- [ ] Two full dry runs timed at ≤ 3:05 raw.
