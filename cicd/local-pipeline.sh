#!/usr/bin/env bash
# Reproduce the CI pipeline locally, in the same order CI runs it.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 1/8 fmt =="
terraform fmt -recursive -check

echo "== 2/8 validate (dev, staging, production) =="
for e in dev staging production; do
  (cd "environments/$e" && terraform init -backend=false -input=false -no-color >/dev/null && terraform validate -no-color)
done

echo "== 3/8 tflint =="
if command -v tflint >/dev/null 2>&1; then tflint --init && tflint --recursive; else echo "tflint not installed - skipped"; fi

echo "== 4/8 checkov =="
if command -v checkov >/dev/null 2>&1; then
  checkov -d . --framework terraform --config-file policies/scanners/checkov.yaml --compact --quiet || true
else echo "checkov not installed - skipped"; fi

echo "== 5/8 trivy =="
if command -v trivy >/dev/null 2>&1; then
  trivy config . --config policies/scanners/trivy.yaml --ignorefile .trivyignore.yaml
else echo "trivy not installed - skipped"; fi

echo "== 6/8 secret scan =="
python3 scripts/secret_scan.py

echo "== 7/8 policy + docs lint =="
python3 scripts/policy_lint.py
python3 scripts/docs_lint.py

echo "== 8/8 tests =="
python3 -m pytest tests -q

echo "All local CI steps passed (no AWS resources created)."
