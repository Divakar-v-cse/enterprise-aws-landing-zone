###############################################################################
# S3 module - encrypted, versioned, non-public object storage
#
# Controls
#  * Block Public Access: all four settings on the bucket itself.
#  * BucketOwnerEnforced: ACLs disabled, owner owns every object (no ACL drift).
#  * Default encryption: SSE-KMS when a CMK is supplied, otherwise SSE-S3.
#  * TLS-only bucket policy: any non-TLS request is explicitly denied.
#  * Versioning + noncurrent version expiry: ransomware/recovery baseline.
#  * Lifecycle: abort incomplete multipart uploads (silent cost leak).
###############################################################################

locals {
  tags = merge(var.tags, {
    Module      = "s3"
    Environment = var.environment
    Purpose     = var.purpose
    DataClass   = var.purpose == "artifacts" ? "internal" : "confidential"
  })

  use_kms = var.kms_key_arn != null
}

resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name

  # Deletion safety: destroy fails while objects/versions remain, unless the
  # operator explicitly opts in. Production buckets are additionally protected
  # by the approval gate in the deployment workflow.
  force_destroy = var.force_destroy

  tags = merge(local.tags, {
    Name = var.bucket_name
  })
}

resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket = aws_s3_bucket.this.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id

  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = local.use_kms ? "aws:kms" : "AES256"
      kms_master_key_id = local.use_kms ? var.kms_key_arn : null
    }

    bucket_key_enabled = local.use_kms ? true : null
  }
}

data "aws_iam_policy_document" "tls_only" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.this.arn,
      "${aws_s3_bucket.this.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid    = "DenyUnencryptedObjectUploads"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:PutObject"]

    resources = ["${aws_s3_bucket.this.arn}/*"]

    # Only evaluate when the client actually sent the header - uploads that rely
    # on bucket default encryption must still succeed.
    condition {
      test     = "Null"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["false"]
    }

    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = local.use_kms ? ["aws:kms"] : ["AES256", "aws:kms"]
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  bucket = aws_s3_bucket.this.id
  policy = data.aws_iam_policy_document.tls_only.json

  depends_on = [aws_s3_bucket_public_access_block.this]
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"

    # Explicit empty prefix (not `filter {}`) so static analysers can attribute
    # the abort rule to the whole bucket.
    filter {
      prefix = ""
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "expire-noncurrent-versions"
    status = var.enable_versioning ? "Enabled" : "Disabled"

    filter {
      prefix = ""
    }

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_expiration_days
    }
  }

  dynamic "rule" {
    for_each = var.transition_to_ia_days > 0 ? [1] : []

    content {
      id     = "transition-to-standard-ia"
      status = "Enabled"

      filter {
        prefix = ""
      }

      transition {
        days          = var.transition_to_ia_days
        storage_class = "STANDARD_IA"
      }
    }
  }

  dynamic "rule" {
    for_each = var.transition_to_glacier_days > 0 ? [1] : []

    content {
      id     = "transition-to-glacier-ir"
      status = "Enabled"

      filter {
        prefix = ""
      }

      transition {
        days          = var.transition_to_glacier_days
        storage_class = "GLACIER_IR"
      }
    }
  }
}

resource "aws_s3_bucket_logging" "this" {
  count = var.enable_access_logging ? 1 : 0

  bucket        = aws_s3_bucket.this.id
  target_bucket = var.access_log_bucket
  target_prefix = "${var.bucket_name}/"
}
