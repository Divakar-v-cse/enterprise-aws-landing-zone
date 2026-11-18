###############################################################################
# Security module - customer managed KMS key (encryption baseline)
#
# Why a dedicated module: encryption at rest is a cross-cutting concern used by
# S3, EC2/EBS, CloudWatch Logs, AWS Backup and CloudTrail. One key per
# environment (not one global key) keeps blast radius small: a compromised dev
# principal can never decrypt production data.
#
# Cost: a customer managed key is $1/month plus request charges, so creation is
# optional and disabled in zero-cost mode. When disabled, consumers fall back to
# AWS-managed keys (aws/s3, aws/ebs) or SSE-S3, which are free.
###############################################################################

locals {
  tags = merge(var.tags, {
    Module      = "security"
    Environment = var.environment
    DataClass   = "confidential"
  })

  key_admin_arns = length(var.kms_key_administrators) > 0 ? var.kms_key_administrators : ["arn:aws:iam::${var.aws_account_id}:root"]

  create_key = var.create_kms_key
}

data "aws_iam_policy_document" "kms" {
  count = local.create_key ? 1 : 0

  # Root delegation: allows IAM policies in this account to grant key usage
  # without editing the key policy for every new consumer.
  statement {
    sid       = "EnableIamUserPermissions"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.aws_account_id}:root"]
    }
  }

  statement {
    sid    = "AllowKeyAdministration"
    effect = "Allow"
    actions = [
      "kms:Create*",
      "kms:Describe*",
      "kms:Enable*",
      "kms:List*",
      "kms:Put*",
      "kms:Update*",
      "kms:Revoke*",
      "kms:Disable*",
      "kms:Get*",
      "kms:Delete*",
      "kms:TagResource",
      "kms:UntagResource",
      "kms:ScheduleKeyDeletion",
      "kms:CancelKeyDeletion",
    ]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = local.key_admin_arns
    }
  }

  statement {
    sid    = "AllowKeyUsage"
    effect = "Allow"
    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey",
    ]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = length(var.kms_key_users) > 0 ? var.kms_key_users : ["arn:aws:iam::${var.aws_account_id}:root"]
    }
  }

  statement {
    sid       = "AllowAwsServicesViaGrants"
    effect    = "Allow"
    actions   = ["kms:CreateGrant", "kms:ListGrants", "kms:RevokeGrant"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = local.key_admin_arns
    }

    condition {
      test     = "Bool"
      variable = "kms:GrantIsForAWSResource"
      values   = ["true"]
    }
  }

  statement {
    sid       = "DenyKeyDeletionWithoutMfa"
    effect    = "Deny"
    actions   = ["kms:ScheduleKeyDeletion", "kms:DisableKey"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    condition {
      test     = "BoolIfExists"
      variable = "aws:MultiFactorAuthPresent"
      values   = ["false"]
    }
  }
}

resource "aws_kms_key" "this" {
  count = local.create_key ? 1 : 0

  description             = "${var.name_prefix} landing zone data encryption key"
  deletion_window_in_days = var.kms_deletion_window_days
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.kms[0].json

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-data-key"
  })
}

resource "aws_kms_alias" "this" {
  count = local.create_key ? 1 : 0

  name          = "alias/${var.name_prefix}-data"
  target_key_id = aws_kms_key.this[0].key_id
}
