# Doosri Raay - top-level developer commands.
# Run from Git Bash on Windows (GNU make + sh) or any POSIX shell. No bashisms beyond `&&` / `||`.
#
#   make validate        lint the SAM template and the Step Functions definitions (no AWS calls)
#   make deploy          sam build --use-container && sam deploy   (needs samconfig.toml, see samconfig.example.toml)
#   make deploy-guided   first-time interactive deploy that writes samconfig.toml
#   make outputs         print the stack outputs (paste into Amplify env vars)
#   make set-vapid       VAPID_PRIVATE_KEY=... overwrite the SSM placeholder as a SecureString
#   make seed / eval / test / frontend-dev / frontend-build / teardown

SAM      ?= sam
PYTHON   ?= python
AWS      ?= aws
NPM      ?= npm
STACK    ?= doosriraay
REGION   ?= ap-south-1
TEMPLATE := infra/template.yaml
# Optional extra CloudFormation parameters for `make deploy`, e.g.
#   make deploy PARAMS='AppOrigins=https://main.xxxx.amplifyapp.com,http://localhost:5173 DemoTimeouts=1'
PARAMS   ?=

.PHONY: help validate build deploy deploy-guided outputs set-vapid seed eval test frontend-dev frontend-build teardown logs-api

help:
	@echo "Targets: validate build deploy deploy-guided outputs set-vapid seed eval test frontend-dev frontend-build teardown logs-api"

# --- infrastructure ---------------------------------------------------------------------------

validate:
	-$(SAM) validate --lint --template $(TEMPLATE) --region $(REGION) || echo "sam validate skipped or failed (is the AWS SAM CLI installed?)"
	$(PYTHON) infra/validate_asl.py

build:
	$(SAM) build --use-container --template $(TEMPLATE)

deploy: build
	$(SAM) deploy --no-fail-on-empty-changeset $(if $(PARAMS),--parameter-overrides $(PARAMS),)

deploy-guided: build
	$(SAM) deploy --guided --template $(TEMPLATE)

outputs:
	$(AWS) cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" --output table

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

seed:
	$(PYTHON) scripts/seed.py

eval:
	$(PYTHON) eval/run_eval.py

test:
	$(PYTHON) -m pytest -q tests backend

# --- frontend ---------------------------------------------------------------------------------

frontend-dev:
	cd frontend && $(NPM) install && $(NPM) run dev

frontend-build:
	cd frontend && $(NPM) install && $(NPM) run build
