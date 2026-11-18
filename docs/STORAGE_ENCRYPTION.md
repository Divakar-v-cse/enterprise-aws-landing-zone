# Storage and encryption

Module mapping: the brief calls these `storage` and `encryption`; in this repo
they are `modules/s3` and `modules/security` (KMS).

## 1. S3 controls

| Control | Setting | Effect |
|---|---|---|
| Public access block | all four `true` | No ACL or policy can make the bucket public |
| Ownership | `BucketOwnerEnforced` | ACLs disabled; owner owns every object |
| Encryption at rest | SSE-KMS with CMK, else SSE-S3 | Encrypted either way; zero-cost mode uses AES256 |
| Encryption in transit | Bucket policy denies `s3:*` when `aws:SecureTransport=false` | HTTP is impossible, not discouraged |
| Upload encryption | `PutObject` denied if a non-approved algorithm header is sent | Prevents downgrade attempts |
| Versioning | Enabled | Object-level recovery from overwrite/delete |
| Version growth | Non-current expiry (30–90 d by env) | Bounds storage cost |
| Cost leak | Abort incomplete multipart uploads after 7 d | The classic silent S3 bill |
| Lifecycle | IA at 30 d (configurable), Glacier IR for audit buckets | Cost curve without operational surprise |

### Why `Null` in the upload-encryption condition

`StringNotEquals` alone would deny uploads that omit the header — exactly the
uploads that should succeed via default encryption. The statement therefore also
requires `Null: s3:x-amz-server-side-encryption == false`, so it only evaluates
when the client actually sent the header. This is a real bug pattern in many
"secure S3" examples.

## 2. KMS

| Setting | Value |
|---|---|
| Key type | Customer managed, per environment |
| Rotation | `enable_key_rotation = true` (annual, automatic) |
| Deletion window | 7 d dev, 30 d production |
| Key policy | Root delegation + split admin/usage statements |
| Deletion guard | `Deny` when `aws:MultiFactorAuthPresent == false` |
| Alias | `alias/<prefix>-data` |

Per-environment keys keep blast radius small: a compromised dev principal can
never decrypt production data.

### Key policy trade-off

The key policy delegates to the account root so IAM policies can grant usage
without editing the key policy for every consumer. That is why Checkov flags
`Resource: "*"` (CKV_AWS_356): a KMS key policy applies to the key itself and
cannot use a narrower resource. Documented as an accepted risk in
[policies/scanners/checkov.yaml](../policies/scanners/checkov.yaml).

## 3. EBS

Every root volume: `encrypted = true`, `volume_type = "gp3"`,
`delete_on_termination = true`. With a CMK the key is used; without one, AWS's
managed `aws/ebs` key (free) still encrypts everything.

## 4. CloudTrail / log storage

The trail bucket adds versioning, SSE, public-access-block and a lifecycle that
moves objects to Glacier IR at 90 days and expires them after the configured
compliance window (365 d default). Its policy is scoped with `aws:SourceArn` so
another account's trail cannot write into it (confused-deputy protection).

## 5. Cost notes

| Item | Cost |
|---|---|
| S3 storage (standard) | ~\$0.023/GB-month |
| S3 requests | ~\$0.005 per 1,000 PUT |
| SSE-S3 / AWS-managed keys | free |
| Customer managed KMS key | ~\$1/key-month + \$0.03/10k requests |
| Glacier IR | ~\$0.004/GB-month, retrieval fee |

Indicative only — see [COST_MANAGEMENT.md](COST_MANAGEMENT.md).
