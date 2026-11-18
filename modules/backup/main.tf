###############################################################################
# Backup module - AWS Backup vault, plan, rules and tag-based selection
#
# Recovery design
#   daily   03:00 UTC  retain 35 days   (operational recovery)
#   weekly  Sunday     retain 90 days   (regression / bad deploy recovery)
#   monthly 1st        retain 365 days  (compliance retention)
#
# The vault is always created (free); schedules are opt-in because backup
# storage is billable. Tag-based selection means new resources are protected by
# adding `Backup = "true"` - no plan rewrite required.
###############################################################################

locals {
  tags = merge(var.tags, {
    Module      = "backup"
    Environment = var.environment
  })

  schedule_enabled = var.enable_backup_plan
}

resource "aws_backup_vault" "this" {
  name        = "${var.name_prefix}-vault"
  kms_key_arn = var.kms_key_arn

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-vault"
  })
}

data "aws_iam_policy_document" "backup_assume" {
  count = local.schedule_enabled ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["backup.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.aws_account_id]
    }
  }
}



resource "aws_iam_role" "backup" {
  count = local.schedule_enabled ? 1 : 0

  name               = "${var.name_prefix}-backup-role"
  description        = "Service role used by AWS Backup to snapshot ${var.environment} resources"
  assume_role_policy = data.aws_iam_policy_document.backup_assume[0].json

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-backup-role"
  })
}

resource "aws_iam_role_policy_attachment" "backup_service" {
  count = local.schedule_enabled ? 1 : 0

  role       = aws_iam_role.backup[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}

resource "aws_iam_role_policy_attachment" "backup_restore" {
  count = local.schedule_enabled ? 1 : 0

  role       = aws_iam_role.backup[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForRestores"
}

resource "aws_backup_plan" "this" {
  count = local.schedule_enabled ? 1 : 0

  name = "${var.name_prefix}-plan"

  rule {
    rule_name         = "daily"
    target_vault_name = aws_backup_vault.this.name
    schedule          = "cron(0 ${tonumber(split(":", var.backup_window)[0])} * * ? *)"

    start_window      = 60
    completion_window = 180

    lifecycle {
      delete_after = var.daily_retention_days
    }

    recovery_point_tags = merge(local.tags, {
      BackupFrequency = "daily"
    })
  }

  rule {
    rule_name         = "weekly"
    target_vault_name = aws_backup_vault.this.name
    schedule          = "cron(30 ${tonumber(split(":", var.backup_window)[0])} ? * SUN *)"

    start_window      = 60
    completion_window = 300

    lifecycle {
      delete_after = var.weekly_retention_days
    }

    recovery_point_tags = merge(local.tags, {
      BackupFrequency = "weekly"
    })
  }

  rule {
    rule_name         = "monthly"
    target_vault_name = aws_backup_vault.this.name
    schedule          = "cron(0 ${tonumber(split(":", var.backup_window)[0])} 1 * ? *)"

    start_window      = 60
    completion_window = 360

    lifecycle {
      cold_storage_after = var.cold_storage_after_days > 0 ? var.cold_storage_after_days : null
      delete_after       = var.monthly_retention_days
    }

    recovery_point_tags = merge(local.tags, {
      BackupFrequency = "monthly"
    })
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-plan"
  })
}

resource "aws_backup_selection" "tagged" {
  count = local.schedule_enabled ? 1 : 0

  name         = "${var.name_prefix}-tagged-resources"
  iam_role_arn = aws_iam_role.backup[0].arn
  plan_id      = aws_backup_plan.this[0].id

  selection_tag {
    type  = "STRINGEQUALS"
    key   = keys(var.selection_tags)[0]
    value = values(var.selection_tags)[0]
  }
}
