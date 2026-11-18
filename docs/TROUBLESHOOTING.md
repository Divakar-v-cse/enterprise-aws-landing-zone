# Troubleshooting

Real symptoms, real causes, real fixes. Commands assume you are in the repository
root unless stated otherwise.

## 1. Provider and initialisation

| Symptom | Cause | Fix |
|---|---|---|
| `Error: Failed to query available provider packages` | No network, proxy, or registry outage | Check connectivity; set `HTTPS_PROXY`; retry `terraform init` |
| `provider ... does not have a package available for your platform` | Lock file lacks your OS/arch | `terraform providers lock -platform=windows_amd64 -platform=linux_amd64` |
| `Error: Inconsistent dependency lock file` | Provider upgraded outside Terraform | `terraform init -upgrade` then commit the updated lock file |
| `Backend initialization required` | `backend.tf` added after init | `terraform init -reconfigure` |
| `Error: Unsupported argument` after upgrade | Provider major version change | Check the pinned constraint; this repo caps `< 7.0.0` |

## 2. Plan fails without credentials

Symptom:

```text
Error: Retrieving AWS account details: validating provider credentials:
RequestError: send request failed ... InvalidClientTokenId
```

Cause: the AWS provider calls STS during configure, even for a plan that creates
nothing.

Fix: ensure `offline_plan_mode = true` in the environment's `terraform.tfvars`. That
sets `skip_credentials_validation`, `skip_requesting_account_id` and
`skip_metadata_api_check`. Also confirm the configuration has **no data sources** —
data sources always need credentials.

## 3. `count cannot be determined until apply`

Symptom: `The "count" value depends on resource attributes that cannot be determined
until apply`.

Cause: a `count` derived from a resource attribute (for example
`length(module.ec2.instance_ids)`, where IDs are unknown until the instances exist).

Fix (already applied in this repo): derive `count` from a plan-known input such as
`var.instance_count`, and let unknown values appear only inside resource arguments.

## 4. `prevent_destroy` / lifecycle errors

Symptom: `Variables may not be used here` on a `lifecycle` block.

Cause: `lifecycle` arguments must be literal constants; a module variable is not
allowed.

Fix: this repo uses `force_destroy = var.force_destroy` (a normal argument) and
enforces deletion safety through approval gates plus `scripts/cleanup.py`.

## 5. State errors

| Error | Meaning | Safe resolution |
|---|---|---|
| `Error acquiring the state lock` | Another run holds the lock, or a run died | Confirm no apply is running, then `terraform force-unlock <LOCK_ID>` |
| `state snapshot was created by Terraform vX` | Older Terraform opening newer state | Upgrade the local Terraform |
| `Resource already exists` | Resource created outside Terraform | `terraform import <address> <id>`, never delete by hand |
| `Error: resource not found` on refresh | Resource deleted manually | Remove from state (`terraform state rm`) and re-apply, or re-import |
| `state data in S3 does not have the expected content` | Truncated or wrong key | Restore a previous object version in S3 |

Never hand-edit state JSON. `terraform state` subcommands plus a reviewed PR.

## 6. IAM permission errors

| Error | Cause | Fix |
|---|---|---|
| `AccessDenied: not authorized to perform: sts:AssumeRoleWithWebIdentity` | OIDC `sub` mismatch | Check the trust policy `sub` against the actual ref or environment |
| `AccessDenied ... iam:PassRole` | Role cannot pass the instance role | Add `iam:PassRole` scoped to that role ARN, with `iam:PassedToService=ec2.amazonaws.com` |
| `AccessDenied ... kms:CreateGrant` | Key policy blocks the caller | Add the principal to the key policy usage statement |
| `UnauthorizedOperation` on `ec2:CreateTags` | Tags are a separate action | Grant `ec2:CreateTags` alongside the create action |
| Works locally, fails in CI | CI role is narrower by design | Add the specific action to the CI policy, not a wildcard |

## 7. Networking mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Instance has no internet egress | No NAT and no `enable_nat_gateway` | Expected in zero-cost mode; enable NAT or use VPC endpoints |
| `Cannot assign requested address` / subnet CIDR error | Subnet CIDR outside the VPC or overlapping | Keep subnets inside the VPC block, never overlap AZs |
| Endpoint works from one subnet only | Route table not associated | Gateway endpoint must be associated with each private route table |
| SSM session fails to connect | No route to SSM endpoints, or missing instance profile | Add NAT or interface endpoints for `ssm`, `ssmmessages`, `ec2messages` |
| Security group change has no effect | NACL denies first (stateless) | Check NACL rules before blaming the SG |
| Cannot reach port 8080 from the internet | By design: no inbound rules | Use SSM port forwarding, not an open SG |

## 8. Scanner findings

| Tool | Finding | Correct response |
|---|---|---|
| Checkov `CKV_AWS_18` | S3 access logging disabled | Justified skip or enable logging with a second bucket |
| Checkov `CKV_AWS_45` | Flow logs disabled | Billable: enable per environment, keep the dated skip |
| Trivy `AWS-0104` | 0.0.0.0/0 egress on 443 | Accepted with statement and expiry in `.trivyignore.yaml` |
| Gitleaks hit in fixtures | Example credential in tests | Allowlist the exact path and value; never allowlist a directory |
| Policy lint `PL004` | Allow on IAM service actions | Scope to specific actions such as `iam:CreateRole` |

If a scanner flags something real, fix the code. A skip without a written reason and
an expiry date is technical debt disguised as a green build.

## 9. Python toolkit

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: eawlz_core` | Run from the repo root, or rely on `tests/conftest.py` which adds `scripts/lib` |
| `PlanFormatError: not a Terraform plan` | You passed a state file; use `terraform show -json tfplan` |
| `terraform executable not found` | Install Terraform and re-open the shell |
| `TerraformError: Refusing to run terraform apply` | Working as intended: automation is read-only |
| Empty inventory | Plan had no changes; run `terraform plan -out` first |

## 10. CI failures

| Job | Likely cause | Fix |
|---|---|---|
| `fmt` | Local file not formatted | `terraform fmt -recursive` |
| `validate` | Module type error | Run the same command locally for a fuller message |
| `tflint` | `--init` needs network for plugins | Re-run; the plugin cache is not persisted between jobs |
| `security-scan` | SARIF upload needs `security-events: write` | Check workflow permissions |
| `apply` guard | `confirm_apply` does not match the environment | Re-run with the exact environment name |
| `apply` init | `TF_STATE_BUCKET` variable not set | Set the repository variable; local backend is refused by design |
