###############################################################################
# Security module - variables (KMS key management + encryption baseline)
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
  description = "AWS account ID used in key policies. Placeholder values are acceptable for offline validation only."
  type        = string
  default     = "111122223333"

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be a 12-digit AWS account ID."
  }
}

variable "create_kms_key" {
  description = "Create a customer managed KMS key. BILLABLE ($1/key/month + request charges) - false in zero-cost mode, true in production."
  type        = bool
  default     = false
}

variable "kms_deletion_window_days" {
  description = "Waiting period before a scheduled KMS key deletion completes (7-30 days)."
  type        = number
  default     = 30

  validation {
    condition     = var.kms_deletion_window_days >= 7 && var.kms_deletion_window_days <= 30
    error_message = "kms_deletion_window_days must be between 7 and 30."
  }
}

variable "kms_key_administrators" {
  description = "IAM principal ARNs allowed to administer the key (key policy delegation). Defaults to the account root when empty."
  type        = list(string)
  default     = []
}

variable "kms_key_users" {
  description = "IAM principal ARNs allowed to use the key for encrypt/decrypt."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
