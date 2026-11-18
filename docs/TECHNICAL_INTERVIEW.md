# Technical interview guide

35 questions and answers based on this project. Answers are deliberately short and
honest: several admit a limitation, because that is what interviewers probe for.

## Networking

**1. What is a VPC?**
A logically isolated virtual network in AWS: you choose the CIDR range, subnets,
route tables, gateways and gateways' policies. Everything network-related in an
account lives inside one.

**2. Public vs private subnet — the actual difference?**
Not the name and not the route table by itself: a public subnet's route table has a
route to an internet gateway. Resources in it can be internet-reachable only if they
also have a public IP and a permissive security group.

**3. Why keep workloads in private subnets?**
No inbound path from the internet and no public IP to attack. Egress goes through a
NAT Gateway or VPC endpoints, and administrative access goes through SSM rather than
SSH.

**4. How does routing work between subnets in the same VPC?**
The VPC's implicit local route handles it; no route table entry is required. Route
tables decide only where traffic leaves the subnet.

**5. What does a NAT Gateway actually do?**
Source-NAT for outbound traffic from private subnets. It is not a firewall, does not
accept inbound connections, and costs ~$32/month plus data processing per AZ.

**6. Why is the S3 gateway endpoint free and why use it?**
Gateway endpoints are a route-table target for S3 and DynamoDB traffic, with no
hourly or data charge. Traffic stays on the AWS network, so it avoids NAT data
processing — usually the biggest line item.

**7. Security group vs NACL?**
SGs are stateful, attached to resources, allow-only. NACLs are stateless, attached to
subnets, allow and deny. Use SGs as the primary control; NACLs give coarse subnet
guard rails.

**8. Why does this design have no bastion host?**
SSM Session Manager provides shell access through the SSM agent and IAM, with full
audit in CloudTrail, no inbound port, and no SSH key to manage or leak.

**9. Three AZs or two?**
Three gives tolerance of one AZ failure with capacity remaining and lets a managed
service place nodes across the maximum number of fault domains. Two is cheaper but
loses a third of capacity on failure.

**10. How do you plan CIDR ranges so you never re-IP?**
Use a /16 per VPC with /20 subnets, allocate by environment (10.10, 10.20, 10.30), and
reserve a block for future tiers. Overlapping ranges make peering and transit
gateways impossible later.

## IAM

**11. What is least privilege in practice?**
Grant specific actions on specific resources with conditions. Example here: S3
`GetObject` on `<bucket>/config/*` only, `ListBucket` only with a matching
`s3:prefix`, and `PutMetricData` only in one namespace.

**12. Why use a permission boundary if the policy is already scoped?**
Defence in depth. If someone later attaches `AdministratorAccess` to the role, the
boundary still blocks IAM changes, audit tampering and non-approved regions.

**13. Why deny statements inside an identity policy?**
Explicit deny wins over any allow, including future ones. It converts "we hope nobody
grants IAM" into "IAM is impossible for this role".

**14. How does GitHub OIDC remove secrets?**
GitHub mints a short-lived JWT describing the repo/ref/environment; AWS STS exchanges
it for temporary credentials via `AssumeRoleWithWebIdentity`. Nothing long-lived is
stored, so there is nothing to leak or rotate.

**15. What breaks OIDC security?**
A wildcard subject such as `repo:*`, or trusting `aud` loosely. The trust policy here
requires `aud = sts.amazonaws.com` and pins the `sub` to specific refs and
environments; `repo:*` is rejected by variable validation.

**16. Why not use an access key for CI?**
It never expires, is easy to exfiltrate from logs or forks, and must be rotated
manually. OIDC has a one-hour lifetime and is bound to a repository identity.

**17. How do EC2 instances get credentials without keys?**
An instance profile delivers temporary credentials via IMDS. Here IMDSv2 is required
with hop limit 1, so SSRF and container escapes cannot reach the metadata service.

**18. What is `iam:PassRole` and why is it dangerous?**
It lets a principal hand a role to a service. Combined with `ec2:RunInstances` it
allows privilege escalation, so it must be scoped to specific role ARNs and to the
intended service.

