# Rajat: what you have to do (deploy, seed, record, submit)

Everything in this repo is built and tested locally: 230 backend tests, clean frontend build, validated SAM template, sources verified against the live government sites. **Nothing is deployed yet**, because the machine it was built on had no AWS credentials. That part is yours. Follow this file top to bottom; every command is copy-paste. Budget about 2 hours for deploy + seed, 1 hour to record, 30 minutes to submit.

Repo: https://github.com/abhay-codes07/doosri-raay (private). Docs you will use: `infra/README.md` (deploy detail), `docs/DEMO.md` (shot list and pre-flight), `docs/SUBMISSION.md` (form answers), `README.md` (judge-facing).

---

## 0. Install on your laptop (once)

| Tool | Get it | Check |
|---|---|---|
| Git | git-scm.com | `git --version` |
| Python 3.12 | python.org (tick "Add to PATH") | `python --version` |
| Node 22 | nodejs.org LTS | `node --version` → v22.x |
| Docker Desktop | docker.com, then start it | `docker info` prints without error |
| AWS CLI v2 | https://awscli.amazonaws.com/AWSCLIV2.msi (Windows) or `brew install awscli` | `aws --version` |
| AWS SAM CLI | https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html | `sam --version` |
| GNU make | Windows: `winget install GnuWin32.Make` or use Git Bash with `mingw32-make`; macOS/Linux: preinstalled | `make --version` |

```bash
git clone https://github.com/abhay-codes07/doosri-raay.git
cd doosri-raay
pip install -r backend/requirements.txt pytest moto
python -m pytest -q          # must print "230 passed" (takes ~4 min)
cd frontend && npm ci && npm run build && cd ..
```

If the tests do not pass on your machine, stop and message Abhay before deploying.

---

## 1. AWS account and credentials (you need to FILL these)

Use the **Paid-plan** AWS account for the hackathon (Free-plan accounts get near-zero Bedrock quota). In the AWS console:

1. IAM → Users → Create user `doosriraay-deployer` → Attach policy `AdministratorAccess` (hackathon only; delete the user after judging) → Create access key → "CLI".
2. On your laptop:
   ```bash
   aws configure
   # AWS Access Key ID:     <paste>
   # AWS Secret Access Key: <paste>
   # Default region name:   ap-south-1
   # Default output format: json
   aws sts get-caller-identity     # must print your account id
   ```
3. **Bedrock model access (critical).** Console → Amazon Bedrock → region **ap-south-1** → Model access → Enable **Anthropic Claude Sonnet 4.6** and **Anthropic Claude Haiku 4.5** (accept the Marketplace terms; both are needed, Haiku is the fallback). Then check:
   ```bash
   aws bedrock list-foundation-models --region ap-south-1 --by-provider anthropic --query "modelSummaries[].modelId"
   ```
   If this errors with access denied, the deploy will succeed but every classification will fail. Fix access first.

---

## 2. Web Push keys (2 minutes)

```bash
npx web-push generate-vapid-keys
```
Save both keys somewhere private. You will paste the **public** key into `samconfig.toml` and Amplify, and the **private** key into SSM in step 5.

---

## 3. Deploy configuration (FILL the values)

```bash
cp samconfig.example.toml samconfig.toml
```
Open `samconfig.toml` and set `parameter_overrides` to exactly this (one line, no spaces inside the AppOrigins list):

```
parameter_overrides = "AppOrigins=http://localhost:5173,http://localhost:4173 BudgetEmail=<YOUR_EMAIL> VapidPublicKey=<PUBLIC_KEY_FROM_STEP_2> VapidSubject=mailto:<YOUR_EMAIL> DemoTimeouts=1 DemoSeedEnabled=0 DailyQuota=200 ModelId=global.anthropic.claude-sonnet-4-6 FallbackModelId=global.anthropic.claude-haiku-4-5-20251001-v1:0"
```

`DemoTimeouts=1` makes the watch and ladder fire in 45 seconds (needed for the video and for judges). `DailyQuota=200` so judges cannot exhaust it. `BudgetEmail` gives you the USD 20 / USD 50 cost alarms; confirm the SNS subscription e-mail AWS sends you.

---

## 4. First deploy (15–20 minutes)

Docker Desktop must be running.

