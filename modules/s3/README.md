# Module: s3

Encrypted, versioned, non-public object storage with TLS-only access and
lifecycle hygiene.

## Controls applied

| Control | Implementation |
|---|---|
| Public access | `aws_s3_bucket_public_access_block` — all four switches `true` |
| Ownership | `BucketOwnerEnforced` (ACLs disabled entirely) |
| Encryption at rest | SSE-KMS when `kms_key_arn` is set, otherwise SSE-S3 `AES256` |
| Encryption in transit | Bucket policy denies `s3:*` when `aws:SecureTransport = false` |
| Upload encryption | `PutObject` denied when an explicit non-approved encryption header is sent |
| Versioning | Enabled by default; supports point-in-time object recovery |
| Version growth | `noncurrent_version_expiration` after 90 days (configurable) |
| Cost leak | `abort_incomplete_multipart_upload` after 7 days |
| Deletion safety | `prevent_destroy` on production buckets |

## Usage

```hcl
module "artifacts" {
  source = "../../modules/s3"

  bucket_name        = "eawlz-dev-artifacts-111122223333"
  environment        = "dev"
  purpose            = "artifacts"
  kms_key_arn        = module.security.kms_key_arn # null -> SSE-S3
  enable_versioning  = true
  transition_to_ia_days = 30
  tags               = local.common_tags
}
```

## Cost notes

* Bucket creation, versioning and lifecycle rules are free.
* You pay for stored bytes, requests, and non-current versions kept for the
  retention window. `noncurrent_version_expiration_days = 90` bounds that growth.
* SSE-S3 and SSE-KMS with an AWS-managed key are free; a customer managed key
  costs ~\$1/month + requests.

## Deliberate omission

S3 server access logging is **off by default** (`enable_access_logging = false`)
because it requires a second bucket and doubles request-logging storage. CloudTrail
data events are the preferred audit path; see `security/SECURITY_REPORT.md` for
the documented exception.
