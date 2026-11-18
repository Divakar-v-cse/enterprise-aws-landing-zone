# Security scan report

Generated: **2026-11-18** by `scripts/security_report.py`  
Scope: static analysis of the Terraform configuration in this repository. No AWS account was scanned, because no infrastructure was deployed.

> This report reflects what the scanners returned on the date above. A passing scan is not proof of a secure deployment: static analysis cannot see runtime configuration, patch level, credentials or live IAM evaluation.

## Tool summary

| Tool | Scope | Result |
|---|---|---|
| Checkov | Terraform static analysis | 0 failed / 0 passed / 0 skipped |
| Trivy (config) | IaC misconfiguration | 0 failure(s) across 11 target(s) |
| secret_scan.py | Credentials in working tree | 0 finding(s), 0 forbidden file(s) |
| policy_lint.py | IAM least privilege | 0 violation(s), 1 warning(s) |

## Findings

### Checkov

No failed checks.

### Trivy (IaC misconfiguration)

No misconfigurations reported.

### Secret scanning

No credential patterns found across 156 files (700 skipped: binaries, vendored code, allowlisted examples).

### IAM policy lint

| Rule | Severity | Detail |
|---|---|---|
| `PL007` | WARN | modules/iam/policies/permission-boundary.json.tftpl#AllowScopedWorkloadServices: PutObject on a whole-bucket wildcard - scope to a prefix |

## Accepted risks and documented exceptions

| Check | Justification |
|---|---|
| `CKV_AWS_18` | policy. Production enables it with enable_access_logging = true. |
| `CKV_AWS_126` | for this workload; enable_detailed_monitoring = true in staging/production. |
| `CKV_AWS_338` | default to 30 days and are configurable via flow_logs_retention_days. |
| `CKV_AWS_158` | which wires kms_key_id into every log group. |
| `CKV_AWS_45` | production profiles, disabled by design in the zero-cost profile. |
| `CKV_AWS_109` | on key deletion. |
| `CKV_AWS_111` | see policies/scanners/checkov.yaml |
| `CKV_AWS_356` | see policies/scanners/checkov.yaml |
| `CKV_AWS_300` | when it sits in its own rule with an explicit empty prefix. |
| `CKV_AWS_231` | RDP from the internet: the public NACL allows only 80, 443 and ephemeral ports. |
| `CKV_AWS_252` | security-notification work. |
| `CKV_AWS_144` | recreation; replication is the next step when RPO drops below 24h. |
| `CKV_AWS_119` | themselves, where the data justifies it. |
| `CKV_AWS_145` | see policies/scanners/checkov.yaml |

## Known limitations of this report

1. **No live account was scanned.** Account-level controls (SCPs, GuardDuty,
   Security Hub, IAM Access Analyzer, Config rules) are out of scope because
   the project is validated in zero-cost mode.
2. **Static analysis only.** Runtime drift, patch state and credential
   exposure at runtime are not visible here.
3. **Version-pinned rules.** Scanner rule sets change between releases; the
   versions used are recorded in the CI log and in `security/raw/`.
4. **Passing this report does not authorise a deployment.** Deployment
   requires the approval gate described in `docs/DEPLOYMENT.md`.

## Reproduction

```bash
python scripts/run_all_checks.py        # fmt, validate, scan, test
```
