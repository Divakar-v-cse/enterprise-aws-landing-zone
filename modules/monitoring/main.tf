###############################################################################
# Monitoring module - logs, dashboard, optional alarms, optional CloudTrail
#
# Observability model
#   logs      : one retained log group per stream class (app, system, audit)
#   dashboard : single pane of glass, free
#   alarms    : per-instance CPU + status checks (opt-in, billable)
#   audit     : multi-region CloudTrail with log file validation (opt-in)
###############################################################################

locals {
  tags = merge(var.tags, {
    Module      = "monitoring"
    Environment = var.environment
  })

  audit_log_groups = [for n in var.log_group_names : n if can(regex("audit|security|trail", n))]
  app_log_groups   = [for n in var.log_group_names : n if !can(regex("audit|security|trail", n))]

  # `count` must be known at plan time, so it is derived from instance_count
  # (a plan-known number) rather than from the instance ID list (unknown until
  # apply). The IDs themselves may stay unknown inside the resource arguments.
  alarm_count = var.enable_alarms ? var.instance_count : 0

  # A dashboard widget needs at least one metric; fall back to the account-wide
  # aggregate so the dashboard stays valid before any instance exists.
  cpu_metrics = var.instance_count > 0 ? [
    for i in range(var.instance_count) : ["AWS/EC2", "CPUUtilization", "InstanceId", element(var.instance_ids, i)]
  ] : [["AWS/EC2", "CPUUtilization"]]

  network_metrics = var.instance_count > 0 ? [
    for i in range(var.instance_count) : ["AWS/EC2", "NetworkIn", "InstanceId", element(var.instance_ids, i)]
  ] : [["AWS/EC2", "NetworkIn"]]
}

resource "aws_cloudwatch_log_group" "app" {
  for_each = toset(local.app_log_groups)

  name              = each.value
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = merge(local.tags, {
    Name = each.value
    Tier = "application"
  })
}

resource "aws_cloudwatch_log_group" "audit" {
  for_each = toset(local.audit_log_groups)

  name              = each.value
  retention_in_days = var.audit_log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = merge(local.tags, {
    Name = each.value
    Tier = "audit"
  })
}

# -----------------------------------------------------------------------------
# Dashboard (free) - one pane per environment
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = "${var.name_prefix}-overview"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "EC2 CPU utilisation (${var.environment})"
          region  = var.aws_region
          view    = "timeSeries"
          stat    = "Average"
          period  = 300
          metrics = local.cpu_metrics
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Network in/out (${var.environment})"
          region  = var.aws_region
          view    = "timeSeries"
          stat    = "Sum"
          period  = 300
          metrics = local.network_metrics
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 6
        width  = 24
        height = 6
        properties = {
          title  = "Recent application errors"
          region = var.aws_region
          query  = "SOURCE '${try(local.app_log_groups[0], "/eawlz/app")}' | fields @timestamp, @message | filter @message like /ERROR|Exception/ | sort @timestamp desc | limit 20"
          view   = "table"
        }
      },
    ]
  })
}

# -----------------------------------------------------------------------------
# Alarms - OPTIONAL and BILLABLE
# -----------------------------------------------------------------------------
resource "aws_sns_topic" "alarms" {
  count = var.enable_alarms ? 1 : 0

  name = "${var.name_prefix}-alarms"
  # AWS-managed SNS key is free and still encrypts at rest; a CMK is used when
  # the environment provides one.
  kms_master_key_id = var.kms_key_arn != null ? var.kms_key_arn : "alias/aws/sns"

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-alarms"
  })
}

resource "aws_sns_topic_subscription" "alarm_email" {
  count = var.enable_alarms && var.alarm_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.alarms[0].arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  count = local.alarm_count

  alarm_name          = "${var.name_prefix}-cpu-high-${count.index + 1}"
  alarm_description   = "CPU above ${var.cpu_alarm_threshold}% for 10 minutes on instance ${count.index + 1}"
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.cpu_alarm_threshold
  evaluation_periods  = 2
  period              = 300
  treat_missing_data  = "notBreaching"

  dimensions = {
    InstanceId = element(var.instance_ids, count.index)
  }

  alarm_actions = aws_sns_topic.alarms[*].arn

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-cpu-high-${count.index + 1}"
  })
}

