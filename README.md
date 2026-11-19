# Enterprise AWS Landing Zone

**Secure multi-environment cloud infrastructure automation** — Terraform modules,
DevSecOps pipelines, drift detection, cost guard rails and audit logging for
`dev`, `staging` and `production` on AWS.

[![Terraform validate](https://img.shields.io/badge/terraform-1.15.8-7B42BC)](docs/TERRAFORM_SETUP.md)
[![Security](https://img.shields.io/badge/checkov-202%20passed-success)](security/SECURITY_REPORT.md)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## What this is

A reusable infrastructure platform, not a demo stack. Three isolated environments
are composed from seven Terraform modules; every environment can be **validated
and planned offline at zero cost**, and nothing is ever applied automatically.

| Capability | Implementation |
|---|---|
| Multi-account / multi-environment isolation | Separate state, CIDR plan, tags and IAM per environment |
| Secure networking | Multi-AZ VPC, public/private segmentation, NACLs, locked-down default SG, optional NAT |
| Least-privilege IAM | Scoped identity policies + permission boundary + GitHub OIDC (no access keys) |
| Encryption | KMS CMK (optional), SSE, TLS-only bucket policies, encrypted EBS |
| Audit & monitoring | CloudTrail with log-file validation, CloudWatch log groups, dashboard, optional alarms |
| Resilience | AWS Backup plan (daily/weekly/monthly), versioning, documented RPO/RTO |
| Delivery | 5 GitHub Actions workflows, approval-gated apply, zero long-lived secrets |
| Assurance | Checkov, Trivy, TFLint, custom IAM policy lint, secret scan, pytest, docs lint |

## Zero-cost by default

Every billable resource (NAT Gateway, EC2, KMS CMK, Flow Logs, alarms, CloudTrail,
backup schedules) is behind an explicit flag and **forced off** unless
`zero_cost_mode = false`. That means:

```bash
cd environments/dev
terraform init && terraform validate && terraform plan
# Plan: 46 to add, 0 to change, 0 to destroy.   (nothing created, nothing billed)
```

No AWS credentials are required for that plan — the provider runs in
`offline_plan_mode`, so `plan` is a pure local computation.

## Repository map

```text
environments/{dev,staging,production}   composition roots (thin: modules + tfvars)
modules/{networking,security,iam,ec2,s3,monitoring,backup}
scripts/                                Python toolkit (drift, cost, tagging, scans)
policies/                               IAM policy library, tagging, budgets, scanner config
.github/workflows/                       fmt/validate, security, plan, apply, docs
bootstrap/                              one-time remote state backend (human-run)
examples/minimal-vpc/                   smallest module composition
docs/                                   architecture, security, operations, interview
diagrams/  screenshots/  reports/  security/
tests/                                  pytest: pure logic + repository contracts
```

## Quick start

```bash
git clone https://github.com/Divakar-v-cse/enterprise-aws-landing-zone.git
cd enterprise-aws-landing-zone

python -m pytest tests -q          # 60+ unit and contract tests, no AWS
python scripts/run_all_checks.py   # fmt, validate, scan, lint, test
cd environments/dev && terraform init && terraform plan
```

Detailed setup: [docs/INSTALLATION.md](docs/INSTALLATION.md) ·
Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) ·
Audit: [docs/PROJECT_AUDIT.md](docs/PROJECT_AUDIT.md)

## Environments

| | dev | staging | production |
|---|---|---|---|
| VPC | `10.10.0.0/16` | `10.20.0.0/16` | `10.30.0.0/16` |
| AZs | 3 | 3 | 3 |
| NAT | off (zero-cost) | 1 shared | 1 per AZ |
| Instances | 0 (`t3.micro`) | 2 (`t3.small`) | 3 (`m7i.large`) |
| Ingress | none (SSM) | none (SSM) | none (SSM) |
| Log retention | 14 d | 30 d | 90 d app / 365 d audit |
| Backup | vault only | 14/30/90 d | 35/90/365 d |
| Approval | optional | 1 reviewer | 2 reviewers + branch policy |

## Deployment

```text
PR -> fmt/validate/tflint -> checkov/trivy/secret scan -> pytest
   -> plan (artefact + cost estimate) -> human review
   -> workflow_dispatch apply (GitHub Environment approval, typed confirmation)
```

`terraform apply` runs only inside a protected GitHub Environment and only from a
saved plan file. There is no local apply path and no automatic deployment.
See [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md).

## Status — what has actually been verified

| Check | Result | Evidence |
|---|---|---|
| `terraform fmt -recursive -check` | clean | [docs/TESTING.md](docs/TESTING.md) |
| `terraform validate` (3 environments) | valid | [docs/TESTING.md](docs/TESTING.md) |
| `terraform plan` dev | 46 to add, $0 | [screenshots/terraform-plan-dev.png](screenshots/terraform-plan-dev.png) |
| Checkov | 202 passed, 0 failed | [security/SECURITY_REPORT.md](security/SECURITY_REPORT.md) |
| Trivy (IaC) | 0 failures | [security/SECURITY_REPORT.md](security/SECURITY_REPORT.md) |
| pytest | see TESTING.md | [docs/TESTING.md](docs/TESTING.md) |
| AWS deployment | **not performed** | no credentials, no approval |

**No AWS infrastructure has been deployed.** Everything in this repository is
validated locally and via static analysis; the architecture diagram and
screenshots are labelled design/local-validation evidence, not a live account.

## Documentation

| Document | Contents |
|---|---|
| [docs/PROJECT_AUDIT.md](docs/PROJECT_AUDIT.md) | Component-by-component completeness audit |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Design, diagrams, decisions and trade-offs |
| [docs/NETWORKING.md](docs/NETWORKING.md) | VPC, subnets, routing, IP plan |
| [docs/IAM_SECURITY.md](docs/IAM_SECURITY.md) | Roles, boundaries, OIDC |
| [docs/STORAGE_ENCRYPTION.md](docs/STORAGE_ENCRYPTION.md) | S3 and KMS controls |
| [docs/MONITORING_AUDITING.md](docs/MONITORING_AUDITING.md) | CloudWatch and CloudTrail |
| [docs/CI_CD.md](docs/CI_CD.md) | Workflows, OIDC, approval gates |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model and controls |
| [docs/COST_MANAGEMENT.md](docs/COST_MANAGEMENT.md) | Cost model and guard rails |
| [docs/BACKUP_DISASTER_RECOVERY.md](docs/BACKUP_DISASTER_RECOVERY.md) | RPO/RTO and runbook |
| [docs/DRIFT_DETECTION.md](docs/DRIFT_DETECTION.md) | Drift reporting scope and limits |
| [docs/TESTING.md](docs/TESTING.md) | Commands and actual results |
| [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) | Safe deployment steps |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Provider, state, IAM, network errors |
| [docs/TECHNICAL_INTERVIEW.md](docs/TECHNICAL_INTERVIEW.md) | 35 Q&A walkthrough |
| [docs/RESUME_DESCRIPTION.md](docs/RESUME_DESCRIPTION.md) | Resume-ready bullets |
| [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) | 4-minute demo script |

## Design principles

1. **Nothing billable is implicit.** Cost is a design input, not a surprise.
2. **Deny beats allow.** Explicit `Deny` statements and permission boundaries
   survive future edits; a missing allow fails closed.
3. **Plan is a proposal, not proof.** Drift reports label candidates, never
   claim verified drift they cannot prove.
4. **No long-lived credentials.** OIDC for CI, instance roles for workloads, SSM
   instead of SSH.
5. **Documented limits.** Every report states what it does not prove.

## Acceptance criteria

- [x] Terraform formats cleanly (`fmt -recursive -check` exit 0)
- [x] Terraform initialises locally (`init -backend=false`, 3 environments)
- [x] Terraform validates (3 of 3)
- [x] Reusable modules with validated inputs and documented outputs
- [x] Environment configurations are separate directories with separate state
- [x] Static security scanning runs (Checkov 202 passed / 0 failed, Trivy 0 failures)
- [x] IAM examples follow least privilege (policy lint: 0 violations)
- [x] Python automation works (73 tests passing)
- [x] Drift reporting works within its documented scope
- [x] CI workflows are valid and approval-gated
- [x] Production approval configured (protected environment + typed confirmation)
- [x] No secrets committed (0 findings, no state or plan files tracked)
- [x] Documentation complete (21 documents, internally linked)
- [x] Local validation requires no paid AWS services

Deliberately **not** ticked: AWS deployment, TFLint (not installed locally) and a
restore test. See [docs/GITHUB_PUSH_REPORT.md](docs/GITHUB_PUSH_REPORT.md) section 9.

## License

[MIT](LICENSE)
