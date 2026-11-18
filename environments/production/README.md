# Environment: production

Isolated production account. Private workloads, full encryption, logging,
backup and a restrictive network posture.

| Property | Value |
|---|---|
| AWS account | **dedicated production account** (never shared with dev/staging) |
| Region | `us-east-1` |
| VPC CIDR | `10.30.0.0/16` |
| AZs | 3 (one instance per AZ) |
| NAT Gateway | 3 — one per AZ (AZ failure ≠ egress outage) |
| Instances | 3 × `m7i.large`, private subnets only |
| Public ingress | **none** — SSM Session Manager only |
| Log retention | 90 days application, 365 days audit |
| Backup | daily 35d / weekly 90d / monthly 365d |
| Encryption | customer managed KMS key, rotation enabled |
| Audit | multi-region CloudTrail, log file validation |
| Deletion | bucket `force_destroy = false`; destroys require change approval |

## Safety interlocks

| Interlock | Effect |
|---|---|
| `zero_cost_mode = true` in committed tfvars | Nothing billable is created even if `apply` is run |
| GitHub Environment `production` | Required reviewers must approve before apply |
| `scripts/preflight.py --environment production` | Blocks apply without `--i-approve-production` |
| Separate AWS account | Production IAM cannot reach dev/staging data |

## Deployment path

```text
PR -> terraform-validate -> security-scan -> terraform-plan (artifact)
   -> manual review -> terraform-apply (production environment, 2 approvals)
```

No engineer holds standing production credentials; the apply job assumes
`eawlz-production-github-ci` via GitHub OIDC for at most one hour.

## What is deliberately NOT automated

* **No automatic apply.** The apply workflow is `workflow_dispatch` only.
* **No automatic rollback.** Rollback is a reviewed re-apply of the previous
  plan artifact (`docs/DISASTER_RECOVERY.md`).
* **No data-plane changes.** Restores are operator-driven via AWS Backup.
