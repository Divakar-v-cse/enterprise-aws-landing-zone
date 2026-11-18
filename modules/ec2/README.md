# Module: ec2

Hardened application compute: no SSH, no public IP, IMDSv2 enforced, encrypted
volumes and an SSM-only management path.

## Hardening matrix

| Control | Setting | Why |
|---|---|---|
| Metadata service | `http_tokens = "required"` (IMDSv2) | Blocks SSRF-based credential theft |
| Hop limit | `1` | Containers on the host cannot reach IMDS |
| Public IP | `associate_public_ip_address = false` | No direct internet attack surface |
| SSH key | none (`key_name` unset) | No long-lived SSH credentials exist |
| Admin access | SSM Session Manager | Auditable, IAM-controlled, no inbound port |
| Root volume | `encrypted = true`, gp3 | Encryption at rest, no `standard` IOPS surprises |
| Detailed monitoring | `false` | 1-minute metrics are billable; basic is enough for dev |
| Instance role | from `modules/iam` | Temporary credentials only |

## Cost behaviour

`instance_count = 0` (the zero-cost default) creates no instances and **no AMI
lookup API call**, so `terraform plan` runs entirely offline. Set
`instance_count > 0` only with a real AWS account and an approved plan.

| Instance type | vCPU / RAM | On-demand reference (us-east-1) | Use |
|---|---|---|---|
| `t3.micro` | 2 / 1 GiB | ~\$0.0104/hour | dev smoke tests |
| `t3.small` | 2 / 2 GiB | ~\$0.0208/hour | dev app |
| `m7i.large` | 2 / 8 GiB | ~\$0.1008/hour | staging / production baseline |
| `m7g.large` | 2 / 8 GiB (ARM) | ~\$0.0816/hour | cost-optimised production |

Prices are indicative reference points for planning, **not** a quote or a bill.
Verify in the AWS Pricing Calculator for your region before approving an apply.

## Bootstrap behaviour

`user-data.sh.tftpl` is idempotent and contains no secrets:

1. Applies security updates and installs the CloudWatch agent.
2. Writes `/etc/eawlz/app.env` with environment metadata (mode 0640).
3. Ensures `amazon-ssm-agent` is running.
4. Ships the bootstrap log to the environment log group.

Secrets belong in SSM Parameter Store / Secrets Manager, never in user data
(user data is readable from instance metadata and stored in the launch
configuration).
