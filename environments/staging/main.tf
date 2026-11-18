###############################################################################
# ENVIRONMENT composition root (staging)
#
# Wiring is identical across dev / staging / production on purpose: security
# controls must not drift between environments. Every difference - CIDR plan,
# instance count/type, NAT topology, retention, billable toggles - lives in
# terraform.tfvars, so a reviewer can diff one small file per environment.
#
# This file creates no resources directly; it only composes reusable modules.
#
# Zero-cost mode: `zero_cost_mode = true` (default) forces every billable
# resource off, so validation and planning are free and require no credentials.
###############################################################################

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  # Single switch that gates every billable resource. Explicit opt-in required.
  billable = !var.zero_cost_mode

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Owner       = var.owner
    CostCenter  = var.cost_center
    Repository  = "enterprise-aws-landing-zone"
    DataClass   = var.environment == "production" ? "confidential" : "internal"
    Backup      = "true"
  }

  app_log_group   = "/${local.name_prefix}/app"
  audit_log_group = "/${local.name_prefix}/audit"
  sys_log_group   = "/${local.name_prefix}/system"

  artifact_bucket_name = "${local.name_prefix}-artifacts-${var.aws_account_id}"
  cloudtrail_bucket    = "${local.name_prefix}-cloudtrail-${var.aws_account_id}"

  # Effective (post-guard) settings - all plan-time known so that every `count`
  # in the modules is resolvable during plan.
  effective_instance_count = local.billable ? var.instance_count : 0
  effective_nat            = local.billable && var.enable_nat_gateway
  effective_flow_logs      = local.billable && var.enable_flow_logs
  effective_kms            = local.billable && var.enable_kms_key
  effective_alarms         = local.billable && var.enable_alarms
  effective_cloudtrail     = local.billable && var.enable_cloudtrail
  effective_backup_plan    = local.billable && var.enable_backup_plan

  state_bucket_arn = "arn:aws:s3:::${var.state_bucket_name}"
  lock_table_arn   = "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}-terraform-locks"
}

# -----------------------------------------------------------------------------
# 1. Encryption baseline (KMS)
# -----------------------------------------------------------------------------
module "security" {
  source = "../../modules/security"

  name_prefix              = local.name_prefix
  environment              = var.environment
  aws_account_id           = var.aws_account_id
  create_kms_key           = local.effective_kms
  kms_deletion_window_days = 7 # short window for non-production key hygiene
  tags                     = local.common_tags
}

# -----------------------------------------------------------------------------
# 2. Network foundation
# -----------------------------------------------------------------------------
module "networking" {
  source = "../../modules/networking"

  name_prefix        = local.name_prefix
  environment        = var.environment
  aws_region         = var.aws_region
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  az_count           = var.az_count

  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs

  enable_nat_gateway = local.effective_nat
  single_nat_gateway = var.single_nat_gateway
  enable_flow_logs   = local.effective_flow_logs

  app_port              = var.app_port
  allowed_ingress_cidrs = var.allowed_ingress_cidrs

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# 3. Object storage
# -----------------------------------------------------------------------------
module "s3" {
  source = "../../modules/s3"

  bucket_name       = local.artifact_bucket_name
  environment       = var.environment
  purpose           = "artifacts"
  kms_key_arn       = module.security.kms_key_arn
  enable_versioning = true
  force_destroy     = false

  transition_to_ia_days              = var.s3_transition_to_ia_days
  noncurrent_version_expiration_days = var.s3_noncurrent_version_expiration_days

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# 4. IAM - workload role, permission boundary, CI OIDC role
# -----------------------------------------------------------------------------
module "iam" {
  source = "../../modules/iam"

  name_prefix              = local.name_prefix
  environment              = var.environment
  aws_account_id           = var.aws_account_id
  aws_region               = var.aws_region
  approved_regions         = [var.aws_region]
  artifact_bucket_arn      = module.s3.bucket_arn
  log_group_arn            = "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:${local.app_log_group}"
  metric_namespace         = "EAWLZ/${title(var.environment)}"
  ssm_parameter_arn_prefix = "arn:aws:ssm:${var.aws_region}:${var.aws_account_id}:parameter/${local.name_prefix}/app"

  create_permission_boundary = true
  create_ci_role             = var.create_ci_role
  create_oidc_provider       = false # once per account, not once per environment
  github_repository          = var.github_repository
  state_bucket_arn           = local.state_bucket_arn
  lock_table_arn             = local.lock_table_arn

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# 5. Compute (0 instances in zero-cost mode)
# -----------------------------------------------------------------------------
module "ec2" {
  source = "../../modules/ec2"

  name_prefix    = local.name_prefix
  environment    = var.environment
  aws_region     = var.aws_region
  instance_count = local.effective_instance_count
  instance_type  = var.instance_type

  subnet_ids            = module.networking.private_subnet_ids
  security_group_ids    = [module.networking.app_security_group_id]
  instance_profile_name = module.iam.ec2_instance_profile_name
  kms_key_arn           = module.security.kms_key_arn

  root_volume_size = var.root_volume_size
  log_group_name   = local.app_log_group
  app_port         = var.app_port

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# 6. Observability
# -----------------------------------------------------------------------------
module "monitoring" {
  source = "../../modules/monitoring"

  name_prefix        = local.name_prefix
  environment        = var.environment
  aws_account_id     = var.aws_account_id
  aws_region         = var.aws_region
  log_group_names    = [local.app_log_group, local.sys_log_group, local.audit_log_group]
  log_retention_days = var.log_retention_days
  kms_key_arn        = module.security.kms_key_arn

  instance_count = local.effective_instance_count
  instance_ids   = module.ec2.instance_ids

  enable_alarms       = local.effective_alarms
  cpu_alarm_threshold = var.cpu_alarm_threshold
  alarm_email         = var.alarm_email

  enable_cloudtrail      = local.effective_cloudtrail
  cloudtrail_bucket_name = local.cloudtrail_bucket

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# 7. Backup
# -----------------------------------------------------------------------------
module "backup" {
  source = "../../modules/backup"

  name_prefix    = local.name_prefix
  environment    = var.environment
  aws_account_id = var.aws_account_id
  kms_key_arn    = module.security.kms_key_arn

  enable_backup_plan = local.effective_backup_plan

  daily_retention_days   = var.backup_daily_retention_days
  weekly_retention_days  = var.backup_weekly_retention_days
  monthly_retention_days = var.backup_monthly_retention_days

  tags = local.common_tags
}
