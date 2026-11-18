# Testing and validation

Every result below was produced by running the command in this repository on
2026-11-18, Windows 11, Terraform 1.15.8, Python 3.12, Checkov 3.4.5,
Trivy 0.76.2. No AWS credentials were used and no infrastructure was created.

## 1. Summary

| Check | Command | Result |
|---|---|---|
| Formatting | `terraform fmt -recursive -check` | clean |
| Init | `terraform init -backend=false` (x3) | success, provider 5.x |
| Validate | `terraform validate` (x3) | `Success! The configuration is valid.` |
| Plan dev | `terraform plan` | **46 to add, 0 to change, 0 to destroy**, $0 |
| Plan staging | `terraform plan` | 46 to add, $0 |
| Plan production profile | `terraform plan -var zero_cost_mode=false -var instance_count=0` | 72 to add |
| Checkov | `checkov -d . --framework terraform --config-file policies/scanners/checkov.yaml` | **202 passed, 0 failed** |
| Trivy | `trivy config . --ignorefile .trivyignore.yaml` | **0 failures** (8 targets) |
| IAM policy lint | `python scripts/policy_lint.py` | 0 failures, 1 warning |
| Secret scan | `python scripts/secret_scan.py` | 0 findings |
| Python tests | `python -m pytest tests -q` | 73 passed in 0.97s |
| Docs lint | `python scripts/docs_lint.py` | all required documents present |
| TFLint | `tflint --recursive` | **not executed** — not installed locally |

## 2. Terraform validation

```bash
$ terraform fmt -recursive -check
$ echo $?
0

$ for e in dev staging production; do (cd environments/$e && terraform validate -no-color); done
Success! The configuration is valid.
Success! The configuration is valid.
Success! The configuration is valid.
```

Evidence: [screenshots/terraform-validate.png](../screenshots/terraform-validate.png)

## 3. Offline plan

```bash
$ cd environments/dev && terraform plan -input=false -no-color
Plan: 46 to add, 0 to change, 0 to destroy.
```

No credentials were configured. This works because the environment sets
`offline_plan_mode = true` and the configuration contains no data sources; see
[TERRAFORM_SETUP.md](TERRAFORM_SETUP.md) section 3.

Evidence: [screenshots/terraform-plan-dev.png](../screenshots/terraform-plan-dev.png)

The production profile plans 72 resources with `zero_cost_mode = false`:
per-AZ NAT Gateways, KMS, Flow Logs, alarms, CloudTrail and the backup plan.

## 4. Security scanning

```bash
$ checkov -d . --framework terraform --config-file policies/scanners/checkov.yaml --compact --quiet
terraform scan results:
Passed checks: 179, Failed checks: 0, Skipped checks: 0

$ trivy config . --config policies/scanners/trivy.yaml --ignorefile .trivyignore.yaml
(no failures)
```

Findings were reduced from 20 to 0 by fixing real defects, not by disabling
checks:

| Was | Fix |
|---|---|
| Unlocked default security group | `aws_default_security_group` with no rules |
| Unencrypted SNS topic | `kms_master_key_id = alias/aws/sns` or CMK |
| CloudTrail bucket without lifecycle | abort-MPU + archive/expire rules |
| Redundant NACL deny-all rules | removed (deny by default) |

Remaining exceptions are dated, justified entries in
`policies/scanners/checkov.yaml` and `.trivyignore.yaml`, summarised in
[../security/SECURITY_REPORT.md](../security/SECURITY_REPORT.md).

Evidence: [screenshots/checkov-scan.png](../screenshots/checkov-scan.png) ·
[screenshots/trivy-scan.png](../screenshots/trivy-scan.png) ·
[screenshots/policy-lint.png](../screenshots/policy-lint.png)

## 5. Python tests

```bash
$ python -m pytest tests -q
73 passed in 0.97s
```

| File | Covers |
|---|---|
| `tests/test_core.py` | tfvars parsing, table rendering, redaction, attribute diffing, terraform verb guard |
| `tests/test_plan_analysis.py` | plan parsing, action classification, prior-state detection, tag violations, cost estimation |
| `tests/test_secret_scan.py` | credential patterns, redaction, path scoping |
| `tests/test_repository.py` | required files, module contract, environment isolation, policy copy sync, workflow YAML, gitignore, no state files, pricing disclaimer |

No test contacts AWS or requires network access.

## 6. Not executed (stated explicitly)

| Item | Why | How to run it |
|---|---|---|
| `tflint --recursive` | Not installed in this environment | `tflint --init && tflint --recursive` (CI runs it) |
| `terraform apply` | Requires credentials and approval | [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) |
| AWS resource verification | Nothing was deployed | After an approved apply |
| Restore test | Requires a live recovery point | [BACKUP_DISASTER_RECOVERY.md](BACKUP_DISASTER_RECOVERY.md) section 4 |
| GitHub Actions execution | Requires the push plus repository variables | Push, then `Actions` tab |

## 7. Reproducing

```bash
python -m pytest tests -q
python scripts/run_all_checks.py        # fmt, validate, scan, lint, test
bash cicd/local-pipeline.sh             # CI order, locally
```
