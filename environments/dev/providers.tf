provider "aws" {
  region = var.aws_region

  # ---------------------------------------------------------------------------
  # Offline / zero-cost validation switches
  # ---------------------------------------------------------------------------
  # With no AWS credentials configured, the provider would still call STS to
  # resolve the account before finalising the plan. These switches keep
  # `terraform plan` completely local (no API calls, no cost, no secrets) and
  # are REQUIRED for the zero-cost development mode.
  #
  # They must be false for real deployments. Set offline_plan_mode = false in
  # terraform.tfvars once credentials/OIDC are wired up.
  # ---------------------------------------------------------------------------
  skip_credentials_validation = var.offline_plan_mode
  skip_requesting_account_id  = var.offline_plan_mode
  skip_metadata_api_check     = var.offline_plan_mode

  # Tags applied to every taggable resource, on top of each module's own tags.
  # Cost allocation reports rely on Project/Environment/CostCenter being present
  # on 100% of resources, including ones created outside the modules.
  default_tags {
    tags = local.common_tags
  }
}
