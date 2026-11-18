# Module: backup

AWS Backup vault, tag-based selection and a three-tier retention schedule.

## Schedule

| Rule | Cron (UTC) | Retention | Purpose |
|---|---|---|---|
| `daily` | every day at `backup_window` | 35 days | operational recovery (RPO 24 h) |
| `weekly` | Sunday | 90 days | bad-deploy / regression recovery |
| `monthly` | 1st of month | 365 days | compliance retention |

`cold_storage_after_days > 0` moves monthly recovery points to cold storage
before deletion — cheaper for long retention, slower to restore.

## Cost behaviour

* `aws_backup_vault` and the IAM role are free.
* **Backup storage is billable** (warm ~\$0.05/GB-month, cold ~\$0.01/GB-month).
* `enable_backup_plan = false` (default) creates the vault only, so the module is
  safe in zero-cost mode while still proving the design.

## Why tag-based selection

```hcl
selection_tag {
  type  = "STRINGEQUALS"
  key   = "Backup"
  value = "true"
}
```

New resources are protected by adding the tag — no plan edit, no PR for every new
volume. The trade-off is that an untagged resource is silently unprotected, which
is why `scripts/tagging_validator.py` enforces `Backup` in the required tag set
for stateful resource types.

## Restore path

Restores are **not** automated by Terraform. Use the documented runbook:

```bash
aws backup start-restore-job \
  --recovery-point-arn <arn> \
  --iam-role-arn <backup-role-arn> \
  --metadata file://restore-metadata.json
```

See `docs/DISASTER_RECOVERY.md` for the full procedure and validation steps.
