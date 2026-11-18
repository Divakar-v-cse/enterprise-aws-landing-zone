output "kms_key_arn" {
  description = "ARN of the customer managed key, or null when create_kms_key = false."
  value       = try(aws_kms_key.this[0].arn, null)
}

output "kms_key_id" {
  description = "ID of the customer managed key, or null when create_kms_key = false."
  value       = try(aws_kms_key.this[0].key_id, null)
}

output "kms_alias_name" {
  description = "Alias of the customer managed key, or null when create_kms_key = false."
  value       = try(aws_kms_alias.this[0].name, null)
}

output "encryption_mode" {
  description = "Effective encryption mode for consumers: cmk (customer managed) or aws-managed."
  value       = local.create_key ? "cmk" : "aws-managed"
}
