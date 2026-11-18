# python/

The Python automation for this project lives in [`scripts/`](../scripts/README.md)
so that every tool is runnable with a short, obvious path
(`python scripts/preflight.py`). There is no duplicate package here.

| Concern | Location |
|---|---|
| Shared domain logic (pure functions, testable) | [`scripts/lib/eawlz_core.py`](../scripts/lib/eawlz_core.py) |
| CLI entry points | [`scripts/*.py`](../scripts) |
| Price catalogue (indicative only) | [`scripts/lib/pricing_catalog.json`](../scripts/lib/pricing_catalog.json) |
| Tests | [`tests/`](../tests) |

Design rule: CLIs stay thin (argument parsing, logging, exit codes) and all
decisions live in `eawlz_core` so they can be unit tested without AWS or
Terraform. That is why `tests/` never shells out to the cloud.
