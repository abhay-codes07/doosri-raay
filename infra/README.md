# Doosri Raay infrastructure

Everything in this folder is deployed by one AWS SAM stack (`infra/template.yaml`) into **ap-south-1**:

| Resource | Purpose |
|---|---|
| DynamoDB table (`Table`) | single table from `docs/DATA_MODEL.md`: PK/SK, GSI1, TTL on `ttl`, PITR on |
| S3 bucket (`UploadBucket`) | screenshots via presigned POST; public access blocked, SSE-S3, CORS only for `AppOrigins`, `circles/` expires after 7 days, TLS-only bucket policy |
| Cognito (`UserPool`, `UserPoolClient`) | e-mail sign-in, no client secret, SRP + USER_PASSWORD + refresh flows, 1 h tokens / 30 d refresh |
| HTTP API (`HttpApi`) | every route from `docs/API.md` on one `ApiFunction`, JWT authorizer `CognitoJwt` as default, 5 rps / burst 10 |
| Lambda | `ApiFunction`, `ClassifyWorkerFunction`, `LadderTaskFunction`, `WatchCheckFunction`, `LadderStatusFunction` (zip, python3.12, x86_64) and `RecoveryAgentFunction` (container image, Strands) |
| Step Functions (Standard) | `WatchStateMachine`, `LadderStateMachine`, `RecoveryStateMachine` from `infra/statemachines/*.asl.json`, logging level ERROR without execution data (task tokens / transactions stay out of CloudWatch), 14-day log groups |
| SSM parameter | `/doosriraay/<stack>/vapid-private-key` placeholder (see VAPID below) |
| AWS Budgets | USD 20 and USD 50 monthly ACTUAL-cost alerts, created only when `BudgetEmail` is set |

The template uses only long-form intrinsics (`Fn::Sub`, `Ref`, `Fn::GetAtt`) so plain YAML parsers and `infra/validate_asl.py` can read it.

## Prerequisites

- An AWS account on a **paid plan** with **Amazon Bedrock model access for Anthropic Claude enabled in ap-south-1** (the stack uses the *global* inference profiles `global.anthropic.claude-sonnet-4-6` and `global.anthropic.claude-haiku-4-5-20251001-v1:0`; enable Claude Sonnet 4.6 and Claude Haiku 4.5 under Bedrock -> Model access). Test once with `aws bedrock-runtime converse --model-id global.anthropic.claude-sonnet-4-6 --messages '[{"role":"user","content":[{"text":"hi"}]}]' --region ap-south-1`.
- AWS CLI v2 configured (`aws configure`) with a user/role that can create IAM roles.
- AWS SAM CLI >= 1.100 (`pip install aws-sam-cli` or the installer).
- Docker Desktop running (`sam build --use-container` builds the Python functions in the x86_64 Lambda build image; the recovery agent is a container image).
- Node 20 (`frontend/`), Python 3.10+ (`scripts/`, `eval/`, tests), GNU make (Git Bash on Windows works).

## One-command deploy

```bash
cp samconfig.example.toml samconfig.toml     # edit parameter_overrides if you like (it is git-ignored)
make validate                                # sam validate --lint + python infra/validate_asl.py
make deploy                                  # sam build --use-container && sam deploy
make outputs                                 # ApiUrl, UserPoolId, UserPoolClientId, ... as a table
```

First time without a `samconfig.toml`: `make deploy-guided` walks through stack name (`doosriraay`), region (`ap-south-1`), parameters, and writes the file. Answer **Y** to "create managed ECR repositories" so the recovery-agent image has somewhere to go.

Override parameters on the fly: `make deploy PARAMS='AppOrigins=https://main.d1234.amplifyapp.com,http://localhost:5173 BudgetEmail=team@example.com'` (a CommaDelimitedList parameter is passed as one comma-separated value, no spaces).

Stack parameters (all have defaults): `AppOrigins` (comma-separated list), `ModelId`, `FallbackModelId`, `BedrockRegion`, `DemoTimeouts` (0/1), `DemoSeedEnabled` (0/1), `DailyQuota`, `VapidPublicKey`, `VapidSubject`, `BudgetEmail`, `PollyVoiceId`.

Build notes:
- All zip functions share `CodeUri: ../backend/` and one `backend/requirements.txt` on purpose (one build, one layer of deps).
- `RecoveryAgentFunction` builds `backend/recovery_agent/Dockerfile` with context `backend/`, tag `v1`, platform `linux/amd64` (all functions are x86_64 so no QEMU emulation is needed on x86 laptops). Verified locally with `docker build --platform linux/amd64 -f recovery_agent/Dockerfile backend/`. Base image is `public.ecr.aws/lambda/python:3.12`.

## Web Push (VAPID)

CloudFormation cannot create a `SecureString`, so the stack creates a `String` placeholder `REPLACE_ME` and the code reads it with `WithDecryption=True` (works for both types).

```bash
npx web-push generate-vapid-keys          # prints Public Key and Private Key
make set-vapid VAPID_PRIVATE_KEY='<private key>'   # aws ssm put-parameter --type SecureString --overwrite
make deploy PARAMS='VapidPublicKey=<public key> VapidSubject=mailto:you@example.com'
```

Only the public key is a stack parameter (it is also served by `GET /push/public-key`); the private key never enters the repo or the template. Push is best-effort: without keys the Lambdas skip sending and the guardian view polls instead.

## Frontend on Amplify Hosting

