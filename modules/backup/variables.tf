###############################################################################
# Backup module - variables
#
# AWS Backup vault creation is free; backup storage is not. The plan is
# therefore opt-in (`enable_backup_plan = false` by default).
###############################################################################

variable "name_prefix" {
  description = "Prefix applied to every resource name."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,30}$", var.name_prefix))
    error_message = "name_prefix must be 2-31 chars, lowercase alphanumeric or hyphen."
  }
}

variable "environment" {
  description = "Environment name (dev, staging, production)."
  type        = string

  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "environment must be one of: dev, staging, production."
  }
}

variable "aws_account_id" {
  description = "AWS account ID used to scope the backup service role trust policy."
  type        = string
  default     = "111122223333"

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be a 12-digit AWS account ID."
  }
}

variable "kms_key_arn" {
  description = "KMS key for vault and backup encryption. Null uses the AWS-managed key."
  type        = string
  default     = null
}

variable "enable_backup_plan" {
  description = "Create the backup plan, rules and resource selection. BILLABLE (backup storage)."
  type        = bool
  default     = false
}

variable "selection_tags" {
  description = "Resource tags that opt a resource into the backup plan."
  type        = map(string)
  default = {
    Backup = "true"
  }
}

variable "daily_retention_days" {
  description = "Retention for daily recovery points (RPO 24h baseline)."
  type        = number
  default     = 35

  validation {
    condition     = var.daily_retention_days >= 7 && var.daily_retention_days <= 365
    error_message = "daily_retention_days must be between 7 and 365."
  }
}

variable "weekly_retention_days" {
  description = "Retention for weekly recovery points."
  type        = number
  default     = 90
}

variable "monthly_retention_days" {
  description = "Retention for monthly recovery points (compliance baseline: 365)."
  type        = number
  default     = 365
}

variable "cold_storage_after_days" {
  description = "Move recovery points to cold storage after N days. 0 disables the transition."
  type        = number
  default     = 0
}

variable "backup_window" {
  description = "UTC backup window (must not overlap the vault lock window)."
  type        = string
  default     = "03:00"

  validation {
    condition     = can(regex("^([01][0-9]|2[0-3]):[0-5][0-9]$", var.backup_window))
    error_message = "backup_window must be HH:MM in 24-hour UTC form."
  }
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
