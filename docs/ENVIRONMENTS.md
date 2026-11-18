# Environments

Three isolated environments, each a separate root module with its own state, CIDR
plan, tags and approval path.

| | dev | staging | production |
|---|---|---|---|
| Purpose | fast feedback, zero cost | production parity, reduced capacity | live workloads |
| AWS account | dev/sandbox | staging | dedicated production |
| VPC | `10.10.0.0/16` | `10.20.0.0/16` | `10.30.0.0/16` |
| Public subnets | `10.10.0.0/20`, `.16.0/20`, `.32.0/20` | `10.20.x` | `10.30.x` |
| Private subnets | `10.10.128.0/20`, `.144.0/20`, `.160.0/20` | `10.20.x` | `10.30.x` |
| AZs | 3 | 3 | 3 |
| NAT | disabled (zero-cost) | 1 shared | 1 per AZ |
| Instances | 0 (`t3.micro` when enabled) | 2 x `t3.small` | 3 x `m7i.large` |
| Root volume | 20 GiB | 30 GiB | 50 GiB |
| Ingress | none | none | none |
| Log retention | 14 d | 30 d | 90 d app, 365 d audit |
| Alarms | off | on | on |
| CloudTrail | off | on | on |
| Backup | vault only | 14/30/90 d | 35/90/365 d |
| Encryption | SSE-S3, AWS-managed EBS key | CMK | CMK |
| Approval | optional | 1 reviewer | 2 reviewers plus branch policy |
| `zero_cost_mode` | true | true (flip for parity) | true, as an interlock |

## Why directories instead of workspaces

| | Directories (chosen) | Workspaces |
|---|---|---|
| State | Separate backend key per environment | One backend, keys derived from workspace name |
| Variables | Separate tfvars per directory | Shared values plus workspace conditionals |
| Blast radius | Wrong directory fails the environment self-guard | One flag slip plans production from a dev shell |
| CI clarity | Matrix over directories | `TF_WORKSPACE` handling |
| Cost | Three plan runs | One run, three workspaces |

The guard matters more than the saved runs: each environment asserts its own name,
so a misdirected command fails at plan time.

## Zero-cost switching

```bash
cd environments/staging
terraform plan                              # zero_cost_mode = true, 46 free resources
terraform plan -var zero_cost_mode=false    # production parity, needs credentials
```

The interlock forces every billable flag off:

```hcl
effective_instance_count = local.billable ? var.instance_count : 0
effective_nat            = local.billable && var.enable_nat_gateway
effective_kms            = local.billable && var.enable_kms_key
```

Two deliberate edits are therefore required to spend money, and
`scripts/cost_guard.py --zero-cost-mode` fails the build if that contract breaks.

## Promotion path

```text
feature branch -> dev (plan only, no approval)
              -> staging (plan plus one reviewer)
              -> production (plan plus two reviewers plus typed confirmation)
```

The same commit must pass all three. Promotion re-applies the same commit; it is
never a manual edit of production values.
