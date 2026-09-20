# Demo script (3:00) and pre-flight checklist

This file is the authoritative shot list (it supersedes the timings in `docs/BUILD_PLAN.md` section 9).
Record with OBS in a single browser window: left pane parent tile (seeded "Papa"), right pane guardian
dashboard (seeded "Priya"), the Step Functions console and one DynamoDB item in separate tabs, and a terminal
for the sources-verification shot. Voiceover after, cut to 3:00.

## Shot list

| # | Time | Shot | On screen | Voice | Console / notes |
|---|---|---|---|---|---|
| 1 | 0:00–0:18 | Hook slide | Sourced numbers, one per line with the source: ₹22,495 cr lost to cyber fraud in 2025 (MHA); 1,03,488 senior-citizen complaints, ₹4,005 cr (MHA reply in Rajya Sabha, 5 Aug 2026); digital arrest 2,97,727 complaints / **₹4,057.7 cr** since 2022 (govt data via News18, Jul 2026); Karnataka recovery 5% → 2.2% (TOI, Mar 2026). Then a **generic mock** "SCAM DETECTED" red overlay, ours, not another team's. | "Every scam app assumes the victim can act. In the twenty-five cases we studied, every save came from an outsider: a bank manager, a daughter, a neighbour. Doosri Raay is the outsider." | Do not show "51% never report". Overlay is a mock we drew. Numbers must match the README table exactly, including the decimal. |
| 2 | 0:18–0:33 | Parent tile | Left pane: Papa's Panchang tile: tithi and date, weather with the "Open-Meteo" credit, "Amlodipine 08:00 · Metformin 20:00", the family photo (uploaded from `/settings` before recording). Cursor opens it once. | "Papa opens this every morning for the tithi and his medicines. Opening it is the check-in. Nothing else is asked of him, ever, and there is no warning on this screen for a scammer to see." | **Amplify Hosting**: URL visible in the address bar. |
| 3 | 0:33–1:03 | Watch → Ladder | Tab: Step Functions `Watch` execution passes its 45 s demo deadline, `StartLadder`, `Ladder` execution opens at `Rung1GuardianCall`. Right pane: Priya's task "Call Papa now". She taps **No answer**. Rung 2 goes to Rahul; rung 3 shows the neighbour script with Sharma ji's address. Cut to the DynamoDB TASK item (with its `taskToken` and `expiresAt`) for 2 s. | "Today he didn't open it. The watch expires and starts the ladder. Priya calls, no answer: that is the second signal. Rahul, then the neighbour with a script and the address, then 112 guidance. Papa's screen never changed, and nothing was recorded. Every rung is a Step Functions task token with a deadline." | **Step Functions** at 0:33; **DynamoDB** at 0:48. Left pane must stay unchanged on camera. |
| 4 | 1:03–1:15 | Classifier card | Guardian view: forward the `whatsapp_cbi.png` screenshot → card in **watching/likely** state with tactics listed. Then paste the benign bank OTP → "Koi khatra nahi mila — phir bhi parivaar se poochhein." | "The checker is a minor tool: one Bedrock call, forced to answer through a tool schema, three states. It never says safe." | The word "safe" must not be on screen. |
| 5 | 1:15–1:27 | Puchho | Papa taps "koi kehta hai police / CBI / bank" → the Polly Hindi clip of the I4C line plays; Priya's dashboard shows the notification task. | "If someone claims to be the police, Papa can hear the official I4C line in Hindi, and his daughter knows in the same second." | **Amazon Polly** (`POST /puchho`; clip cached in S3). If audio fails on the recording machine the card still shows the text; say so. |
| 6 | 1:27–2:05 | Recovery case | Priya opens a case for Papa. Uploads `upi_success_1.png` and `upi_success_2.png`. Extracted fields appear beside each image; one UTR flagged invalid, she corrects it and confirms. 1930 script card. NCRP narrative with character count ≥ 200 and its "Source" line. e-Zero FIR threshold for Maharashtra ("check with 1930"). MRM checklist. Tab: `RecoveryCase` execution waiting at `NCRPFiled`; the 45 s demo timer expires → guardian task appears on the dashboard. | "After a loss, everyone else gives a 1930 button. We run the whole pipeline: extraction validated in code and confirmed beside the image, the NCRP form's real rules, the state's e-Zero FIR threshold, and the refund module most victims never reach. The thresholds and rules are data files, not prompts. Every step is a callback with a deadline." | **S3** upload at 1:40, **Lambda** at 1:45, **Bedrock** model id at 1:50, **Step Functions** again at 2:00. |
| 7 | 2:05–2:29 | Console tour, 2 s each (12 shots) | 2:05 Amplify app page → 2:07 Cognito user pool with the seeded users → 2:09 API Gateway routes with the JWT authorizer and the stage throttle → 2:11 Lambda function list (`api`, `classify-worker`, `ladder-task`, `watch-check`, `ladder-status`, `recovery-agent`) → 2:13 Lambda env showing `MODEL_ID=global.anthropic.claude-sonnet-4-6` and the fallback → 2:15 S3 bucket with Block Public Access on and the 7-day lifecycle rule → 2:17 ECR repository holding the `recovery-agent` image → 2:19 SSM Parameter Store `/doosriraay/<stack>/vapid-private-key` **(only if `make set-vapid` ran: it must show Type SecureString, value hidden; otherwise skip this shot)** → 2:21 CloudWatch Logs: the `api` function log group and the `RecoveryCase` state-machine log group → 2:23 **X-Ray trace map** for `POST /analyze` (the SDK patches boto3, so the map shows API Gateway → Lambda → DynamoDB → Bedrock; if the map is empty on the day, show the finished `Ladder` execution graph instead) → 2:25 AWS Budgets: the USD 20 and USD 50 alarms **(only if `BudgetEmail` was set on deploy; otherwise skip)** → 2:27 the `api` function's IAM policy statement `PollyPuchhoClip` (Polly has no per-resource console object). | "One SAM stack. Nine services doing product work, five for operations, and you saw them doing it: hosting, identity, the API, the Lambdas, Bedrock, the bucket, the container registry, the secret, the logs, the ladder's execution graph, the cost alarm and the voice." | Every service in the README table appears here or earlier. Keep each shot to 2 s; zoom 110%. Skipped shots shorten the tour; give the seconds to shot 8. |
| 8 | 2:29–2:49 | Sources verified | Terminal: run the sources verification command (`python scripts/verify_sources.py`, flags as in the script's docstring) so the output lists each source with its hash and "OK"; then the app's `/sources` panel (or the `GET /sources` response) showing the same hashes beside the e-Zero FIR and MRM cards. | "Every number and rule the app shows comes from a source we snapshot and hash. This command re-verifies the snapshot against `docs/sources-manifest.json`, and the app shows the same hash beside the fact. If the source changes, the check fails before a judge sees a stale threshold." | Run the command once before recording so the output is instant. If the verify script or the panel is not in the repo on the day, drop this shot and give the 20 s to shot 6 (slower recovery walk-through). |
| 9 | 2:49–3:00 | Close | Eval status slide: "70-item test set, harness `eval/run_eval.py`, run against Bedrock" and the summary row from `eval/results.md` **only if the model run has been executed**; otherwise the slide says "eval pending: numbers produced by the harness after deployment". One line: prior art named (Kavach, Rakshak, SwarVed AI) and what we did differently. End card: repo URL, live URL with `/try`. | "A seventy-item Hindi and English test set with benign controls and an evaluation harness against Bedrock are in the repo. What we learned: build the outsider." | If the eval has run, change the voice line to "...the numbers are in the README". |

Voice track is about 300 words over 3:00, roughly **100 words per minute**: unhurried, with room for the
Hindi words. The earlier cut was ~75 wpm, which is why shots 3, 6 and 8 carry a sentence of "what we learned"
narration now. Rehearse twice on Sunday morning, then record.

## Pre-flight checklist (run in order, tick each)

Environment
- [ ] `make deploy` finished green on the demo stack with `DemoTimeouts=1` (`GET /demo/config` returns `"demoTimeouts": true`, 45 s rungs).
- [ ] `MODEL_ID` is `global.anthropic.claude-sonnet-4-6`; the Haiku fallback smoke-tested from ap-south-1 today.
- [ ] Amplify Hosting shows the latest build; `/demo` **and `/try`** load at the live URL. `/try` is the judge path: open it in a private window and confirm it needs no sign-up and lands in a seeded judge circle with a clean dashboard.
- [ ] `BudgetEmail` was set on deploy and the SNS e-mail subscription confirmed; **if not, drop the Budgets shot** (2:25) rather than show an empty Budgets page.
- [ ] `make set-vapid VAPID_PRIVATE_KEY=...` ran and the SSM parameter shows Type **SecureString**; **if not, drop the SSM shot** (2:19), it would show the `REPLACE_ME` placeholder as a plain String.
- [ ] Open the X-Ray trace map once before recording so the `POST /analyze` trace exists; if it is empty, shot 2:23 becomes the `Ladder` execution graph.

Seed
- [ ] `make seed` (or `python scripts/seed.py --user-pool-id ... --client-id ... --api-url ...`) ran; summary table shows all four users and the circle; password stored in the team vault, not in the repo.
- [ ] **`DemoSeedEnabled=0` after seeding**: if `POST /demo/seed` was ever enabled, redeploy with `make deploy PARAMS='DemoSeedEnabled=0'` and confirm `POST /demo/seed` no longer serves before recording.
- [ ] Judge circles seeded separately from the recording circle, so a judge pressing "Reset demo" during judging cannot stop the ladder on camera and vice versa.
- [ ] Papa's profile has the neighbour, code word, medicines and `checkinHourIST=11`; a family photo uploaded from `/settings` (signed in as Papa) and holiday mode **off**.
- [ ] **Run `POST /demo/reset` from the guardian pane (the "Reset demo" button on `/demo`, signed in as Priya) before recording**: it stops leftover `Watch`/`Ladder`/`RecoveryCase` executions, closes open demo tasks and clears this browser's local state, so the dashboard starts clean. Confirm in the Step Functions console that no execution is still `Running`.
- [ ] `scripts/seed_demo_screenshots/*.png` on the recording machine (two UPI receipts, WhatsApp CBI, courier SMS, KYC SMS, genuine OTP, injection probe).
- [ ] Sources: `python scripts/verify_sources.py` exits 0 on the recording machine and the terminal font is large enough to read at 1080p.

Tabs open, in this order
- [ ] Tab 1: `/demo` split view, logged in as Papa (left) and Priya (right).
- [ ] Tab 2: Step Functions console, state machines list (`Watch`, `Ladder`, `RecoveryCase`), region ap-south-1.
- [ ] Tab 3: DynamoDB `doosriraay` table, item explorer filtered on the demo `CIRCLE#` PK.
- [ ] Tabs 4–15, in shot-7 order: Amplify app, Cognito user pool users, API Gateway routes + authorizer, Lambda list, Lambda env (`classify-worker`), S3 bucket permissions + lifecycle, ECR repository, SSM Parameter Store entry (if set), CloudWatch Logs (`api` function log group and the `RecoveryCase` state-machine log group), the finished `Ladder` execution's graph view, AWS Budgets (if set), IAM policy of the `api` function (statement `PollyPuchhoClip`).
- [ ] Tab 16: the `/sources` panel in the guardian view. Terminal window sized to half the screen for shot 8.
- [ ] Browser zoom 110%, bookmarks bar hidden, notifications off, account emails other than the demo ones hidden, account id blurred in post if it is visible in the ECR/SSM ARNs.

Push
- [ ] Web Push (VAPID) works on the recording machine's Chrome **or** the guardian view is in the foreground and the voiceover says "push or foreground" as written. Do not claim background buzzing if it is not working on the day.

Content
- [ ] Hook slide numbers match README's table exactly (sources on screen; ₹4,057.7 cr, not ₹4,057 cr).
- [ ] The word "safe" appears nowhere in the UI (`pytest tests -k safe` green).
- [ ] The "SCAM DETECTED" overlay in shot 1 is our own mock.
- [ ] The eval slide (shot 9) matches `eval/results.md`: if that file is still the placeholder, the slide says "eval pending" and shows no numbers.
- [ ] Hindi copy reviewed by a native speaker.
- [ ] The weather card shows the Open-Meteo credit (CC BY 4.0) on camera.

Timing rehearsal
- [ ] Watch deadline (45 s) started *before* recording shot 2 so the ladder fires during shot 3.
- [ ] Case opened *before* shot 6 begins so `Extract` has finished (container cold start).
- [ ] Two full dry runs timed at ≤ 3:05 raw.
