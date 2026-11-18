# Thin wrapper: run the full zero-cost verification suite on Windows.
# Nothing here applies infrastructure or contacts AWS.
$ErrorActionPreference = "Stop"
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    python scripts/run_all_checks.py @args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
