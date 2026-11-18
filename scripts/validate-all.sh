#!/usr/bin/env bash
# Thin wrapper: run the full zero-cost verification suite.
# Nothing here applies infrastructure or contacts AWS.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/run_all_checks.py "$@"
