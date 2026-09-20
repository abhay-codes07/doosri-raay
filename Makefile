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

# Stack outputs as eval-able KEY='VALUE' lines (infra/outputs.py wraps `sam list stack-outputs --output json`).
OUTPUTS   = $(PYTHON) infra/outputs.py --stack-name $(STACK) --region $(REGION) --sam "$(SAM)"

.PHONY: help validate build deploy deploy-guided outputs env seed image-check set-vapid eval test frontend-dev frontend-build teardown logs-api

help:
	@echo "Targets: validate build deploy deploy-guided outputs env seed image-check set-vapid eval test frontend-dev frontend-build teardown logs-api"

# --- infrastructure ---------------------------------------------------------------------------

validate:
	-$(SAM) validate --lint --template $(TEMPLATE) --region $(REGION) || echo "sam validate skipped or failed (is the AWS SAM CLI installed?)"
	$(PYTHON) infra/validate_asl.py

# BuildKit attaches provenance/SBOM attestations by default, which turns the pushed recovery-agent
# image into a multi-manifest OCI index that Lambda rejects. Disable them for every image build.
build deploy deploy-guided image-check: export BUILDX_NO_DEFAULT_ATTESTATIONS = 1

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
