###############################################################################
# Terraform remote-state bootstrap (run ONCE per account, manually)
#
# Creates:
#   * S3 bucket for state (versioned, encrypted, public access blocked, TLS-only)
#   * DynamoDB table for state locking (PayPerWrite, on-demand)
#
# This configuration uses the LOCAL backend on purpose: it must exist before any
# other configuration can use the S3 backend. Nothing here is applied by CI.
#
#   cd bootstrap
#   terraform init
#   terraform plan      # review: 5 resources, no compute
#   terraform apply     # ~ $0.03/month for state storage + lock table
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

variable "aws_region" {
  description = "Region for the state bucket and lock table."
  type        = string
  default     = "us-east-1"
}

variable "state_bucket_name" {
  description = "Globally unique bucket name for Terraform state."
  type        = string
  default     = "eawlz-terraform-state"
}

variable "lock_table_name" {
  description = "DynamoDB table used for state locking."
  type        = string
  default     = "eawlz-terraform-locks"
}

variable "tags" {
  description = "Tags applied to bootstrap resources."
  type        = map(string)
  default = {
    Project   = "eawlz"
    ManagedBy = "terraform"
    Purpose   = "terraform-state"
  }
}

provider "aws" {
  region = var.aws_region
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name

  tags = merge(var.tags, { Name = var.state_bucket_name })
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"

    filter {
      prefix = ""
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"

    filter {
      prefix = ""
    }

    # State versions are the recovery mechanism: keep 90 days, not forever.
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "state" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions   = ["s3:*"]
    resources = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state.json

  depends_on = [aws_s3_bucket_public_access_block.state]
}

resource "aws_dynamodb_table" "locks" {
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(var.tags, { Name = var.lock_table_name })
}

output "state_bucket" {
  description = "Bucket to use in each environment's backend.tf."
  value       = aws_s3_bucket.state.id
}

output "lock_table" {
  description = "DynamoDB table for state locking."
  value       = aws_dynamodb_table.locks.name
}

output "backend_snippet" {
  description = "Copy into environments/<env>/backend.tf and adjust the key."
  value       = <<-EOT
    backend "s3" {
      bucket         = "${aws_s3_bucket.state.id}"
      key            = "landing-zone/<env>/terraform.tfstate"
      region         = "${var.aws_region}"
      encrypt        = true
      dynamodb_table = "${aws_dynamodb_table.locks.name}"
    }
  EOT
}
