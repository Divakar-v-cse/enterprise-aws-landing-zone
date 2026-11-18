###############################################################################
# EC2 module - variables
#
# Hardening default: no SSH key, no public IP, IMDSv2 required, encrypted root
# volume, detailed monitoring off (cost), SSM-only administrative access.
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

variable "aws_region" {
  description = "AWS region written into the instance bootstrap configuration."
  type        = string
  default     = "us-east-1"
}

variable "instance_count" {
  description = "Number of application instances. 0 = zero-cost validation mode (no instances, no compute charges)."
  type        = number
  default     = 0

  validation {
    condition     = var.instance_count >= 0 && var.instance_count <= 20
    error_message = "instance_count must be between 0 and 20."
  }
}

variable "ami_id" {
  description = "Explicit AMI ID. When empty and instance_count > 0, the latest Amazon Linux 2023 AMI is resolved at plan time."
  type        = string
  default     = ""

  validation {
    condition     = var.ami_id == "" || can(regex("^ami-[0-9a-f]{8,17}$", var.ami_id))
    error_message = "ami_id must be empty or a valid AMI ID (ami-xxxxxxxx)."
  }
}

variable "instance_type" {
  description = "Instance type. t3.micro is the cost baseline for dev; m7g/t3 for staging; m7i/c7i for production."
  type        = string
  default     = "t3.micro"

  validation {
    condition     = can(regex("^[a-z][0-9][a-z]?\\.[a-z0-9]+$", var.instance_type))
    error_message = "instance_type must look like t3.micro or m7i.large."
  }
}

variable "subnet_ids" {
  description = "Private subnet IDs where instances are placed (spread round-robin across AZs)."
  type        = list(string)

  validation {
    condition     = length(var.subnet_ids) > 0
    error_message = "At least one private subnet ID is required."
  }
}

variable "security_group_ids" {
  description = "Security group IDs applied to the instances."
  type        = list(string)

  validation {
    condition     = length(var.security_group_ids) > 0
    error_message = "At least one security group ID is required."
  }
}

variable "instance_profile_name" {
  description = "IAM instance profile name providing the workload role."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key for EBS encryption. Null uses the AWS-managed aws/ebs key (free)."
  type        = string
  default     = null
}

variable "root_volume_size" {
  description = "Root EBS volume size in GiB (gp3)."
  type        = number
  default     = 20

  validation {
    condition     = var.root_volume_size >= 8 && var.root_volume_size <= 1000
    error_message = "root_volume_size must be between 8 and 1000 GiB."
  }
}

variable "enable_detailed_monitoring" {
  description = "1-minute CloudWatch metrics. BILLABLE - disabled by default."
  type        = bool
  default     = false
}

variable "log_group_name" {
  description = "CloudWatch log group name the workload writes application logs to."
  type        = string
  default     = "/eawlz/dev/app"
}

variable "app_port" {
  description = "Port the application listens on (written into the instance environment file)."
  type        = number
  default     = 8080
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
