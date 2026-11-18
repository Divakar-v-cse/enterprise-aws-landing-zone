output "vault_name" {
  description = "AWS Backup vault name."
  value       = aws_backup_vault.this.name
}

output "vault_arn" {
  description = "AWS Backup vault ARN."
  value       = aws_backup_vault.this.arn
}

output "backup_plan_id" {
  description = "Backup plan ID, or null when the plan is disabled."
  value       = try(aws_backup_plan.this[0].id, null)
}

output "backup_role_arn" {
  description = "Service role ARN used by AWS Backup, or null when the plan is disabled."
  value       = try(aws_iam_role.backup[0].arn, null)
}

output "schedule_summary" {
  description = "Human-readable backup schedule summary for runbooks."
  value = local.schedule_enabled ? format(
    "daily(retain %dd) + weekly(retain %dd) + monthly(retain %dd) starting %s UTC",
    var.daily_retention_days, var.weekly_retention_days, var.monthly_retention_days, var.backup_window
  ) : "disabled (vault only, no scheduled backups)"
}
