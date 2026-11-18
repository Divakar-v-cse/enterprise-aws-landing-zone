# Module: security

Encryption baseline: an optional customer managed KMS key with automatic rotation,
a least-privilege key policy and MFA-protected deletion.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `name_prefix` | `string` | – | Resource name prefix |
| `environment` | `string` | – | `dev` / `staging` / `production` |
| `aws_account_id` | `string` | `111122223333` | Account used in key policy principals |
| `create_kms_key` | `bool` | `false` | Create the CMK (**billable**, ~\$1/key/month) |
| `kms_deletion_window_days` | `number` | `30` | 7–30 day deletion window |
| `kms_key_administrators` | `list(string)` | `[]` | Key admin principals (defaults to account root) |
| `kms_key_users` | `list(string)` | `[]` | Key consumer principals |

## Outputs

| Name | Description |
|---|---|
| `kms_key_arn` | CMK ARN, `null` when disabled |
| `kms_key_id` | CMK ID, `null` when disabled |
| `kms_alias_name` | `alias/<prefix>-data`, `null` when disabled |
| `encryption_mode` | `cmk` or `aws-managed` |

## Key policy design

1. **Root delegation** (`kms:*` to the account root) lets IAM policies grant key
   usage without rewriting the key policy for every consumer.
2. **Explicit administrator statement** scoped to `local.key_admin_arns`.
3. **Usage statement** limited to `Encrypt`, `Decrypt`, `ReEncrypt*`,
   `GenerateDataKey*`, `DescribeKey` — no administrative actions.
4. **Grants only for AWS services**, gated by `kms:GrantIsForAWSResource`.
5. **Deletion/disable requires MFA** (`BoolIfExists` deny) so a stolen
   long-term credential cannot destroy the key that protects backups.

## Zero-cost behaviour

With `create_kms_key = false` the module creates nothing and returns `null`.
Consumers degrade gracefully:

* S3 → `AES256` (SSE-S3, free) instead of `aws:kms`.
* EBS → AWS-managed `aws/ebs` key (free, encryption still on).
* CloudWatch Logs → unencrypted by CMK (still encrypted at rest by AWS).

The same module therefore works in a zero-cost portfolio environment and in a
production account without conditional code in the environment root.
