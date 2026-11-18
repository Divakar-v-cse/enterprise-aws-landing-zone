###############################################################################
# IAM module - least-privilege workload role, permission boundary, GitHub OIDC
#
# Threat model this module addresses
#  1. Over-privileged application roles          -> scoped policy + boundary
#  2. Long-lived credentials in the workload      -> instance role, IMDSv2 only
#  3. Long-lived credentials in CI/CD            -> GitHub OIDC federation
#  4. Credential misuse from a compromised app   -> explicit deny guardrails
#  5. Lateral movement into IAM                  -> iam:* denied by boundary
###############################################################################

locals {
  tags = merge(var.tags, {
    Module      = "iam"
    Environment = var.environment
  })

  # Never fall back to "repo:*". Explicit ref/environment scoping only.
  allowed_subjects = length(var.github_oidc_subjects) > 0 ? var.github_oidc_subjects : [
    "repo:${var.github_repository}:ref:refs/heads/main",
    "repo:${var.github_repository}:environment:production",
    "repo:${var.github_repository}:environment:staging",
  ]

  boundary_arn = try(aws_iam_policy.permission_boundary[0].arn, null)
}

# -----------------------------------------------------------------------------
# Workload (EC2) role
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    sid     = "AllowEc2ServiceToAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2" {
  name                 = "${var.name_prefix}-ec2-app"
  description          = "Least-privilege role assumed by ${var.environment} application instances via IMDSv2"
  assume_role_policy   = data.aws_iam_policy_document.ec2_assume_role.json
  permissions_boundary = local.boundary_arn
  max_session_duration = 3600

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-ec2-app"
  })
}

resource "aws_iam_policy" "ec2_app" {
  name        = "${var.name_prefix}-ec2-app-policy"
  description = "Scoped S3/CloudWatch/SSM permissions for the ${var.environment} application tier"
  policy = templatefile("${path.module}/policies/ec2-app-policy.json.tftpl", {
    artifact_bucket_arn      = var.artifact_bucket_arn
    log_group_arn            = var.log_group_arn
    metric_namespace         = var.metric_namespace
    ssm_parameter_arn_prefix = var.ssm_parameter_arn_prefix
  })

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-ec2-app-policy"
  })
}

resource "aws_iam_role_policy_attachment" "ec2_app" {
  role       = aws_iam_role.ec2.name
  policy_arn = aws_iam_policy.ec2_app.arn
}

# AWS managed policy required for Session Manager (no inbound SSH, no bastion).
# It only covers SSM messaging/metadata - it does not grant infrastructure access.
resource "aws_iam_role_policy_attachment" "ec2_ssm_core" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${var.name_prefix}-ec2-app"
  role = aws_iam_role.ec2.name

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-ec2-app"
  })
}

# -----------------------------------------------------------------------------
# Permission boundary - independent ceiling applied to the workload role
# -----------------------------------------------------------------------------
resource "aws_iam_policy" "permission_boundary" {
  count = var.create_permission_boundary ? 1 : 0

  name        = "${var.name_prefix}-workload-boundary"
  description = "Permission boundary: workload services only, no IAM, no audit tampering, approved regions only"
  policy = templatefile("${path.module}/policies/permission-boundary.json.tftpl", {
    approved_regions = var.approved_regions
  })

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-workload-boundary"
  })
}

# -----------------------------------------------------------------------------
# GitHub Actions OIDC - no long-lived AWS access keys in CI/CD
# -----------------------------------------------------------------------------
resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_ci_role && var.create_oidc_provider ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-github-oidc"
  })
}

resource "aws_iam_role" "ci" {
  count = var.create_ci_role ? 1 : 0

  name        = "${var.name_prefix}-github-ci"
  description = "Role assumed by GitHub Actions via OIDC for ${var.environment} Terraform plans and approved applies"
  assume_role_policy = templatefile("${path.module}/policies/github-oidc-trust.json.tftpl", {
    aws_account_id   = var.aws_account_id
    allowed_subjects = local.allowed_subjects
  })
  max_session_duration = 3600

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-github-ci"
  })
}

resource "aws_iam_policy" "ci_deploy" {
  count = var.create_ci_role ? 1 : 0

  name        = "${var.name_prefix}-ci-terraform-deploy"
  description = "Scoped Terraform deployment permissions for ${var.environment} (state access, networking, compute, storage, logs)"
  policy = templatefile("${path.module}/policies/ci-terraform-deploy-policy.json.tftpl", {
    state_bucket_arn = var.state_bucket_arn
    lock_table_arn   = var.lock_table_arn
    approved_regions = var.approved_regions
  })

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-ci-terraform-deploy"
  })
}

resource "aws_iam_role_policy_attachment" "ci_deploy" {
  count = var.create_ci_role ? 1 : 0

  role       = aws_iam_role.ci[0].name
  policy_arn = aws_iam_policy.ci_deploy[0].arn
}
