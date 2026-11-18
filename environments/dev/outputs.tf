output "environment" {
  description = "Environment name."
  value       = var.environment
}

output "zero_cost_mode" {
  description = "True when every billable resource is disabled."
  value       = !local.billable
}

output "vpc_id" {
  description = "VPC ID."
  value       = module.networking.vpc_id
}

output "vpc_cidr" {
  description = "VPC CIDR block."
  value       = module.networking.vpc_cidr
}

output "public_subnet_ids" {
  description = "Public subnet IDs."
  value       = module.networking.public_subnet_ids
}

output "private_subnet_ids" {
  description = "Private subnet IDs."
  value       = module.networking.private_subnet_ids
}

output "app_security_group_id" {
  description = "Application security group ID."
  value       = module.networking.app_security_group_id
}

output "artifact_bucket_name" {
  description = "Artifact bucket name."
  value       = module.s3.bucket_id
}

output "artifact_bucket_encryption" {
  description = "Effective bucket encryption algorithm."
  value       = module.s3.encryption_algorithm
}

output "ec2_role_arn" {
  description = "Workload IAM role ARN."
  value       = module.iam.ec2_role_arn
}

output "permission_boundary_arn" {
  description = "Permission boundary policy ARN."
  value       = module.iam.permission_boundary_arn
}

output "ci_role_arn" {
  description = "GitHub Actions OIDC role ARN (used as the role-to-assume in workflows)."
  value       = module.iam.ci_role_arn
}

output "instance_count" {
  description = "Number of EC2 instances planned/created."
  value       = module.ec2.instance_count
}

output "instance_ids" {
  description = "EC2 instance IDs."
  value       = module.ec2.instance_ids
}

output "ssm_session_hint" {
  description = "How to reach an instance without SSH."
  value       = module.ec2.ssm_start_session_hint
}

output "dashboard_name" {
  description = "CloudWatch dashboard name."
  value       = module.monitoring.dashboard_name
}

output "log_groups" {
  description = "Log groups created."
  value       = concat(module.monitoring.app_log_group_names, module.monitoring.audit_log_group_names)
}

output "backup_vault_name" {
  description = "AWS Backup vault name."
  value       = module.backup.vault_name
}

output "backup_schedule" {
  description = "Backup schedule summary."
  value       = module.backup.schedule_summary
}

output "kms_encryption_mode" {
  description = "kms (customer managed) or aws-managed."
  value       = module.security.encryption_mode
}
