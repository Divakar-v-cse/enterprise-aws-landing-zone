###############################################################################
# S3 module - variables
###############################################################################

variable "bucket_name" {
  description = "Globally unique bucket name, e.g. eawlz-dev-artifacts-123456789012."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name must be 3-63 chars, lowercase letters, numbers, dots and hyphens only."
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

variable "purpose" {
  description = "Bucket purpose, used for tagging and lifecycle tuning (artifacts, logs, backups)."
  type        = string
  default     = "artifacts"

  validation {
    condition     = contains(["artifacts", "logs", "backups", "access-logs"], var.purpose)
    error_message = "purpose must be one of: artifacts, logs, backups, access-logs."
  }
}

variable "kms_key_arn" {
  description = "Customer managed KMS key ARN for SSE-KMS. Null falls back to SSE-S3 (AES256, free)."
  type        = string
  default     = null
}

variable "force_destroy" {
  description = "Allow Terraform to delete a non-empty bucket. Keep false: deletion must be a deliberate, reviewed operation."
  type        = bool
  default     = false
}

variable "enable_versioning" {
  description = "Enable object versioning. Required for point-in-time recovery and ransomware resilience."
  type        = bool
  default     = true
}

variable "noncurrent_version_expiration_days" {
  description = "Days before a non-current object version is permanently deleted."
  type        = number
  default     = 90

  validation {
    condition     = var.noncurrent_version_expiration_days >= 7
    error_message = "Keep at least 7 days of non-current versions for recovery."
  }
}

variable "transition_to_ia_days" {
  description = "Days before objects move to STANDARD_IA. 0 disables the transition."
  type        = number
  default     = 0
}

variable "transition_to_glacier_days" {
  description = "Days before objects move to GLACIER_IR. 0 disables the transition."
  type        = number
  default     = 0
}

variable "enable_access_logging" {
  description = "Write S3 server access logs to var.access_log_bucket. Adds storage cost."
  type        = bool
  default     = false
}

variable "access_log_bucket" {
  description = "Target bucket for server access logs (required when enable_access_logging = true)."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
