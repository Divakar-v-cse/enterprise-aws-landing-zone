terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.40.0, < 7.0.0"
    }
  }

  # ---------------------------------------------------------------------------
  # Backend
  # ---------------------------------------------------------------------------
  # Intentionally omitted: with no backend block Terraform uses the *local*
  # backend, which is what makes zero-cost validation possible without an S3
  # bucket, DynamoDB table or AWS credentials.
  #
  # To switch to remote state:
  #   1. Bootstrap the bucket + lock table:  ../../bootstrap/README.md
  #   2. cp backend.tf.example backend.tf
  #   3. Edit bucket/table/key values (key must be unique per environment).
  #   4. terraform init -migrate-state
  #
  # backend.tf is git-ignored so a misconfigured local backend cannot be committed.
  # ---------------------------------------------------------------------------
}
