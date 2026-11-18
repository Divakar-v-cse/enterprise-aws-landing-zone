# Project audit

Audit date: 2026-11-18. Target: `enterprise-aws-landing-zone`, working tree before completion.

Legend: **Complete** (implemented and verified) · **Incomplete** (partial, unverified) ·
**Missing** (absent) · **N/A** (not applicable to this design).

## 1. Summary

| Area | Found at audit | Action taken | Status now |
|---|---|---|---|
| Terraform modules | 7 of 7 present, validating | hardened (default SG, SNS encryption, trail lifecycle) | Complete |
| Environment configs | 3 of 3 present | added `terraform.tfvars.example` per environment | Complete |
| IAM policies | 4 templates + boundary | added policy lint + copy-sync test | Complete |
| Networking | VPC, NAT, NACLs, SGs, endpoints | removed redundant deny rules, locked default SG | Complete |
| Storage and encryption | S3 + KMS modules | TLS-only policy, lifecycle, upload-encryption guard | Complete |
| Monitoring and audit | log groups, dashboard, alarms, trail | trail bucket lifecycle, SNS encryption | Complete |
| Backup and DR | vault, plan, tag selection | verification script + runbook | Complete |
| CI/CD workflows | **0 of 5** | written, YAML-validated | Complete |
| Tests | 5 files but **fixtures missing** (suite could not run) | fixtures added, suite executed | Complete |
| Documentation | **0 of 20** | written | Complete |
| Diagrams | **Missing** | `.mmd` plus rendered `.png` | Complete |
| Screenshots | **Missing** | rendered from real terminal captures | Complete |
| Security report | **Missing** | generated from real scanner output | Complete |
| Git repository | **not initialised** | init, remote, commit, push | Complete |

**Critical finding:** the Terraform layer was sound (all three environments validated
and planned offline), but the project could not be *evidenced*: no documentation, no
CI, a test suite whose fixtures were absent, and no git history.

## 2. Modules

| Module | Status | Contents |
|---|---|---|
| `modules/networking` | Complete | VPC, 6 subnets across 3 AZs, IGW, route tables, optional NAT + EIP, 2 NACLs, 3 SGs including default-SG lockdown, S3 gateway endpoint, optional flow logs |
| `modules/security` | Complete | KMS CMK, rotation, split key policy, MFA-gated deletion deny, optional creation |
| `modules/iam` | Complete | EC2 role, scoped policy, permission boundary, instance profile; GitHub OIDC provider, CI role, scoped deploy policy |
| `modules/ec2` | Complete | IMDSv2 required, no public IP, no key pair, encrypted gp3 root, conditional AMI lookup, preconditions |
| `modules/s3` | Complete | Public-access block x4, SSE, versioning, lifecycle, TLS-only and encryption-required policy |
| `modules/monitoring` | Complete | Log groups with retention, dashboard, optional alarms and SNS, optional CloudTrail with validation |
| `modules/backup` | Complete | Vault, three-rule plan, tag-based selection, service role |

Naming deviation: the brief names `storage`, `compute`, `encryption`; this repository
uses `s3`, `ec2`, `security`. Existing names were kept to avoid churn across seven
modules and three environments. Mapping documented in
[STORAGE_ENCRYPTION.md](STORAGE_ENCRYPTION.md).

## 3. Environments

| Environment | Status | Profile |
|---|---|---|
| `environments/dev` | Complete | `10.10.0.0/16`, zero-cost, no NAT, 0 instances |
| `environments/staging` | Complete | `10.20.0.0/16`, production-parity toggles, 2 x t3.small |
| `environments/production` | Complete | `10.30.0.0/16`, per-AZ NAT, 3 x m7i.large, CMK, trail, backups |

Environment roots are identical in wiring; only `terraform.tfvars` differs, so a
reviewer diffs one small file per environment.

## 4. Security controls

| Control | Status | Implementation |
|---|---|---|
| IAM least privilege | Complete | Scoped ARNs, condition keys, deny guardrails, permission boundary |
| No long-lived credentials | Complete | OIDC for CI, instance roles, SSM instead of SSH |
| S3 public access blocked | Complete | Bucket PAB, ownership enforced, TLS-only policy |
| Encryption at rest | Complete | S3 SSE (KMS when CMK present), encrypted EBS, CloudWatch CMK when enabled |
| Encryption in transit | Complete | TLS-only bucket policies, HTTPS-only egress |
| Restricted security groups | Complete | No inbound by default, no ports 22 or 3389 anywhere |
| CloudTrail | Complete (opt-in) | Multi-region, log-file validation, lifecycle |
| Secret management | Complete | SSM parameter paths, no secrets in code or tfvars |
| State security | Complete | Backend template, bootstrap with versioning/encryption/locking, state git-ignored |
| Environment isolation | Complete | Separate accounts (documented), state, CIDR, KMS, tags |

## 5. Defects found and fixed

| Defect | Fix |
|---|---|
| `prevent_destroy` given a variable (invalid HCL) | Replaced with `force_destroy`; deletion safety via approval gate and `cleanup.py` |
| Alarm `count` derived from unknown instance IDs (count cannot be determined until apply) | Count derives from plan-known `instance_count` |
| `data.aws_region` and unconditional AMI lookup broke offline plan | Region is an input; AMI lookup conditional on `instance_count > 0` |
| Explicit NACL deny-all rules flagged by scanners | Removed, NACLs deny by default |
| Default security group left at AWS defaults | Managed with no rules |
| SNS topic unencrypted | `alias/aws/sns` (free) or environment CMK |
| CloudTrail bucket had no lifecycle | Abort-MPU plus archive/expire rules |

## 6. Not applicable

| Item | Why |
|---|---|
| AWS Organizations / Control Tower | Single-account scope; governance documented, not provisioned |
| EKS / ECS / ALB / RDS | The platform is the network, identity, storage and audit foundation |
| Cross-region replication | Backup-based DR instead; documented as future work |
| WAF | No public ingress by design |
| Live AWS deployment | No credentials and no approval were used |

## 7. Verification status

| Command | Result |
|---|---|
| `terraform fmt -recursive -check` | clean |
| `terraform init -backend=false` x 3 | success |
| `terraform validate` x 3 | valid |
| `terraform plan` dev and staging (zero-cost) | 46 to add, 0 USD |
| `terraform plan` production profile | 72 to add |
| Checkov 3.4.5 | 202 passed, 0 failed |
| Trivy 0.76.2 | 0 failures after documented ignores |
| pytest | see [TESTING.md](TESTING.md) |
| TFLint | **not installed in this environment**, wired into CI, not executed locally |

TFLint is the single required tool that could not run here. That is stated rather
than hidden: the workflow installs and runs it on every pull request.
