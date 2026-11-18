# scripts/

Automation toolkit. Every script is read-only with respect to AWS: none of them
run `terraform apply`. Destructive verbs are refused in code (see
`eawlz_core.run_terraform`), so a mistake in a wrapper cannot deploy anything.

| Script | What it answers | Read-only |
|---|---|---|
| `preflight.py` | Is this environment safe to plan/apply right now? | yes |
| `drift_report.py` | What does Terraform propose, and is it drift? | yes (runs `plan`) |
| `tf_state_inspect.py` | What does Terraform believe it owns? | yes |
| `inventory.py` | What resources does the config intend to create? | yes |
| `tagging_validator.py` | Does every resource carry the mandatory tags? | yes |
| `cost_guard.py` | What will this plan roughly cost per month? | yes |
| `backup_verify.py` | Is backup/DR configured as the standard requires? | yes |
| `secret_scan.py` | Are there credentials in the working tree? | yes |
| `policy_lint.py` | Are the IAM policies least-privilege? | yes |
| `security_report.py` | Merge scanner output into one report | yes |
| `docs_lint.py` | Are the docs complete, linked and placeholder-free? | yes |
| `run_all_checks.py` | Run the whole suite locally | yes |
| `make_evidence_images.py` | Render captured transcripts as PNG evidence | yes |
| `cleanup.py` | Print (or, with explicit confirmation, run) destroy | gated |

## Conventions

* Exit codes: `0` success, `1` failure/violation, `2` "changes detected"
  (mirrors `terraform plan -detailed-exitcode`).
* Every CLI has `--help`, validates arguments, and logs to stderr.
* Reports never include a live secret: matches are redacted.
* Indicative prices are labelled as estimates everywhere, including in JSON.

## Quick start

```bash
python scripts/run_all_checks.py          # fmt, validate, scan, test
python scripts/preflight.py --environment dev
python scripts/drift_report.py --environment dev --markdown reports/drift-dev.md
```
