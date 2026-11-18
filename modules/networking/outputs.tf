output "vpc_id" {
  description = "VPC identifier."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "VPC CIDR block."
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "Public subnet identifiers (ingress / load balancer tier)."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet identifiers (workload tier)."
  value       = aws_subnet.private[*].id
}

output "public_subnet_cidrs" {
  description = "Public subnet CIDR blocks (used for IP planning checks)."
  value       = aws_subnet.public[*].cidr_block
}

output "private_subnet_cidrs" {
  description = "Private subnet CIDR blocks (used for IP planning checks)."
  value       = aws_subnet.private[*].cidr_block
}

output "app_security_group_id" {
  description = "Security group for application workloads."
  value       = aws_security_group.app.id
}

output "db_security_group_id" {
  description = "Security group for the data tier."
  value       = aws_security_group.db.id
}

output "nat_gateway_ids" {
  description = "NAT Gateway identifiers. Empty when enable_nat_gateway = false."
  value       = aws_nat_gateway.this[*].id
}

output "private_route_table_ids" {
  description = "Private route table identifiers."
  value       = aws_route_table.private[*].id
}

output "s3_endpoint_id" {
  description = "S3 gateway VPC endpoint identifier, if created."
  value       = try(aws_vpc_endpoint.s3[0].id, null)
}

output "flow_log_id" {
  description = "VPC Flow Log identifier, if enabled."
  value       = try(aws_flow_log.this[0].id, null)
}
