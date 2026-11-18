# Cost management

## 1. Design rule

Cost is an input to the design, not a monthly surprise. Every billable resource is
opt-in, and `zero_cost_mode = true` forces all of them off regardless of the flags.
Two deliberate edits are required before anything can bill.

## 2. What costs money here

| Resource | Approx. cost | Default | Where |
|---|---|---|---|
| NAT Gateway | ~$0.045/h (~$32/mo) + $0.045/GB | off | dev off, staging 1, production 3 |
| EC2 instances | depends on type, 730 h/mo | 0 instances | dev 0, staging 2, production 3 |
| EBS gp3 | ~$0.08/GB-month | encrypted root only | 20/30/50 GiB per env |
| KMS CMK | ~$1/key-month + requests | off | on in staging/production parity |
| CloudWatch alarms | ~$0.10/alarm-month | off | 2 per instance when enabled |
| CloudWatch Logs | ~$0.50/GB ingest, $0.03/GB-month storage | log groups only | retention 14/30/90 d |
| CloudTrail | S3 storage beyond the free management-event copy | off | on in staging/production |
| AWS Backup | ~$0.05/GB-month warm, $0.01 cold | vault only | schedules in staging/production |
| S3 storage | ~$0.023/GB-month standard, $0.0125 IA, $0.004 Glacier IR | one bucket | lifecycle moves objects |

Figures are **indicative list prices** from the checked-in catalogue
[`scripts/lib/pricing_catalog.json`](../scripts/lib/pricing_catalog.json). They are
not a quote and not a bill; confirm with the AWS Pricing Calculator before approving
spend.

## 3. Reference profiles

| Profile | Monthly estimate | Composition |
|---|---|---|
| Zero-cost validation (committed default) | **$0.00** | no NAT, no EC2, no CMK, no alarms, no trail, no backup schedule |
| Dev with one t3.micro | ~$8 | 1 instance, 20 GiB gp3, no NAT |
| Staging parity | ~$55 | 1 NAT, 2 x t3.small, CMK, alarms, trail, backups |
| Production | ~$280 | 3 NAT, 3 x m7i.large, CMK, alarms, trail, backups, 150 GiB EBS |

Treat those numbers as order-of-magnitude. The mechanism (flags, estimates, guard)
matters more than the arithmetic.

## 4. Guard rails in code

```bash
# 1. The interlock: fail if any billable resource is planned in zero-cost mode
python scripts/cost_guard.py --plan plan.json --zero-cost-mode

# 2. Budget ceiling on an intentional billable plan
python scripts/cost_guard.py --plan plan.json --max-monthly-usd 50

# 3. Tag-based chargeback readiness
python scripts/tagging_validator.py --plan plan.json
```

`cost_guard.py` exits `2` when zero-cost mode is violated, so CI fails before a
reviewer has to notice.

## 5. Tagging for chargeback

Every resource carries `Project`, `Environment`, `ManagedBy`, `Owner`, `CostCenter`
via provider `default_tags`. Cost Explorer filtered on `user:Project` then
`user:Environment` produces per-environment spend without any extra instrumentation.
Policy: [`policies/tagging/tagging-policy.json`](../policies/tagging/tagging-policy.json).

## 6. Budget configuration

[`policies/budgets/budget.json`](../policies/budgets/budget.json) holds a
Terraform-ready budget: $50/month filtered on `user:Project`, alerts at 80% actual
and 100% forecasted. AWS Budgets is free for the first two actions; the file is
deliberately not applied, because a budget alerts on spend rather than preventing it.

## 7. Cleanup

```bash
python scripts/cleanup.py --environment dev                      # read-only review
python scripts/cleanup.py --environment dev --execute --confirm dev
```

The default only runs `terraform plan -destroy` and prints what would disappear.
Production teardown is refused from a workstation by design.

## 8. The three most common cost accidents

1. **Forgotten NAT Gateway** — $32/month each, invisible in a plan summary.
2. **Idle EC2 from a demo** — instances left running after a recording.
3. **Log ingestion** — verbose debug logging retained for 365 days.

Each is addressed above by a flag, an estimate, or a retention default.