```bash
make image-check     # builds the recovery-agent image locally and checks Lambda will accept it
make deploy          # sam build --use-container, then sam deploy
```

If `make` is missing on Windows Git Bash: `mingw32-make SHELL=sh deploy`. If `sam` is not on PATH: `make deploy SAM=/full/path/to/sam.exe`.

What "good" looks like: CloudFormation prints `CREATE_COMPLETE` for stack `doosriraay` and a list of Outputs (`ApiUrl`, `UserPoolId`, `UserPoolClientId`, `UploadBucket`, the three state machine ARNs). Save them:

```bash
make outputs
```

If it fails: console → CloudFormation → stack `doosriraay` → Events → the first `CREATE_FAILED` line is the cause. Known ones: "Image not found" (run `make image-check`, make sure Docker is running); Bedrock access errors appear only at runtime, not at deploy.

---

## 5. Push private key into SSM (1 minute)

```bash
make set-vapid VAPID_PRIVATE_KEY=<PRIVATE_KEY_FROM_STEP_2>
```
Verify in console → Systems Manager → Parameter Store → `/doosriraay/doosriraay/vapid-private-key` shows Type **SecureString**.

---

## 6. Seed the demo users and judge circles (2 minutes)

```bash
export DEMO_PASSWORD='<PICK_A_STRONG_PASSWORD>'    # Windows PowerShell: $env:DEMO_PASSWORD='...'
make seed
```
This creates in Cognito and in the app:

| Purpose | Emails | Role |
|---|---|---|
| Recording circle "Sharma family" | papa@demo.doosriraay.in, priya@…, rahul@…, aman@… | parent, guardian1, guardian2, son |
| Judge circle 1 | judge1@demo.doosriraay.in, judge1-papa@…, judge1-guardian2@…, judge1-son@… | same |
| Judge circle 2 | judge2@…, judge2-papa@… … | same |
| Judge circle 3 | judge3@…, judge3-papa@… … | same |

All share `DEMO_PASSWORD`. **Write it in the submission form's "judge access" field, never in the repo.** Papa's profile is pre-filled (Pune, Maharashtra, neighbour Verma ji, code word "gulab jamun", 4 medicines, check-in hour 11, pact accepted).

---

## 7. Frontend: run locally first, then host on Amplify

```bash
make env            # writes frontend/.env.local from the stack outputs
```
Open `frontend/.env.local` and ADD these lines (fill the password):

```
VITE_VAPID_PUBLIC_KEY=<PUBLIC_KEY_FROM_STEP_2>
VITE_DEMO_PARENT_EMAIL=papa@demo.doosriraay.in
VITE_JUDGE_EMAIL=judge1@demo.doosriraay.in
VITE_JUDGE_PASSWORD=<DEMO_PASSWORD>
VITE_JUDGE_PARENT_EMAIL=judge1-papa@demo.doosriraay.in
VITE_JUDGE_PARENT_PASSWORD=<DEMO_PASSWORD>
```

```bash
cd frontend && npm run dev
```
Open http://localhost:5173/try — it must land you in the judge circle with **no sign-in**. Do the smoke test in section 9 here before touching Amplify.

**Amplify Hosting** (console → AWS Amplify → Create new app → GitHub):
1. Authorise GitHub, pick `abhay-codes07/doosri-raay`, branch `main`.
2. App settings: **Monorepo / app root = `frontend`**. Build settings come from `amplify.yml` automatically.
3. Environment variables: add every `VITE_*` line from your `.env.local` (VITE_API_URL, VITE_USER_POOL_ID, VITE_USER_POOL_CLIENT_ID, VITE_REGION=ap-south-1, and the six above).
4. Save and deploy. Copy the URL, e.g. `https://main.d1abc2def3.amplifyapp.com`.
5. App settings → Rewrites and redirects → add rule: Source `</^[^.]+$|\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json|webmanifest)$)([^.]+$)/>` Target `/index.html` Type `200 (Rewrite)`. Without this, refreshing `/try` gives a 404.

Then tell the backend about the new origin:

```bash
make deploy PARAMS="AppOrigins=https://main.d1abc2def3.amplifyapp.com,http://localhost:5173"
```
(keep all the other parameters from `samconfig.toml`; PARAMS only overrides these.)

---

## 8. Two more one-time commands