## Terraform

**19. What is Terraform state and why is it sensitive?**
A mapping from configuration addresses to real resource IDs plus cached attributes.
It can contain generated passwords and tokens, so it belongs in an encrypted,
access-controlled bucket — never in git.

**20. How do you lock state?**
A DynamoDB table with a `LockID` key (used here), or S3 native locking in Terraform
1.10+. Locking prevents two applies from interleaving and corrupting state.

**21. Directories or workspaces — why did you choose directories?**
Workspaces share one backend and one variable set; a `-var` slip can plan production
from a dev shell. Separate directories give separate state, separate tfvars and a
per-environment self-guard. Cost: three plan runs in CI.

**22. What makes a module reusable?**
No hardcoded account IDs, regions or names; validated inputs; meaningful outputs; no
data sources that force live API calls; and behaviour driven by flags (for example
NAT on/off) rather than forks.

**23. How do you handle resource naming across environments?**
A `name_prefix` of `<project>-<environment>` flows into every resource name and tag,
plus provider `default_tags` for `Project`, `Environment`, `Owner`, `CostCenter`.

**24. Why pin provider versions with an upper bound?**
A major provider release can change resource schemas. `>= 5.40, < 7.0` plus a
committed lock file means every machine resolves the same build.

**25. How do you make `terraform plan` work with no credentials?**
Remove data sources, inject AZs/region/account as variables, and set the provider's
`skip_credentials_validation`, `skip_requesting_account_id` and
`skip_metadata_api_check`. That is how the zero-cost mode in this repo plans offline.

**26. What does `terraform fmt -check` protect against?**
Unreviewable diffs. A single misaligned HCL block can hide an added IAM action in a
large diff; formatting keeps changes visually scannable.

## Drift and operations

**27. What is infrastructure drift?**
A difference between what the code declares, what state records, and what actually
exists. It appears when someone changes resources in the console, a provider changes
a default, or an automated process mutates a resource.

**28. Can `terraform plan` prove drift?**
No. A plan combines configuration, state and (with refresh) live data; it cannot tell
you whether a diff came from a console change or from a code change. This project
labels changes as `drift-candidate` and requires a human to confirm against git log
and CloudTrail.

**29. How do you detect resources Terraform does not manage?**
Terraform cannot see them. You need AWS Config, a resource inventory (Resource
Explorer) or tag audits — an explicit scope limit of this project.

**30. How would you handle a production hotfix made in the console?**
Treat it as drift: capture the config, add it to Terraform, review the diff, apply so
state matches, then investigate why the change bypassed review.

**31. What is your rollback strategy?**
Re-apply the previous commit's saved plan. Never hand-edit resources, never destroy
production to "clean up". If data is corrupted, restore from AWS Backup.

**32. How do you approach RPO and RTO?**
RPO is acceptable data loss (24h here, daily backups), RTO is acceptable downtime (4h,
mostly Terraform time). They are targets until a restore test measures them.

**33. What is the biggest gap in this project's DR?**
No executed restore test and no cross-region backup copy. Configuration checks do not
prove a recovery point restores.

## DevSecOps and judgement

**34. How do you decide to accept a scanner finding?**
Fix it if it is real. If it is a cost or design trade-off, skip it by check ID with a
written justification and an expiry date, and record it in the security report. Never
skip a directory or disable a whole scanner.

**35. What would you do differently for a real enterprise?**
Separate accounts per environment under AWS Organizations with SCPs, a central log
archive account, a dedicated network account for transit gateway, GuardDuty and
Security Hub at organisation level, tag-conditioned CI policies generated from
CloudTrail with Access Analyzer, and scheduled restore drills.

## Closing advice

When asked "is it production ready?", the correct answer here is: "the code is, the
evidence is partial." State what was verified (validation, plans, static analysis),
what was not (no deployment, no restore test, no TFLint run locally), and what you
would do first (deploy to dev with approval, then a restore drill).
