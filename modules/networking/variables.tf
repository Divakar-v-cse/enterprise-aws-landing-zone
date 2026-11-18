###############################################################################
# Networking module - variables
#
# Design notes
#  * Availability zones are injected as a variable instead of being discovered
#    with a data source. This keeps `terraform plan` fully offline-capable for
#    zero-cost validation (no AWS credentials, no API calls, no state refresh).
#  * Every billable resource (NAT Gateway, Elastic IP, VPC Flow Logs) is gated
#    behind a variable that defaults to `false`.
###############################################################################

variable "name_prefix" {
  description = "Prefix applied to every resource name, e.g. eawlz-dev."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,30}$", var.name_prefix))
    error_message = "name_prefix must be 2-31 chars, lowercase alphanumeric or hyphen, starting with a letter or digit."
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
  description = "AWS region, used for the regional S3 gateway endpoint service name."
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be a valid IPv4 CIDR block."
  }
}

variable "availability_zones" {
  description = "Availability zones used for the multi-AZ layout. Must contain at least az_count entries."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]

  validation {
    condition     = length(var.availability_zones) >= 2
    error_message = "At least two availability zones are required for a multi-AZ design."
  }
}

variable "az_count" {
  description = "Number of availability zones to spread subnets across."
  type        = number
  default     = 3

  validation {
    condition     = var.az_count >= 1 && var.az_count <= 6
    error_message = "az_count must be between 1 and 6."
  }
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public (ingress-facing) subnets, one per AZ."
  type        = list(string)
  default     = ["10.0.0.0/20", "10.0.16.0/20", "10.0.32.0/20"]

  validation {
    condition     = length(var.public_subnet_cidrs) >= 1 && alltrue([for c in var.public_subnet_cidrs : can(cidrnetmask(c))])
    error_message = "public_subnet_cidrs must contain at least one valid IPv4 CIDR block."
  }
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private (workload) subnets, one per AZ."
  type        = list(string)
  default     = ["10.0.128.0/20", "10.0.144.0/20", "10.0.160.0/20"]

  validation {
    condition     = length(var.private_subnet_cidrs) >= 1 && alltrue([for c in var.private_subnet_cidrs : can(cidrnetmask(c))])
    error_message = "private_subnet_cidrs must contain at least one valid IPv4 CIDR block."
  }
}

variable "enable_dns_support" {
  description = "Enable DNS resolution inside the VPC."
  type        = bool
  default     = true
}

variable "enable_dns_hostnames" {
  description = "Enable DNS hostnames inside the VPC (required for private DNS names and VPC endpoints)."
  type        = bool
  default     = true
}

variable "enable_nat_gateway" {
  description = "Create NAT Gateway(s) for private subnet egress. BILLABLE (~$0.045/hour + data processing). Keep false in zero-cost mode."
  type        = bool
  default     = false
}

variable "single_nat_gateway" {
  description = "Use one shared NAT Gateway instead of one per AZ. Cheap but a single point of failure - dev only."
  type        = bool
  default     = true
}

variable "enable_flow_logs" {
  description = "Enable VPC Flow Logs to CloudWatch Logs. Billable (log ingestion + storage)."
  type        = bool
  default     = false
}

variable "flow_logs_retention_days" {
  description = "Retention for the VPC Flow Logs CloudWatch log group."
  type        = number
  default     = 30
}

variable "enable_s3_gateway_endpoint" {
  description = "Create a free S3 gateway VPC endpoint so private workloads reach S3 without NAT."
  type        = bool
  default     = true
}

variable "app_port" {
  description = "Application port allowed by the application security group."
  type        = number
  default     = 8080

  validation {
    condition     = var.app_port > 0 && var.app_port <= 65535
    error_message = "app_port must be a valid TCP port."
  }
}

variable "db_port" {
  description = "Database port allowed from the application security group only."
  type        = number
  default     = 5432
}

variable "allowed_ingress_cidrs" {
  description = "CIDR blocks allowed to reach the application port. Empty list = no public ingress (SSM-only access). Never use 0.0.0.0/0 in production."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