```bash
python scripts/verify_sources.py --s3      # uploads the hashed government sources to S3; the app's "Sources verified" panel then reads the live manifest
python eval/run_eval.py --fallback         # runs the 70-item eval against the real Bedrock models (~10 min, ~USD 1); writes eval/results.md
git add eval/results.md docs/sources-manifest.json && git commit -m "eval: model run on judge stack; sources manifest refreshed" && git push
```
Then open `README.md`, find the "Eval status" section and replace the "no model numbers yet" sentence with the summary row from `eval/results.md`.

---

## 9. Smoke test (do this on the live URL before recording)

1. Private window → `<AMPLIFY_URL>/try` → judge FAQ visible, Papa's tile on the left, dashboard on the right. Press **Reset demo**.
2. Click Papa's tile once (that is the check-in). Open Step Functions console (ap-south-1) → `Watch` execution is Running.
3. Wait ~45 s without touching the tile → `Ladder` execution starts → right pane shows "Call Papa now" → tap **No answer** → rung 2 → rung 3 shows the neighbour script.
4. Right pane → screenshot check → upload `scripts/seed_demo_screenshots/whatsapp_cbi.png` → verdict card in amber/red within ~10 s. Paste the bank OTP text → grey "Koi khatra nahi mila — phir bhi parivaar se poochhein."
5. Left pane → "koi kehta hai police/CBI/bank" → the Hindi audio plays (Polly) and a task appears on the right.
6. Right pane → Open a case → upload `upi_success_1.png` and `upi_success_2.png` → within ~40 s the extracted rows appear beside the images → confirm → 1930 script, NCRP narrative, e-Zero FIR note, MRM checklist, each with a "Source" line.
7. Right pane → "Sources verified" panel lists 13 sources with hashes.
8. Enable alerts button → allow notifications → (optional) confirm a push arrives on the next task.

If any step fails, check CloudWatch Logs for the `api` or `classify-worker` function first; a `model_unavailable` error means Bedrock access (step 1.3).

---

## 10. Record the video (3:00, unlisted YouTube)

Full shot list and pre-flight checklist: `docs/DEMO.md`. Do the pre-flight checklist in order; it takes 20 minutes and saves a re-shoot. Condensed script:

| Time | Show | Say |
|---|---|---|
| 0:00–0:18 | Hook slide with the sourced numbers, then our own mock "SCAM DETECTED" overlay | "Every scam app assumes the victim can act. In the twenty-five cases we studied, every save came from an outsider: a bank manager, a daughter, a neighbour. Doosri Raay is the outsider." |
| 0:18–0:33 | Papa's tile (tithi, weather with Open-Meteo credit, medicines, family photo); click it once | "Papa opens this every morning for the tithi and his medicines. Opening it is the check-in. Nothing else is asked of him, ever, and there is no warning on this screen for a scammer to see." |
| 0:33–1:03 | Step Functions: Watch expires, Ladder starts; Priya taps No answer; rung 2, rung 3 neighbour script; 2 s on the DynamoDB task item | "Today he didn't open it. The watch expires and starts the ladder. Priya calls, no answer: that is the second signal. Rahul, then the neighbour with a script and the address, then 112 guidance. Papa's screen never changed, and nothing was recorded. Every rung is a Step Functions task token with a deadline." |
| 1:03–1:15 | Classifier: CBI screenshot → watching/likely; bank OTP → grey card | "The checker is a minor tool: one Bedrock call, forced to answer through a tool schema, three states. It never says safe." |
| 1:15–1:27 | Puchho: Papa taps the police/CBI button, Hindi clip plays, Priya's task appears | "If someone claims to be the police, Papa can hear the official I4C line in Hindi, and his daughter knows in the same second." |
| 1:27–2:05 | Recovery: two UPI screenshots, fields beside images, one UTR corrected, 1930 script, NCRP narrative with source line, e-Zero FIR, MRM; Step Functions waiting at NCRPFiled, timer expires into a guardian task | "After a loss, everyone else gives a 1930 button. We run the whole pipeline: extraction validated in code and confirmed beside the image, the NCRP form's real rules, the state's e-Zero FIR threshold, and the refund module most victims never reach. The thresholds and rules are data files, not prompts. Every step is a callback with a deadline." |
| 2:05–2:29 | Console tour, 2 s each: Amplify, Cognito users, API Gateway routes + JWT authorizer, Lambda list, Lambda env with MODEL_ID, S3 bucket (Block Public Access, lifecycle), ECR image, SSM SecureString, CloudWatch log groups, X-Ray trace map, Budgets alarms, IAM statement PollyPuchhoClip | "One SAM stack. Nine services doing product work, five for operations, and you saw them doing it: hosting, identity, the API, the Lambdas, Bedrock, the bucket, the container registry, the secret, the logs, the trace, the cost alarm and the voice." |
| 2:29–2:49 | Terminal: `python scripts/verify_sources.py` output; then the Sources panel in the app | "Every number and rule the app shows comes from a source we snapshot and hash. This command re-verifies the snapshot, and the app shows the same hash beside the fact. If the source changes, the check fails before a judge sees a stale threshold." |
| 2:49–3:00 | Eval slide (numbers from eval/results.md), prior art line, end card with repo + `/try` URL | "A seventy-item Hindi and English test set with benign controls, run against Bedrock; the numbers are in the README. What we learned: build the outsider." |

