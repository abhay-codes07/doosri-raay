# Doosri Raay - top-level developer commands.
# Run from Git Bash on Windows (GNU make + sh) or any POSIX shell. No bashisms beyond `&&` / `||`.
#
#   make validate        lint the SAM template and the Step Functions definitions (no AWS calls)
#   make build           sam build --use-container --cached --parallel (BUILDX_NO_DEFAULT_ATTESTATIONS=1)
#   make deploy          build + sam deploy; extra params: make deploy PARAMS="AppOrigins=... BudgetEmail=..."
#   make deploy-guided   first-time interactive deploy that writes samconfig.toml
#   make outputs         print the stack outputs as a table
#   make env             write frontend/.env.local (VITE_API_URL, VITE_USER_POOL_ID, ...) from the stack outputs
#   make seed            python scripts/seed.py with --user-pool-id/--client-id/--api-url/--region from the outputs
#   make image-check     docker build the recovery-agent image for linux/amd64 and verify Lambda will accept it
#   make set-vapid       VAPID_PRIVATE_KEY=... overwrite the SSM placeholder as a SecureString
#   make local-up        docker compose up -d --wait (LocalStack: S3 + DynamoDB on 127.0.0.1:4566)
#   make local-bootstrap python scripts/localstack_bootstrap.py (creates the local table + bucket)
#   make local-api       sam build + sam local start-api with infra/local-env.json on the compose network
#   make local-down      docker compose down -v
#   make eval / test / frontend-dev / frontend-build / teardown / logs-api

SAM      ?= sam
PYTHON   ?= python
AWS      ?= aws
NPM      ?= npm
DOCKER   ?= docker
STACK    ?= doosriraay
REGION   ?= ap-south-1
TEMPLATE := infra/template.yaml
# Optional extra CloudFormation parameters for `make deploy`, space separated Key=Value pairs.
# A CommaDelimitedList value (AppOrigins) is one comma-separated token without spaces, e.g.
#   make deploy PARAMS="AppOrigins=https://main.xxxx.amplifyapp.com,http://localhost:5173 BudgetEmail=you@example.com DemoTimeouts=1"
PARAMS   ?=
# Extra arguments for scripts/seed.py, e.g. make seed SEED_ARGS="--password 'Demo#1234' --invite-code ABCD"
SEED_ARGS ?=
# Local tag used by `make image-check` (sam build tags its own copy of the same Dockerfile).
IMAGE_TAG ?= doosriraay-recovery-agent:check
# --- local mode (infra/README.md -> "Run it locally") -----------------------------------------
COMPOSE       ?= $(DOCKER) compose
# Docker network the Lambda containers join so `http://localstack:4566` (infra/local-env.json)
# resolves. `doosriraay_default` is what docker-compose.yml (name: doosriraay) creates and works
# on Docker Desktop and Linux alike. On Linux you may instead use LOCAL_NETWORK=host together with
# AWS_ENDPOINT_URL=http://localhost:4566 in the env file.
LOCAL_NETWORK ?= doosriraay_default
LOCAL_ENV     ?= infra/local-env.json
LOCAL_PORT    ?= 3000
# Host-side endpoint for scripts that talk to LocalStack from this machine (not from a container).
LOCAL_ENDPOINT ?= http://localhost:4566

# Stack outputs as eval-able KEY='VALUE' lines (infra/outputs.py wraps `sam list stack-outputs --output json`).
OUTPUTS   = $(PYTHON) infra/outputs.py --stack-name $(STACK) --region $(REGION) --sam "$(SAM)"

.PHONY: help validate build deploy deploy-guided outputs env seed image-check set-vapid local-up local-bootstrap local-api local-down eval test frontend-dev frontend-build teardown logs-api

help:
	@echo "Targets: validate build deploy deploy-guided outputs env seed image-check set-vapid local-up local-bootstrap local-api local-down eval test frontend-dev frontend-build teardown logs-api"

# --- infrastructure ---------------------------------------------------------------------------

validate:
	-$(SAM) validate --lint --template $(TEMPLATE) --region $(REGION) || echo "sam validate skipped or failed (is the AWS SAM CLI installed?)"
	$(PYTHON) infra/validate_asl.py

# BuildKit attaches provenance/SBOM attestations by default, which turns the pushed recovery-agent
# image into a multi-manifest OCI index that Lambda rejects. Disable them for every image build.
build deploy deploy-guided image-check local-api: export BUILDX_NO_DEFAULT_ATTESTATIONS = 1

