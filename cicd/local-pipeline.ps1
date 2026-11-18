# Reproduce the CI pipeline locally on Windows, in CI order.
$ErrorActionPreference = "Stop"
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    Write-Output "== 1/8 fmt =="
    terraform fmt -recursive -check

    Write-Output "== 2/8 validate =="
    foreach ($e in @("dev", "staging", "production")) {
        Push-Location "environments/$e"
        try {
            terraform init -backend=false -input=false -no-color | Out-Null
            terraform validate -no-color
        }
        finally { Pop-Location }
    }

    Write-Output "== 3/8 tflint =="
    if (Get-Command tflint -ErrorAction SilentlyContinue) { tflint --init; tflint --recursive }
    else { Write-Output "tflint not installed - skipped" }

    Write-Output "== 4/8 checkov =="
    python -m checkov.main -d . --framework terraform --config-file policies/scanners/checkov.yaml --compact --quiet

    Write-Output "== 5/8 trivy =="
    $trivy = if (Test-Path ".tools/trivy.exe") { ".tools/trivy.exe" } else { "trivy" }
    & $trivy config . --config policies/scanners/trivy.yaml --ignorefile .trivyignore.yaml

    Write-Output "== 6/8 secret scan =="
    python scripts/secret_scan.py

    Write-Output "== 7/8 policy + docs lint =="
    python scripts/policy_lint.py
    python scripts/docs_lint.py

    Write-Output "== 8/8 tests =="
    python -m pytest tests -q

    Write-Output "All local CI steps passed (no AWS resources created)."
}
finally { Pop-Location }
