# Environment: dev

Development environment. Lowest cost, fastest iteration, **no production data**.

| Property | Value |
|---|---|
| AWS account | sandbox / dev account (never the production account) |
| Region | `us-east-1` |
| VPC CIDR | `10.10.0.0/16` |
| AZs | 3 (`us-east-1a/b/c`) |
| NAT Gateway | **disabled** in zero-cost mode |
| Instances | `0` in zero-cost mode (`t3.micro` when enabled) |
| Public ingress | none — SSM Session Manager only |
| Log retention | 14 days |
| Backup | vault only (no schedule) |
| Encryption | SSE-S3 / AWS-managed EBS key (CMK off in zero-cost mode) |

## Commands

```bash
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan            # offline, no credentials required in zero-cost mode
```

Enable real resources (requires an approved change and cost estimate):

```bash
# 1. edit terraform.tfvars:  zero_cost_mode = false
# 2. enable only what you need, e.g. enable_nat_gateway = true
terraform plan -out=dev.tfplan
# 3. review the plan, then apply with explicit approval
terraform apply dev.tfplan
```

## Why dev is not a smaller copy of production

Dev optimises for **feedback speed** and **zero cost**:

* 2 NAT Gateways are replaced by 1 (or none) — availability in dev is not a
  business requirement.
* Backup schedules are off; S3 versioning still protects against operator error.
* Alarms are off; the dashboard is free and sufficient for a solo developer.

Everything that changes *security posture* (encryption, public access blocks,
least-privilege IAM, IMDSv2) stays identical to production. Drift between
environments should only ever be in capacity and availability, never in security
controls.
