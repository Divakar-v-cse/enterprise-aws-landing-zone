###############################################################################
# IAM module - variables
#
# Principles enforced:
#  * No IAM users, no access keys, no console logins are created anywhere.
#  * Workload access is via instance roles (EC2 -> STS temporary credentials).
#  * CI access is via GitHub OIDC federation (no long-lived AWS secrets in CI).
#  * Every role carries a permission boundary as a second, independent control.
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
  description = "AWS account ID used to build role and provider ARNs. Placeholder acceptable for offline validation."
  type        = string
  default     = "111122223333"

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be a 12-digit AWS account ID."
  }
}

variable "approved_regions" {
  description = "Regions where the workload and CI roles may operate. Used in permission boundary region guardrails."
  type        = list(string)
  default     = ["us-east-1"]

  validation {
    condition     = length(var.approved_regions) > 0
    error_message = "At least one approved region is required."
  }
}

variable "artifact_bucket_arn" {
  description = "ARN of the S3 bucket the workload may read configuration from."
  type        = string
  default     = "arn:aws:s3:::eawlz-dev-artifacts"

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:s3:::[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.artifact_bucket_arn))
    error_message = "artifact_bucket_arn must be a valid S3 bucket ARN."
  }
}

variable "log_group_arn" {
  description = "ARN of the CloudWatch log group the workload may write to."
  type        = string
  default     = "arn:aws:logs:us-east-1:111122223333:log-group:/eawlz/dev/app"
}

variable "metric_namespace" {
  description = "CloudWatch namespace the workload may publish custom metrics to."
  type        = string
  default     = "EAWLZ/Workload"
}

variable "ssm_parameter_arn_prefix" {
  description = "SSM parameter ARN prefix the workload may read (no wildcard suffix)."
  type        = string
  default     = "arn:aws:ssm:us-east-1:111122223333:parameter/eawlz/dev/app"
}

variable "create_permission_boundary" {
  description = "Create the customer managed permission boundary policy and attach it to the workload role."
  type        = bool
  default     = true
}

variable "create_ci_role" {
  description = "Create the GitHub Actions OIDC role and its scoped deployment policy."
  type        = bool
  default     = true
}

variable "create_oidc_provider" {
  description = "Create the GitHub OIDC identity provider. Set false if the account already has token.actions.githubusercontent.com (only one is allowed per account)."
  type        = bool
  default     = false
}

variable "github_repository" {
  description = "GitHub repository in owner/name form, used to scope the OIDC trust policy."
  type        = string
  default     = "example-org/enterprise-aws-landing-zone"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must be in owner/name form."
  }
}

variable "github_oidc_subjects" {
  description = "Exact or wildcard `sub` claims allowed to assume the CI role. Prefer ref/environment scoping over `repo:*`."
  type        = list(string)
  default     = []

  validation {
    condition     = !anytrue([for s in var.github_oidc_subjects : s == "repo:*"])
    error_message = "Wildcard repo:* subjects are not allowed - scope the trust policy to a repository, branch or environment."
  }
}

variable "state_bucket_arn" {
  description = "ARN of the Terraform remote state bucket the CI role may read/write."
  type        = string
  default     = "arn:aws:s3:::eawlz-terraform-state"
}

variable "lock_table_arn" {
  description = "ARN of the DynamoDB state lock table the CI role may use."
  type        = string
  default     = "arn:aws:dynamodb:us-east-1:111122223333:table/eawlz-terraform-locks"
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
