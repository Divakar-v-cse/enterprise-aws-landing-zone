# Security architecture

## 1. Threat model

| Threat | Vector | Control |
|---|---|---|
| Credential theft from CI | Long-lived keys in secrets | OIDC federation, 1-hour sessions, no stored keys |
| Credential theft from a workload | SSRF against instance metadata | IMDSv2 required, hop limit 1, no public IP |
| Privilege escalation | Over-broad role | Scoped policy plus independent permission boundary |
| Lateral movement | Open security groups | No inbound by default, no SSH or RDP anywhere |
| Data exfiltration | Public bucket or plain HTTP | PAB x4, TLS-only and encryption-required bucket policy |
| Ransomware | Key deletion, bucket policy rewrite | MFA-gated KMS deletion deny, deny on policy widening |
| Anti-forensics | Disabling logging | Deny on CloudTrail, GuardDuty and Config tampering |
| Supply chain | Malicious provider or module | Version bounds, committed lock file, no third-party modules |
| State compromise | State in git or public bucket | Ignored, TLS-only bucket, versioning, locking |

## 2. Controls by layer

| Layer | Controls |
|---|---|
| Identity | Scoped IAM, condition keys, boundary, OIDC, SSO with MFA, no IAM users created |
| Network | Private workloads, multi-AZ, NACLs, least-privilege SGs, free S3 endpoint, optional flow logs |
| Data | SSE (KMS or AES256), versioning, lifecycle, PAB, TLS-only policies |
| Audit | Multi-region CloudTrail with log-file validation, retained log groups |
| Delivery | fmt, validate, TFLint, Checkov, Trivy, Gitleaks, custom policy lint, approval gate |
| Operations | Preflight checks, drift report, cost guard, tagging policy, runbooks |

## 3. Defence in depth example: the workload role

1. **Identity policy** allows only specific ARNs and condition-key-scoped actions.
2. **Explicit denies** block IAM, audit tampering, key deletion, bucket widening.
3. **Permission boundary** independently blocks the same classes even if a future
   edit attaches `AdministratorAccess`.
4. **IMDSv2 with hop limit 1** means a compromised process inside a container
   cannot fetch the role's credentials.
5. **No inbound network path** means the credential cannot be reached from outside.

Removing any one layer does not collapse the model, which is the point.

## 4. Secrets management

| Secret | Where it lives | Never |
|---|---|---|
| AWS credentials (CI) | Nowhere: OIDC token per run | in repo variables as keys |
| AWS credentials (human) | SSO cache, expires in hours | in `.env` committed |
| Application secrets | SSM Parameter Store or Secrets Manager (referenced, not created) | in user data, tfvars, or code |
| Terraform state | Encrypted S3 bucket | in git |

`user-data.sh.tftpl` deliberately contains no secrets: user data is readable from
instance metadata and stored in the launch template.

## 5. Scanning and what it proves

| Scanner | Proves | Does not prove |
|---|---|---|
| `terraform validate` | The configuration is syntactically and type valid | That it is secure or correct |
| Checkov | Known insecure resource patterns are absent | Runtime configuration |
| Trivy | No misconfiguration matches its rule set | That a rule set covers your threat model |
| `secret_scan.py` | No credential-shaped string in the working tree | That history is clean (Gitleaks covers history) |
| `policy_lint.py` | Policies avoid the classic over-grant patterns | Actual IAM evaluation against real requests |

A green pipeline means "no known bad patterns", not "secure". The honest statement
matters more than the badge.

## 6. Known limitations

1. No AWS account was scanned; account-level controls (SCPs, GuardDuty, Security
   Hub, Access Analyzer, Config) are out of scope for zero-cost validation.
2. The CI deploy policy is service-scoped and deny-hardened but not tag-conditioned;
   hardening steps are listed in [IAM_SECURITY.md](IAM_SECURITY.md).
3. Data events are not enabled on CloudTrail (cost), so S3 object-level reads of
   sensitive prefixes are not audited yet.
4. No penetration test, no restore test, no chaos experiment has been executed.

## 7. Incident response entry points

| Situation | First action | Document |
|---|---|---|
| Suspected credential leak | Revoke the credential, then review CloudTrail | [BACKUP_DISASTER_RECOVERY.md](BACKUP_DISASTER_RECOVERY.md) |
| Unexpected infrastructure change | Run the drift report, compare with git log | [DRIFT_DETECTION.md](DRIFT_DETECTION.md) |
| Public bucket discovered | Check PAB and bucket policy, review CloudTrail `PutBucketPolicy` | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| Region-wide outage | Follow the DR runbook | [BACKUP_DISASTER_RECOVERY.md](BACKUP_DISASTER_RECOVERY.md) |
