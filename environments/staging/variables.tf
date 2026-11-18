###############################################################################
# Staging environment - variables
#
# Staging mirrors the production topology (NAT, flow logs, alarms, CloudTrail,
# disabled, so `terraform init && terraform validate && terraform plan` run
# `zero_cost_mode` only after a cost review.
###############################################################################

# -----------------------------------------------------------------------------
# Identity
# -----------------------------------------------------------------------------
variable "project_name" {
  description = "Short project identifier used in every resource name."
  type        = string
  default     = "eawlz"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.project_name))
    error_message = "project_name must be 2-16 chars, lowercase alphanumeric or hyphen."
  }
}

variable "environment" {
  description = "Environment name. Fixed per directory - do not override."
  type        = string
  default     = "staging"

  validation {
    condition     = var.environment == "staging"
    error_message = "This directory provisions the staging environment only."
  }
}

variable "aws_region" {
  description = "Primary AWS region."
  type        = string
  default     = "us-east-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.aws_region))
    error_message = "aws_region must look like us-east-1."
  }
}

variable "aws_account_id" {
  description = "Target AWS account ID. The placeholder is safe for offline validation and makes bucket names deterministic."
  type        = string
  default     = "111122223333"

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be a 12-digit AWS account ID."
  }
}

variable "owner" {
  description = "Owning team or individual, used for the Owner tag."
  type        = string
  default     = "platform-engineering"
}

variable "cost_center" {
  description = "Cost centre code for chargeback reports."
  type        = string
  default     = "CC-STG-001"
}

# -----------------------------------------------------------------------------
# Cost guard rails
# -----------------------------------------------------------------------------
variable "zero_cost_mode" {
  description = "When true, every billable resource is forced off regardless of the other flags. Keep true for local validation."
  type        = bool
  default     = true
}

variable "offline_plan_mode" {
  description = "Skip AWS credential/account validation so plan works with no credentials. Must be false for real deployments."
  type        = bool
  default     = true
}

variable "enable_nat_gateway" {
  description = "Enable NAT Gateway egress. Ignored when zero_cost_mode = true (~$32/month per NAT)."
  type        = bool
  default     = false
}

variable "enable_flow_logs" {
  description = "Enable VPC Flow Logs. Ignored when zero_cost_mode = true."
  type        = bool
  default     = false
}

variable "enable_kms_key" {
  description = "Create a customer managed KMS key. Ignored when zero_cost_mode = true (~$1/key/month)."
  type        = bool
  default     = false
}

variable "enable_alarms" {
  description = "Create CloudWatch alarms. Ignored when zero_cost_mode = true."
  type        = bool
  default     = false
}

variable "enable_cloudtrail" {
  description = "Create a CloudTrail trail. Ignored when zero_cost_mode = true."
  type        = bool
  default     = false
}

variable "enable_backup_plan" {
  description = "Create the AWS Backup plan. Ignored when zero_cost_mode = true (backup storage is billable)."
  type        = bool
  default     = false
}

# -----------------------------------------------------------------------------
# Compute
# -----------------------------------------------------------------------------
variable "instance_count" {
  description = "Number of application instances. Forced to 0 when zero_cost_mode = true."
  type        = number
  default     = 0

  validation {
    condition     = var.instance_count >= 0 && var.instance_count <= 10
    error_message = "staging supports 0-10 instances."
  }
}

variable "instance_type" {
  description = "Instance type for staging (t3.small baseline)."
  type        = string
  default     = "t3.small"

  validation {
    condition     = can(regex("^[a-z][0-9][a-z]?\\.[a-z0-9]+$", var.instance_type))
    error_message = "instance_type must look like t3.micro."
  }
}

variable "root_volume_size" {
  description = "Root EBS volume size in GiB."
  type        = number
  default     = 30
}

# -----------------------------------------------------------------------------
# Networking
# -----------------------------------------------------------------------------
variable "az_count" {
  description = "Number of availability zones to use (2-3 for dev)."
  type        = number
  default     = 3

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be 2 or 3."
  }
}

variable "single_nat_gateway" {
  description = "Share one NAT Gateway across AZs. True = cheaper, single point of failure."
  type        = bool
  default     = true
}

variable "s3_transition_to_ia_days" {
  description = "Days before artifacts move to STANDARD_IA (0 disables)."
  type        = number
  default     = 30
}

variable "s3_noncurrent_version_expiration_days" {
  description = "Days to keep non-current object versions."
  type        = number
  default     = 30
}

variable "cpu_alarm_threshold" {
  description = "CPU percentage that triggers the high-CPU alarm."
  type        = number
  default     = 85

  validation {
    condition     = var.cpu_alarm_threshold > 0 && var.cpu_alarm_threshold <= 100
    error_message = "cpu_alarm_threshold must be between 1 and 100."
  }
}

# -----------------------------------------------------------------------------
# Backup retention
# -----------------------------------------------------------------------------
variable "backup_daily_retention_days" {
  description = "Daily recovery point retention."
  type        = number
  default     = 7
}

variable "backup_weekly_retention_days" {
  description = "Weekly recovery point retention."
  type        = number
  default     = 30
}

variable "backup_monthly_retention_days" {
  description = "Monthly recovery point retention."
  type        = number
  default     = 30
}

variable "vpc_cidr" {
  description = "VPC CIDR for staging (10.20.0.0/16 keeps dev/staging/prod distinct)."
  type        = string
  default     = "10.20.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be a valid IPv4 CIDR."
  }
}

variable "availability_zones" {
  description = "Availability zones for the multi-AZ layout."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDR blocks (one per AZ)."
  type        = list(string)
  default     = ["10.20.0.0/20", "10.20.16.0/20", "10.20.32.0/20"]
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDR blocks (one per AZ)."
  type        = list(string)
  default     = ["10.20.128.0/20", "10.20.144.0/20", "10.20.160.0/20"]
}

variable "allowed_ingress_cidrs" {
  description = "CIDRs allowed to reach the application port. Empty = SSM-only access (recommended)."
  type        = list(string)
  default     = []
}

variable "app_port" {
  description = "Application listening port."
  type        = number
  default     = 8080
}

# -----------------------------------------------------------------------------
# Observability
# -----------------------------------------------------------------------------
variable "log_retention_days" {
  description = "Application log retention in days."
  type        = number
  default     = 30
}

variable "alarm_email" {
  description = "Optional email for alarm notifications (requires enable_alarms)."
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# CI/CD
# -----------------------------------------------------------------------------
variable "github_repository" {
  description = "GitHub repository (owner/name) allowed to assume the CI role via OIDC."
  type        = string
  default     = "example-org/enterprise-aws-landing-zone"
}

variable "create_ci_role" {
  description = "Create the GitHub OIDC role in this environment."
  type        = bool
  default     = true
}

variable "state_bucket_name" {
  description = "Remote state bucket used by CI (bootstrap output). Does not need to exist for local validation."
  type        = string
  default     = "eawlz-terraform-state"
}