build:
	$(SAM) build --use-container --cached --parallel --template $(TEMPLATE)

# No --template on `sam deploy`: SAM must read .aws-sam/build/template.yaml (the built copy carries
# the packaged CodeUri / ImageUri for RecoveryAgentFunction) and write samconfig.toml at the repo
# root. Passing the source template here makes `sam deploy` fail with a missing ImageUri.
deploy: build
	$(SAM) deploy --no-fail-on-empty-changeset --region $(REGION) $(if $(PARAMS),--parameter-overrides $(PARAMS),)

deploy-guided: build
	$(SAM) deploy --guided --region $(REGION)

outputs:
	$(SAM) list stack-outputs --stack-name $(STACK) --region $(REGION) --output table

# frontend/.env.local is git-ignored; other keys already in it (VITE_VAPID_PUBLIC_KEY, ...) are kept.
env:
	$(OUTPUTS) --vite frontend/.env.local

# Build the same Dockerfile sam uses, then check Architecture/Os and the manifest type.
image-check:
	$(DOCKER) build --platform linux/amd64 -t $(IMAGE_TAG) -f backend/recovery_agent/Dockerfile backend
	$(DOCKER) image inspect $(IMAGE_TAG) --format '{{.Os}}/{{.Architecture}}'
	$(PYTHON) infra/image_check.py $(IMAGE_TAG)

# `npx web-push generate-vapid-keys` prints both keys; pass the private one here and the public
# one as the VapidPublicKey stack parameter (make deploy PARAMS='VapidPublicKey=...').
set-vapid:
	@test -n "$(VAPID_PRIVATE_KEY)" || (echo "usage: make set-vapid VAPID_PRIVATE_KEY=<base64url private key>" && exit 1)
	$(AWS) ssm put-parameter --region $(REGION) --name /doosriraay/$(STACK)/vapid-private-key --type SecureString --overwrite --value "$(VAPID_PRIVATE_KEY)"

teardown:
	$(SAM) delete --stack-name $(STACK) --region $(REGION) --no-prompts

logs-api:
	$(SAM) logs --stack-name $(STACK) --region $(REGION) --name ApiFunction --tail

# --- local mode: LocalStack (S3 + DynamoDB) + sam local start-api -----------------------------
# Bedrock, Polly and Step Functions are not in LocalStack community, so this covers the API,
# DynamoDB and S3 routes only; see infra/README.md -> "Run it locally" for what works.

local-up:
	$(COMPOSE) up -d --wait

# The bootstrap script talks to LocalStack from the host, so it gets the host-side endpoint and the
# dummy credentials LocalStack accepts; the names match infra/local-env.json.
local-bootstrap:
	AWS_ENDPOINT_URL=$(LOCAL_ENDPOINT) AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=$(REGION) 	  TABLE_NAME=doosriraay-local UPLOAD_BUCKET=doosriraay-local $(PYTHON) scripts/localstack_bootstrap.py

# No --template here either: sam local must read .aws-sam/build/template.yaml (built deps), not the
# source tree. --env-vars can only override variables the template declares (AWS_ENDPOINT_URL and
# LOCAL_STUB_SFN are declared empty / "0" for exactly this reason).
local-api: build
	$(SAM) local start-api --env-vars $(LOCAL_ENV) --docker-network $(LOCAL_NETWORK) --port $(LOCAL_PORT) --warm-containers EAGER --region $(REGION)

local-down:
	$(COMPOSE) down -v

# --- data / evaluation / tests ----------------------------------------------------------------

# Reads UserPoolId / UserPoolClientId / ApiUrl / Region from the stack, then runs the seed script,
# which creates the demo users (admin API) and the circle through /circles + /circles/join.
seed:
	@eval "$$($(OUTPUTS) --shell)" && \
	  echo "seeding stack $(STACK) at $$ApiUrl (pool $$UserPoolId)" && \
	  $(PYTHON) scripts/seed.py --user-pool-id "$$UserPoolId" --client-id "$$UserPoolClientId" --api-url "$$ApiUrl" --region "$$Region" $(SEED_ARGS)

eval:
	$(PYTHON) eval/run_eval.py

test:
	$(PYTHON) -m pytest -q tests backend

# --- frontend ---------------------------------------------------------------------------------

frontend-dev:
	cd frontend && $(NPM) install && $(NPM) run dev

frontend-build:
	cd frontend && $(NPM) install && $(NPM) run build
