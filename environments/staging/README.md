# Environment: staging

Pre-production environment. **Production-parity topology**, reduced capacity.

| Property | Value |
|---|---|
| AWS account | staging account (separate from production) |
| Region | `us-east-1` |
| VPC CIDR | `10.20.0.0/16` |
| AZs | 3 |
| NAT Gateway | 1 shared (production uses 3) |
| Instances | 2 × `t3.small` |
| Public ingress | none |
| Log retention | 30 days |
| Backup | daily 14d / weekly 30d / monthly 90d |
| Encryption | CMK (when `zero_cost_mode = false`) |

## Why staging exists

Staging is where a change proves it can survive production conditions *before*
production sees it:

1. **Same topology** — 3 AZs, NAT egress, flow logs, alarms, CloudTrail.
2. **Same IAM model** — the workload role and permission boundary are identical
   to production, so a permission that works in staging works in production.
3. **Different blast radius** — 2 instances instead of 3, cheaper instance class,
   shorter retention.

## Zero-cost switching

```bash
# Free plan (default, no credentials needed)
terraform init && terraform validate && terraform plan

# Production-parity plan (requires credentials; still creates nothing)
terraform plan -var zero_cost_mode=false

# Apply - only through CI with the `staging` environment approval
```

`zero_cost_mode` is checked by `scripts/preflight.py`, which refuses to allow a
"production-parity" plan unless the cost estimate has been reviewed.