Timing tricks: click Papa's tile ~40 s before you start recording shot 3 so the ladder fires on cue; open the case before shot 6 so extraction is already done; press Reset demo between takes.

Upload to YouTube as **unlisted**, copy the link.

---

## 11. Fill the placeholders and push

```bash
grep -rn "FILL BEFORE SUBMISSION\|<AMPLIFY_URL>\|<YOUTUBE_URL>\|<NAME>" README.md docs/SUBMISSION.md docs/BLOG.md
```
Replace every one: live URL (`<AMPLIFY_URL>/try`), YouTube link, four team names with roles, Builder Center verification line, credential rotation date (set it AFTER judging closes). Add any tool you used for the video (OBS, editor, voice) to `docs/AI_TOOLS.md`. Then:

```bash
git add -A && git commit -m "docs: submission links, team, eval numbers" && git push
```
Every teammate should push at least one commit before submitting (the rules judge the git history). Also make sure every teammate's student status is verified on AWS Builder Center or the entry is not scored.

---

## 12. Submit

Form: https://wemakedevs.org/aws/first-commit/submit. Paste from `docs/SUBMISSION.md` section by section: idea, problem, what it does, live demo (`/try`, no sign-up, plus the judge password), video link, AWS services and how each is used, feedback on AWS, team split, AI tools. Tick Ship It (one submission is considered for all tracks).

Optional for the keyboard prize: publish `docs/BLOG.md` (fix the four status notes at its top first) and link it in the form.

---

## 13. After judging

```bash
python scripts/seed.py --rotate --user-pool-id <UserPoolId> --client-id <ClientId> --api-url <ApiUrl>   # new passwords for every demo user
make deploy PARAMS="DemoTimeouts=0"     # or: make teardown  (deletes the stack)
```
Delete the `doosriraay-deployer` IAM user. Empty and delete the S3 bucket if you tear down.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Classifier card says "model unavailable" | Bedrock model access not enabled, or Free-plan account | Step 1.3; check CloudWatch Logs of `classify-worker` |
| `/try` shows "not configured" | `VITE_JUDGE_*` env missing in Amplify | Step 7.3, redeploy the Amplify branch |
| Browser console shows CORS error | Amplify URL not in `AppOrigins` | Step 7 last command |
| Refreshing `/try` gives 404 | Missing SPA rewrite rule | Step 7.5 |
| Ladder never starts | Papa's tile was not opened (no check-in) or holiday mode on | Click the tile; `/settings` holiday off; Reset demo |
| Case stuck at "Extracting" > 2 min | Recovery-agent container cold start or Bedrock throttled | Wait; check `recovery-agent` logs; retry |
| No push notification | VAPID private key not in SSM, or browser blocked | Step 5; the demo is fine in the foreground |
| `sam deploy` says image not found | Ran `sam deploy --template ...` by hand | Use `make deploy` (it deploys the built template) |
| Cost worry | Everything is pay-per-use; judges are quota-capped | Budget alarms at USD 20 and 50 go to your e-mail |

Realistic total cost for the weekend: a few dollars (Bedrock calls dominate; Sonnet vision extraction is the biggest item).
