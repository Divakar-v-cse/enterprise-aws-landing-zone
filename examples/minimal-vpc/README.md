# Example: minimal VPC

Shows the `modules/networking` contract with the fewest possible inputs and no
billable resources (no NAT Gateway, no Flow Logs, no instances).

```bash
cd examples/minimal-vpc
terraform init
terraform plan     # 14 to add, all free
```

Use this when you need to prove module behaviour in isolation, or when writing a
new environment that does not need the full landing zone.
