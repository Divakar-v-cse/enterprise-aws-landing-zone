"""Shared pytest configuration: puts scripts/ and scripts/lib on sys.path."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"

for entry in (str(REPO_ROOT), str(SCRIPTS), str(SCRIPTS / "lib")):
    if entry not in sys.path:
        sys.path.insert(0, entry)
