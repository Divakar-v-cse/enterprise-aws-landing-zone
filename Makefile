# Enterprise AWS Landing Zone - developer entry points
#
#   make help      list targets
#   make check     full zero-cost verification (fmt, validate, scan, test)
#   make plan      offline plan for dev (no credentials, no cost)
#   make clean     remove local plan artefacts
#
# Nothing here applies infrastructure. Deployment is a reviewed GitHub Actions
# workflow, never a local make target.

SHELL := /bin/bash
PY ?= python
TF ?= terraform
ENV ?= dev
ENV_DIR := environments/$(ENV)

.PHONY: help init fmt fmt-check validate plan preflight cost check scan test docs clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

init: ## terraform init for one environment (ENV=dev|staging|production)
	cd $(ENV_DIR) && $(TF) init -input=false

fmt: ## Format all Terraform files
	$(TF) fmt -recursive

fmt-check: ## Fail if any file is not formatted
	$(TF) fmt -recursive -check

validate: ## Validate all three environments
	@for e in dev staging production; do \
		echo "== $$e =="; \
		(cd environments/$$e && $(TF) init -input=false -no-color >/dev/null && $(TF) validate -no-color) || exit 1; \
	done

plan: ## Offline plan for ENV (zero-cost mode, no credentials required)
	cd $(ENV_DIR) && $(TF) plan -input=false -no-color -out=../../artifacts/local/$(ENV).tfplan

preflight: ## Deployment readiness checks for ENV
	$(PY) scripts/preflight.py --environment $(ENV)

cost: ## Estimate monthly cost of the ENV plan
	cd $(ENV_DIR) && $(TF) plan -input=false -no-color -out=../../artifacts/local/$(ENV).tfplan >/dev/null
	cd $(ENV_DIR) && $(TF) show -json ../../artifacts/local/$(ENV).tfplan > ../../artifacts/local/$(ENV)-plan.json
	$(PY) scripts/cost_guard.py --plan artifacts/local/$(ENV)-plan.json

check: ## Full zero-cost verification suite
	$(PY) scripts/run_all_checks.py

scan: ## Security scans only (checkov, trivy, policies, secrets)
	checkov -d . --framework terraform --config-file policies/scanners/checkov.yaml -o json --output-file-path security/raw --compact --quiet || true
	trivy config . --config policies/scanners/trivy.yaml --ignorefile .trivyignore.yaml
	$(PY) scripts/policy_lint.py
	$(PY) scripts/secret_scan.py

test: ## Python unit tests
	$(PY) -m pytest tests -q

docs: ## Documentation lint
	$(PY) scripts/docs_lint.py

clean: ## Remove local plan artefacts and caches
	$(PY) -c "import pathlib; [p.unlink() for p in pathlib.Path('artifacts/local').glob('*') if p.is_file()]"
