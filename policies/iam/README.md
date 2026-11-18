# IAM policy library

Reviewable mirror of `modules/iam/policies/`. Verified identical by
`tests/test_policy_sync.py`.

| Document | Attached to | Purpose |
|---|---|---|
| `ec2-app-policy.json.tftpl` | workload role | Scoped S3/CloudWatch/SSM access + deny guardrails |
| `permission-boundary.json.tftpl` | workload role | Independent ceiling: no IAM, no audit tampering, approved regions only |
| `github-oidc-trust.json.tftpl` | CI role trust policy | Keyless GitHub Actions federation |
| `ci-terraform-deploy-policy.json.tftpl` | CI role | Scoped Terraform deployment permissions with explicit denies |

## Reading the templates

Placeholders are Terraform template expressions:

| Placeholder | Supplied by | Example |
|---|---|---|
| `${artifact_bucket_arn}` | `modules/iam` | `arn:aws:s3:::eawlz-dev-artifacts-111122223333` |
| `${log_group_arn}` | `modules/iam` | `arn:aws:logs:us-east-1:111122223333:log-group:/eawlz-dev/app` |
| `${metric_namespace}` | `modules/iam` | `EAWLZ/Dev` |
| `${ssm_parameter_arn_prefix}` | `modules/iam` | `arn:aws:ssm:us-east-1:111122223333:parameter/eawlz-dev/app` |
| `${approved_regions}` | `modules/iam` | `["us-east-1"]` (rendered via `jsonencode`) |
| `${aws_account_id}` | environment | `111122223333` |
| `${allowed_subjects}` | `modules/iam` | `["repo:org/repo:ref:refs/heads/main"]` |
| `${state_bucket_arn}`, `${lock_table_arn}` | environment | state bucket ARN, lock table ARN |

## Threat model notes

* The workload policy denies `iam:*`, `organizations:*`, CloudTrail/GuardDuty
  tampering, KMS key deletion and S3 policy widening **inside the identity
  policy**. Explicit denies survive future edits that add permissions.
* The boundary is deliberately narrower than the identity policy: even
  `AdministratorAccess` on the role cannot escape it.
* The CI role cannot create IAM users or access keys. It can create roles and
  policies because Terraform manages them — the trade-off is documented in
  `docs/IAM_SECURITY.md`.
