# Module: iam

Least-privilege identity layer: a workload role with a scoped policy and a
permission boundary, plus a GitHub Actions OIDC role for keyless CI/CD.

## What it creates

| Resource | Purpose | Billable |
|---|---|---|
| `aws_iam_role.ec2` | Workload role assumed via IMDSv2 | no |
| `aws_iam_policy.ec2_app` | Scoped S3 / CloudWatch / SSM permissions + deny guardrails | no |
| `aws_iam_policy.permission_boundary` | Hard ceiling on the workload role | no |
| `aws_iam_instance_profile.ec2` | Profile attached to instances | no |
| `aws_iam_role.ci` | GitHub OIDC role | no |
| `aws_iam_policy.ci_deploy` | Scoped Terraform deployment permissions | no |
| `aws_iam_openid_connect_provider.github` | OIDC provider (optional) | no |

No IAM user, access key, or console login is created by this module — by design.

## Least-privilege decisions

* **Explicit resourced ARNs.** The S3 statements name the exact bucket plus a
  prefix (`config/*`, `releases/*`, `app-logs/*`). No `Resource: "*"` on data
  plane actions.
* **Condition keys** on `s3:ListBucket` (`s3:prefix`) and
  `cloudwatch:PutMetricData` (`cloudwatch:namespace`) so the role cannot enumerate
  the bucket or pollute other namespaces.
* **Own log group only**: `${log_group_arn}:*` rather than `logs:*` on `*`.
* **Deny guardrails inside the identity policy**: `iam:*`, `organizations:*`,
  CloudTrail/GuardDuty/Config tampering, KMS key deletion and S3 policy widening
  are explicitly denied. An explicit deny beats any future allow added by mistake.
* **Permission boundary** is a second, independent control: even if someone
  attaches `AdministratorAccess` to the role, the boundary blocks IAM, audit
  tampering, public bucket exposure and non-approved regions.
* **`AmazonSSMManagedInstanceCore`** is attached deliberately: it is required for
  Session Manager and grants no infrastructure read/write. This is why the
  landing zone needs no bastion host and no inbound port 22.

## GitHub OIDC

```text
GitHub Actions job --(OIDC JWT)--> sts:AssumeRoleWithWebIdentity --> eawlz-<env>-github-ci
```

Trust policy conditions:

1. `aud` must equal `sts.amazonaws.com`.
2. `sub` must match one of `local.allowed_subjects`:
   `repo:<org>/<repo>:ref:refs/heads/main`,
   `repo:<org>/<repo>:environment:staging`,
   `repo:<org>/<repo>:environment:production`.

`repo:*` is rejected by variable validation — a wildcard subject would let *any*
repository in any organisation assume the role.

The CI role intentionally does **not** carry the workload permission boundary,
because the boundary denies `iam:*` and Terraform must manage roles. The CI
policy compensates with its own explicit denies (`iam:CreateUser`,
`iam:CreateAccessKey`, `cloudwatch:StopLogging` equivalents, region guard).

## Known trade-off

The CI policy is service-scoped and deny-hardened, but not yet tag-conditioned.
Before production use, tighten it with `aws:RequestedRegion` +
`aws:ResourceTag/Environment` conditions and consider AWS IAM Access Analyzer
policy generation from CloudTrail activity. This is documented as a harden-before-
production item in `docs/IAM_SECURITY.md`.
