output "ec2_role_arn" {
  description = "ARN of the workload (EC2) role."
  value       = aws_iam_role.ec2.arn
}

output "ec2_role_name" {
  description = "Name of the workload (EC2) role."
  value       = aws_iam_role.ec2.name
}

output "ec2_instance_profile_name" {
  description = "Instance profile name for attaching to EC2 instances."
  value       = aws_iam_instance_profile.ec2.name
}

output "ec2_policy_arn" {
  description = "ARN of the scoped application policy."
  value       = aws_iam_policy.ec2_app.arn
}

output "permission_boundary_arn" {
  description = "ARN of the permission boundary policy, or null when disabled."
  value       = local.boundary_arn
}

output "ci_role_arn" {
  description = "ARN of the GitHub Actions OIDC role, or null when create_ci_role = false."
  value       = try(aws_iam_role.ci[0].arn, null)
}

output "ci_policy_arn" {
  description = "ARN of the scoped CI deployment policy, or null."
  value       = try(aws_iam_policy.ci_deploy[0].arn, null)
}

output "oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider created by this module, or null."
  value       = try(aws_iam_openid_connect_provider.github[0].arn, null)
}

output "allowed_oidc_subjects" {
  description = "Subject claims permitted to assume the CI role (audit trail for trust policy review)."
  value       = var.create_ci_role ? local.allowed_subjects : []
}
