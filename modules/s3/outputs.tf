output "bucket_id" {
  description = "Bucket name."
  value       = aws_s3_bucket.this.id
}

output "bucket_arn" {
  description = "Bucket ARN, used by IAM policies and monitoring."
  value       = aws_s3_bucket.this.arn
}

output "bucket_domain_name" {
  description = "Global bucket domain name."
  value       = aws_s3_bucket.this.bucket_domain_name
}

output "bucket_regional_domain_name" {
  description = "Regional bucket domain name (preferred for same-region access)."
  value       = aws_s3_bucket.this.bucket_regional_domain_name
}

output "encryption_algorithm" {
  description = "Effective default encryption algorithm (aws:kms or AES256)."
  value       = local.use_kms ? "aws:kms" : "AES256"
}

output "versioning_status" {
  description = "Versioning status applied to the bucket."
  value       = var.enable_versioning ? "Enabled" : "Suspended"
}
