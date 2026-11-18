# ---------------------------------------------------------------------------
# PRODUCTION environment values
#
# The full security profile is declared here: customer managed KMS key, per-AZ
# NAT Gateways, VPC Flow Logs, CloudTrail with log file validation, AWS Backup
# with 365-day monthly retention, private workloads, no public ingress.
#
# `zero_cost_mode = true` is a deliberate safety interlock: the declared profile
# is inert until an authorised operator flips BOTH zero_cost_mode and the
# per-resource toggles during an approved change window.
#
# NEVER apply production from a laptop. Use .github/workflows/terraform-apply.yml
# with the `production` GitHub Environment (required reviewers).
# ---------------------------------------------------------------------------

project_name = "eawlz"
environment  = "production"
aws_region   = "us-east-1"

aws_account_id = "111122223333"

owner       = "platform-engineering"
cost_center = "CC-PRD-001"

# --- Cost guard rails --------------------------------------------------------
zero_cost_mode    = true  # safety interlock - see header
offline_plan_mode = false # production plans must authenticate (OIDC)

# --- Production profile ------------------------------------------------------
enable_nat_gateway = true
enable_flow_logs   = true
enable_kms_key     = true
enable_alarms      = true
enable_cloudtrail  = true
enable_backup_plan = true

# --- Compute -----------------------------------------------------------------
# 3 instances across 3 AZs = one AZ failure tolerated without capacity loss.
instance_count   = 3
instance_type    = "m7i.large"
root_volume_size = 50

# --- Networking (10.30.0.0/16) ----------------------------------------------
vpc_cidr             = "10.30.0.0/16"
public_subnet_cidrs  = ["10.30.0.0/20", "10.30.16.0/20", "10.30.32.0/20"]
private_subnet_cidrs = ["10.30.128.0/20", "10.30.144.0/20", "10.30.160.0/20"]
availability_zones   = ["us-east-1a", "us-east-1b", "us-east-1c"]
az_count             = 3

# One NAT per AZ: a single NAT would make one AZ failure an egress outage.
single_nat_gateway = false

# No public ingress at all: workloads are private, admin is SSM-only.
allowed_ingress_cidrs = []
app_port              = 8080

# --- Storage lifecycle -------------------------------------------------------
s3_transition_to_ia_days              = 30
s3_noncurrent_version_expiration_days = 90

# --- Observability -----------------------------------------------------------
log_retention_days  = 90
cpu_alarm_threshold = 75
alarm_email         = ""

# --- Backup (RPO 24h / RTO 4h; 365-day monthly for compliance) ---------------
backup_daily_retention_days   = 35
backup_weekly_retention_days  = 90
backup_monthly_retention_days = 365

# --- CI/CD -------------------------------------------------------------------
github_repository = "example-org/enterprise-aws-landing-zone"
create_ci_role    = true
state_bucket_name = "eawlz-terraform-state"
