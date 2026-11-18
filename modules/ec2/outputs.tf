output "instance_ids" {
  description = "Instance IDs (empty when instance_count = 0)."
  value       = aws_instance.this[*].id
}

output "private_ips" {
  description = "Private IP addresses of the instances."
  value       = aws_instance.this[*].private_ip
}

output "instance_count" {
  description = "Number of instances actually created."
  value       = length(aws_instance.this)
}

output "ami_used" {
  description = "AMI ID resolved for the instances, or the explicit override."
  value       = var.instance_count > 0 ? (var.ami_id != "" ? var.ami_id : data.aws_ami.amazon_linux[0].id) : null
}

output "ssm_start_session_hint" {
  description = "Ready-to-run command showing how to reach an instance without SSH."
  value       = length(aws_instance.this) > 0 ? "aws ssm start-session --target ${aws_instance.this[0].id}" : "No instances created (instance_count = 0)."
}
