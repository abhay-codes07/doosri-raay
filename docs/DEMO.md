# Demo script (3:00) and pre-flight checklist

Authoritative script: `docs/BUILD_PLAN.md` section 9. This file turns it into a shot list. Record with
OBS in a single browser window: left pane parent tile (seeded "Papa"), right pane guardian dashboard (seeded
"Priya"), the Step Functions console and one DynamoDB item in separate tabs. Voiceover after, cut to 3:00.

## Shot list

| # | Time | Shot | On screen | Voice | Console / notes |
|---|---|---|---|---|---|
| 1 | 0:00–0:20 | Hook slide | Sourced numbers, one per line with the source: ₹22,495 cr lost to cyber fraud in 2025 (MHA); 1,03,488 senior-citizen complaints, ₹4,005 cr (MHA reply in Rajya Sabha, 5 Aug 2026); digital arrest 2,97,727 complaints / ₹4,057 cr since 2022 (govt data via News18, Jul 2026); Karnataka recovery 5% → 2.2% (TOI, Mar 2026). Then a **generic mock** "SCAM DETECTED" red overlay, ours, not another team's. | "Every scam app assumes the victim can act. In the cases we studied, every save came from an outsider. Doosri Raay is the outsider." | Do not show "51% never report". Overlay is a mock we drew. |
| 2 | 0:20–0:35 | Parent tile | Left pane: Papa's Panchang tile: tithi and date, weather, "Amlodipine 08:00 · Metformin 20:00", family photo. Cursor opens it once. | "Papa opens this every morning for the tithi and his medicines. Opening it is the check-in. Nothing else is asked of him, ever." | Amplify URL visible in the address bar (service 1). |
| 3 | 0:35–1:05 | Watch → Ladder | Tab: Step Functions `Watch` execution passes its 45 s demo deadline, `StartLadder`, `Ladder` execution opens at `Rung1GuardianCall`. Right pane: Priya's task "Call Papa now". She taps **No answer**. Rung 2 goes to Rahul; rung 3 shows the neighbour script with Sharma ji's address. Cut to the DynamoDB TASK item for 2 s. | "Today he didn't open it. The watch expires, the ladder starts. Priya calls, no answer, that is the second signal. The neighbour gets a script. Papa's screen never changed, and nothing was recorded." | Step Functions (service 8) at 0:35; DynamoDB (service 6) at 0:50. Left pane must stay unchanged on camera. |
| 4 | 1:05–1:20 | Classifier card | Guardian view: forward the `whatsapp_cbi.png` screenshot → card in **watching/likely** state with tactics listed. Then paste the benign bank OTP → "Koi khatra nahi mila — phir bhi parivaar se poochhein." | "The checker is a minor tool. It never says safe." | The word "safe" must not be on screen. |
| 4b | (+15 s, only if Puchho shipped) | Puchho | Papa taps "koi kehta hai CBI/police/TRAI hai" → Polly Hindi plays the I4C line; Priya's dashboard shows the notification. | "If someone claims to be the police, Papa can hear the official line and his daughter knows in the same second." | Trim shot 6 by 15 s to compensate. |
| 5 | 1:20–2:20 | Recovery case | Priya opens a case for Papa. Uploads `upi_success_1.png` and `upi_success_2.png`. Extracted fields appear beside each image; one UTR flagged invalid, she corrects it and confirms. 1930 script card. NCRP narrative with character count ≥ 200. e-Zero FIR threshold for Maharashtra ("check with 1930"). MRM checklist. Tab: `RecoveryCase` execution waiting at `NCRPFiled`; the 45 s demo timer expires → guardian task appears on the dashboard. | "After a loss, everyone else gives a 1930 button. We run the whole pipeline: extraction validated in code, the NCRP form's real rules, the state's e-Zero FIR threshold, and the refund module most victims never reach. Every step is a callback with a deadline." | S3 upload at 1:40 (service 7), Lambda at 1:45 (service 4), Bedrock model id at 1:50 (service 5), Step Functions again at 2:05. |
| 6 | 2:20–2:45 | Console tour, 3 s each | Amplify app page → Cognito user pool with the four seeded users → API Gateway routes with the JWT authorizer → Lambda function list → Lambda env showing `MODEL_ID=global.anthropic.claude-sonnet-4-6` and the fallback → S3 bucket with Block Public Access on and the 7-day lifecycle rule. | "Eight services, each one you just saw doing work." | Cognito and API Gateway at 2:40 (services 2 and 3). DynamoDB and Step Functions were already shown. |
| 7 | 2:45–3:00 | Close | Eval table from `eval/results.md` (summary row). Prior-art slide: Kavach, Rakshak, SwarVed and the four gaps. Roadmap: bank-counter copilot, Khyaal/Emoha distribution. | "Seventy-item Hindi and English eval with benign controls, numbers in the README. What we learned: build the outsider." | End card: repo URL, live URL. |

Voice total is about 140 words per minute; rehearse twice on Sunday morning, then record.

## Pre-flight checklist (run in order, tick each)

Environment
- [ ] `make deploy` finished green on the demo stack; `DEMO_TIMEOUTS=1` and `DEMO_SEED_ENABLED=1` are set on the API Lambda (`GET /demo/config` returns `"demoTimeouts": true`, 45 s rungs).
- [ ] `MODEL_ID` is `global.anthropic.claude-sonnet-4-6`; the Haiku fallback smoke-tested from ap-south-1 today.
- [ ] Amplify Hosting shows the latest build; `/demo` route loads at the live URL.

Seed
- [ ] `python scripts/seed.py --user-pool-id ... --client-id ... --api-url ...` ran; summary table shows all four users and the circle; password stored in the team vault, not in the repo.
- [ ] Papa's profile has the neighbour, code word, medicines and `checkinHourIST=11`.
- [ ] Any leftover `Watch`/`Ladder`/`RecoveryCase` executions from rehearsal stopped, and open demo tasks completed, so the dashboard starts clean.
- [ ] `scripts/seed_demo_screenshots/*.png` on the recording machine (two UPI receipts, WhatsApp CBI, courier SMS, KYC SMS, genuine OTP, injection probe).

Tabs open, in this order
- [ ] Tab 1: `/demo` split view, logged in as Papa (left) and Priya (right).
- [ ] Tab 2: Step Functions console, state machines list (`Watch`, `Ladder`, `RecoveryCase`), region ap-south-1.
- [ ] Tab 3: DynamoDB `doosriraay` table, item explorer filtered on the demo `CIRCLE#` PK.
- [ ] Tabs 4–9: Amplify app, Cognito user pool users, API Gateway routes + authorizer, Lambda list, Lambda env (classify-worker), S3 bucket permissions + lifecycle.
- [ ] Browser zoom 110%, bookmarks bar hidden, notifications off, account emails other than the demo ones hidden.

Push
- [ ] Web Push (VAPID) works on the recording machine's Chrome **or** the guardian view is in the foreground and the voiceover says "push or foreground" as written. Do not claim background buzzing if it is not shipped.

Content
- [ ] Hook slide numbers match README's table exactly (sources on screen).
- [ ] The word "safe" appears nowhere in the UI (`pytest tests -k safe` green).
- [ ] The "SCAM DETECTED" overlay in shot 1 is our own mock.
- [ ] Hindi copy reviewed by a native speaker.

Timing rehearsal
- [ ] Watch deadline (45 s) started *before* recording shot 2 so the ladder fires during shot 3.
- [ ] Case opened *before* shot 5 begins so `Extract` has finished (container cold start).
- [ ] Two full dry runs timed at ≤ 3:05 raw.