resource "aws_cloudwatch_metric_alarm" "status_check_failed" {
  count = local.alarm_count

  alarm_name          = "${var.name_prefix}-status-check-${count.index + 1}"
  alarm_description   = "Instance status check failed for instance ${count.index + 1}"
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  statistic           = "Maximum"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 2
  period              = 60
  treat_missing_data  = "notBreaching"

  dimensions = {
    InstanceId = element(var.instance_ids, count.index)
  }

  alarm_actions = aws_sns_topic.alarms[*].arn

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-status-check-${count.index + 1}"
  })
}

# -----------------------------------------------------------------------------
# CloudTrail - OPTIONAL, multi-region, tamper-evident
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "cloudtrail" {
  count = var.enable_cloudtrail ? 1 : 0

  bucket = var.cloudtrail_bucket_name

  tags = merge(local.tags, {
    Name    = var.cloudtrail_bucket_name
    Purpose = "cloudtrail"
  })
}

resource "aws_s3_bucket_public_access_block" "cloudtrail" {
  count = var.enable_cloudtrail ? 1 : 0

  bucket = aws_s3_bucket.cloudtrail[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cloudtrail" {
  count = var.enable_cloudtrail ? 1 : 0

  bucket = aws_s3_bucket.cloudtrail[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.kms_key_arn != null ? "aws:kms" : "AES256"
      kms_master_key_id = var.kms_key_arn
    }
  }
}

resource "aws_s3_bucket_versioning" "cloudtrail" {
  count = var.enable_cloudtrail ? 1 : 0

  bucket = aws_s3_bucket.cloudtrail[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "cloudtrail" {
  count = var.enable_cloudtrail ? 1 : 0

  bucket = aws_s3_bucket.cloudtrail[0].id

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
    id     = "archive-and-expire-audit-logs"
    status = "Enabled"

    filter {
      prefix = ""
    }

    # Audit logs are read rarely but must be retained: cold storage after 90 days,
    # hard expiry only after the configured compliance window.
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }

    expiration {
      days = var.cloudtrail_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

data "aws_iam_policy_document" "cloudtrail_bucket" {
  count = var.enable_cloudtrail ? 1 : 0

  statement {
    sid    = "AWSCloudTrailAclCheck"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.cloudtrail[0].arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = ["arn:aws:cloudtrail:${var.aws_region}:${var.aws_account_id}:trail/${var.name_prefix}-trail"]
    }
  }

  statement {
    sid    = "AWSCloudTrailWrite"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.cloudtrail[0].arn}/AWSLogs/${var.aws_account_id}/*"]

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = ["arn:aws:cloudtrail:${var.aws_region}:${var.aws_account_id}:trail/${var.name_prefix}-trail"]
    }
  }

  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions   = ["s3:*"]
    resources = [aws_s3_bucket.cloudtrail[0].arn, "${aws_s3_bucket.cloudtrail[0].arn}/*"]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "cloudtrail" {
  count = var.enable_cloudtrail ? 1 : 0

  bucket = aws_s3_bucket.cloudtrail[0].id
  policy = data.aws_iam_policy_document.cloudtrail_bucket[0].json

  depends_on = [aws_s3_bucket_public_access_block.cloudtrail]
}

resource "aws_cloudtrail" "this" {
  count = var.enable_cloudtrail ? 1 : 0

  name                          = "${var.name_prefix}-trail"
  s3_bucket_name                = aws_s3_bucket.cloudtrail[0].id
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true
  kms_key_id                    = var.kms_key_arn

  # Data events are high volume and expensive - management events only by default.
  advanced_event_selector {
    name = "Management events only"

    field_selector {
      field  = "eventCategory"
      equals = ["Management"]
    }
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-trail"
  })

  depends_on = [aws_s3_bucket_policy.cloudtrail]
}
