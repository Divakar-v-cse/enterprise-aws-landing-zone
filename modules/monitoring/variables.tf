###############################################################################
# Monitoring module - variables
#
# Zero-cost default: log groups (free up to 5 GB ingest), dashboard (free) and
# an SNS topic (free). Alarms, CloudTrail and metric streams are opt-in because
# they are billable.
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
  description = "AWS account ID (CloudTrail bucket policy principal scope)."
  type        = string
  default     = "111122223333"

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be a 12-digit AWS account ID."
  }
}

variable "aws_region" {
  description = "AWS region for metric namespaces and the CloudTrail trail."
  type        = string
  default     = "us-east-1"
}

variable "log_group_names" {
  description = "CloudWatch log groups to create (application, system, audit)."
  type        = list(string)
  default     = ["/eawlz/dev/app"]

  validation {
    condition     = alltrue([for n in var.log_group_names : can(regex("^/[A-Za-z0-9._/-]{2,480}$", n))])
    error_message = "Log group names must start with '/' and contain only letters, numbers, '.', '_', '/' or '-'."
  }
}

variable "log_retention_days" {
  description = "Retention for application log groups. Longer retention = more storage cost."
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.log_retention_days)
    error_message = "log_retention_days must be a retention value supported by CloudWatch Logs."
  }
}

variable "audit_log_retention_days" {
  description = "Retention for the audit/security log group."
  type        = number
  default     = 365

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.audit_log_retention_days)
    error_message = "audit_log_retention_days must be a retention value supported by CloudWatch Logs."
  }
}

variable "kms_key_arn" {
  description = "KMS key for log group encryption. Null leaves CloudWatch's default encryption."
  type        = string
  default     = null
}

variable "instance_count" {
  description = "Number of instances to monitor. Must be plan-time known; drives alarm count and dashboard series."
  type        = number
  default     = 0

  validation {
    condition     = var.instance_count >= 0
    error_message = "instance_count cannot be negative."
  }
}

variable "instance_ids" {
  description = "Instance IDs to alarm on (empty list = no alarms, zero-cost mode)."
  type        = list(string)
  default     = []
}

variable "enable_alarms" {
  description = "Create CloudWatch metric alarms. BILLABLE (~$0.10/alarm/month)."
  type        = bool
  default     = false
}

variable "cpu_alarm_threshold" {
  description = "CPU utilisation percentage that triggers the high-CPU alarm."
  type        = number
  default     = 80

  validation {
    condition     = var.cpu_alarm_threshold > 0 && var.cpu_alarm_threshold <= 100
    error_message = "cpu_alarm_threshold must be between 1 and 100."
  }
}

variable "alarm_email" {
  description = "Optional email address subscribed to the alarm SNS topic. Leave empty to skip the subscription."
  type        = string
  default     = ""

  validation {
    condition     = var.alarm_email == "" || can(regex("^[^@\\s]+@[^@\\s]+\\.[a-zA-Z]{2,}$", var.alarm_email))
    error_message = "alarm_email must be empty or a valid email address."
  }
}

variable "enable_cloudtrail" {
  description = "Create a multi-region CloudTrail trail with log file validation. BILLABLE (S3 storage + management events beyond the free tier)."
  type        = bool
  default     = false
}

variable "cloudtrail_retention_days" {
  description = "Days before CloudTrail log objects expire (after moving to Glacier IR at day 90)."
  type        = number
  default     = 365

  validation {
    condition     = var.cloudtrail_retention_days >= 90
    error_message = "Audit retention below 90 days is not acceptable for a landing zone."
  }
}

variable "cloudtrail_bucket_name" {
  description = "S3 bucket for CloudTrail logs. Required when enable_cloudtrail = true."
  type        = string
  default     = ""

  validation {
    condition     = var.cloudtrail_bucket_name == "" || can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.cloudtrail_bucket_name))
    error_message = "cloudtrail_bucket_name must be empty or a valid S3 bucket name."
  }
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