1. Deploy the backend once (above) and note the outputs.
2. Amplify console -> **Create new app** -> **GitHub** -> pick this repo and branch. Set **App root / monorepo root** to `frontend` (build command `npm ci && npm run build`, output `dist`).
3. Environment variables (App settings -> Environment variables):

   | Variable | Value |
   |---|---|
   | `VITE_API_URL` | output `ApiUrl` (no trailing slash) |
   | `VITE_USER_POOL_ID` | output `UserPoolId` |
   | `VITE_USER_POOL_CLIENT_ID` | output `UserPoolClientId` |
   | `VITE_REGION` | `ap-south-1` |
   | `VITE_VAPID_PUBLIC_KEY` | the VAPID public key |

4. Add a rewrite rule for the SPA/PWA: source `</^[^.]+$|\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json|webmanifest)$)([^.]+$)/>` -> target `/index.html`, type `200 (Rewrite)`.
5. After the first Amplify build, copy its URL (e.g. `https://main.d1234abcd.amplifyapp.com`) and **redeploy the backend with that origin** so API Gateway and S3 CORS accept it:

   ```bash
   make deploy PARAMS='AppOrigins=https://main.d1234abcd.amplifyapp.com,http://localhost:5173'
   ```

   `AppOrigins` is a comma-separated list (default `http://localhost:5173,http://localhost:4173`, i.e. `vite dev` and `vite preview`). API Gateway and the S3 bucket accept every entry; the API reads the same list from `APP_ORIGINS` and echoes the matching request `Origin` (`APP_ORIGIN`, the first entry, is kept for backward compatibility). Keep the localhost entries in the list if you develop against the deployed API, or run two stacks (`--stack-name doosriraay-dev`).

## Cognito for the demo

- The app client already allows `ALLOW_USER_PASSWORD_AUTH`, `ALLOW_USER_SRP_AUTH` and `ALLOW_REFRESH_TOKEN_AUTH`. The PWA uses SRP; `scripts/seed.py` and judges' curl scripts can use the simpler password flow:

  ```bash
  aws cognito-idp initiate-auth --region ap-south-1 --auth-flow USER_PASSWORD_AUTH \
    --client-id <UserPoolClientId> --auth-parameters USERNAME=papa@example.com,PASSWORD='<pw>' \
    --query AuthenticationResult.IdToken --output text
  ```

  Send the **ID token** as `Authorization: Bearer <token>` (the authorizer's audience is the app client id, which only the ID token carries).
- Seeded users are created with the admin API by `make seed` (`AdminCreateUser` + `AdminSetUserPassword --permanent`), so no e-mail verification is needed for the demo.
- `POST /demo/seed` is only served when `DemoSeedEnabled=1`; set it to `0` (and `DemoTimeouts=0`) for anything beyond the hackathon demo, and rotate the seeded passwords after judging.

## Contracts the state machines assume from the backend

- `ladder-task` payload: `{kind, rung?, assigneeRole, circleId, parentSub?, caseId?, reason?, wait, taskToken?, attempt?, reminder?, escalation?}`. `wait:true` states use `.waitForTaskToken`; `wait:false` states (rung 4 emergency, 1930 / NCRP escalations, confirm-fields reminder) are plain invokes and the task is informational.
- `ladder-status` payload: `{ladderState: watching|escalated|ok, closeOpenTasks: bool, circleId, parentSub, reason}`.
- `watch-check` payload `{circleId, parentSub, startedAt, deadline}` -> `{checkedIn: bool, holidayMode: bool}`.
- `recovery-agent` payload `{action: extract|build|mrm|finalize|fail, circleId, caseId, error?}`; `mrm` must return `{eligible, firRequired, checklist}` in the Lambda result (the Choice reads `$.mrm.Payload.eligible`). The agent reads confirmed transactions and the NCRP ack number from the CASE item, so `POST /tasks/{id}/complete` must persist `txns` / `ackNo` there before calling `SendTaskSuccess`.
- Task outcomes read by Choice states: ladder rungs `outcome == "reached"`; `Call1930` `outcome == "done"`; everything else is treated as "move to the next rung / escalate".

## Cost guards

- API Gateway stage throttle 5 rps / burst 10 (`DefaultRouteSettings`).
- Per-user daily LLM quota `DailyQuota` (default 30) enforced in the API on `/analyze`, `/cases`, `/puchho`.
- Presigned POST capped at 5 MB, `image/*` only; screenshots expire after 7 days.
- Bedrock `max_tokens` capped in code; Haiku fallback on throttling.
- AWS Budgets: pass `BudgetEmail=you@example.com` to create the USD 20 and USD 50 monthly alerts (confirm the SNS/e-mail subscription that AWS sends). Budgets is a global service; the resources are created from ap-south-1 without any extra setup.
- Standard Step Functions executions cost per transition, not per second of waiting, so a 24 h `Wait` is effectively free. Log groups keep 14 days.

## Teardown

```bash
make teardown            # sam delete --stack-name doosriraay --no-prompts
```

Before that, empty the upload bucket if you want the bucket itself gone (`aws s3 rm s3://<UploadBucket> --recursive`); CloudFormation refuses to delete a non-empty bucket. The SAM-managed artifact bucket and the ECR repository are deleted by `sam delete` as well. If you overwrote the VAPID SSM parameter as a SecureString, `sam delete` still removes it (same name). Delete the Amplify app from its console.

## Validation without AWS

```bash
make validate
# or individually
sam validate --lint --template infra/template.yaml
python infra/validate_asl.py
```

`validate_asl.py` checks every `Next`/`Default`/`Catch` target exists, exactly one `StartAt`, terminal states, reachability, that every `waitForTaskToken` state passes `$$.Task.Token`, and that every `${Placeholder}` in the ASL files matches a `DefinitionSubstitutions` entry in the template (and vice versa).
