###############################################################################
# Example: smallest useful composition of the networking module.
#
#   cd examples/minimal-vpc
#   terraform init && terraform plan     # offline, 14 resources, $0
#
# Zero-cost: no NAT Gateway, no Flow Logs, no instances. This example exists to
# show the module contract without the environment wiring.
###############################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.40.0, < 7.0.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

variable "aws_region" {
  description = "Region for the example."
  type        = string
  default     = "us-east-1"
}

module "networking" {
  source = "../../modules/networking"

  name_prefix        = "eawlz-example"
  environment        = "dev"
  aws_region         = var.aws_region
  vpc_cidr           = "10.99.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b"]
  az_count           = 2

  public_subnet_cidrs  = ["10.99.0.0/20", "10.99.16.0/20"]
  private_subnet_cidrs = ["10.99.128.0/20", "10.99.144.0/20"]

  enable_nat_gateway = false
  enable_flow_logs   = false

  tags = {
    Project     = "eawlz"
    Environment = "dev"
    ManagedBy   = "terraform"
    Owner       = "platform-engineering"
    CostCenter  = "CC-DEV-001"
  }
}

output "vpc_id" {
  description = "Created VPC."
  value       = module.networking.vpc_id
}

output "private_subnets" {
  description = "Private subnet IDs."
  value       = module.networking.private_subnet_ids
}
