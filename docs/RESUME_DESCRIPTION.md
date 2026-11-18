# Resume description

## Project line (one sentence)

Built a multi-environment AWS landing zone as reusable Terraform modules with
zero-cost validation, DevSecOps pipelines, drift detection and least-privilege IAM —
validated with 202 passing Checkov controls and a clean Trivy IaC scan, without
deploying paid infrastructure.

## Bullet points

* Designed and implemented seven reusable Terraform modules (networking, KMS,
  IAM, EC2, S3, monitoring, backup) composing three isolated environments with
  separate state, non-overlapping CIDRs and environment-specific security postures.
* Eliminated standing AWS credentials: GitHub Actions authenticates via OIDC with a
  trust policy scoped to repository, branch and environment; workloads use instance
  roles with IMDSv2 enforced (hop limit 1) and no SSH ingress.
* Enforced least privilege with scoped identity policies, condition keys, explicit
  deny guardrails (IAM, audit tampering, key deletion, bucket widening) and an
  independent permission boundary that survives future over-grants.
* Achieved zero-cost infrastructure-as-code validation: `terraform plan` runs fully
  offline with no AWS credentials, producing 46-resource dev and 72-resource
  production-profile plans, gated by a `zero_cost_mode` interlock that CI verifies.
* Built a Python toolkit (13 CLIs, 60+ unit and contract tests) for drift reporting,
  cost estimation, tagging compliance, backup readiness, secret scanning, IAM policy
  linting and documentation validation, with redacted, commit-safe reports.
* Hardened storage and audit: S3 public-access blocks, TLS-only and
  encryption-required bucket policies, versioning with non-current expiry, KMS with
  rotation and MFA-gated deletion deny, multi-region CloudTrail with log-file
  validation and a 365-day lifecycle.
* Engineered a five-workflow CI/CD pipeline (fmt, validate, TFLint, Checkov, Trivy,
  Gitleaks, pytest, plan artefacts) with approval-gated deployment that refuses
  local state and requires a typed environment confirmation.
* Reduced static-analysis findings from 20 to 0 by fixing real defects (unlocked
  default security group, unencrypted SNS, lifecycle gaps) and documenting the
  remainder as dated, justified accepted risks rather than blanket skips.

## Skills demonstrated

Terraform (modules, state, validation), AWS (VPC, IAM, KMS, S3, EC2, CloudWatch,
CloudTrail, AWS Backup), DevSecOps (Checkov, Trivy, TFLint, Gitleaks), Python
automation and testing, GitHub Actions with OIDC, security architecture, technical
writing and honest scoping of what was verified.

## Interview one-liner

"The interesting part was not writing Terraform; it was making the project provable —
offline plans, dated risk exceptions, and reports that say what they do not prove."

## Honest caveats to include if asked

* No AWS deployment was performed: no credentials, no approval.
* TFLint is wired into CI but was not executed locally (not installed in that
  environment).
* No restore test has run, so RPO/RTO are targets, not measurements.
