# bootstrap/ — Terraform state backend

Run **once per AWS account**, by a human, before any environment switches to
remote state. Nothing in CI applies this configuration.

## Why it lives outside `environments/`

Terraform cannot store its own state in a bucket it is about to create. The
bootstrap configuration therefore uses the local backend, and its state file
(`bootstrap/terraform.tfstate`) is git-ignored. Keep a copy in a password manager
or an internal vault — if it is lost, re-import the bucket and table with
`terraform import` rather than recreating them.

## Steps

```bash
cd bootstrap
terraform init
terraform plan -out=bootstrap.tfplan     # expect: 7 resources, no EC2/NAT
terraform apply bootstrap.tfplan
terraform output backend_snippet
```

Then, for each environment:

```bash
cd ../environments/dev
cp backend.tf.example backend.tf
# paste the snippet from `terraform output backend_snippet`, set key to landing-zone/dev/terraform.tfstate
terraform init -migrate-state
```

## Cost

| Resource | Approx. monthly |
|---|---|
| S3 bucket (a few KB of state + versions) | < \$0.01 |
| DynamoDB on-demand (a handful of lock operations) | < \$0.01 |
| KMS CMK (optional) | ~\$1.00 |

Figures are indicative; the bucket and table are effectively free at this scale.

## Security properties

* Versioning on — a corrupt or truncated state can be rolled back.
* Server-side encryption (SSE-S3 by default; swap to a CMK if policy requires).
* All four public-access blocks on, plus a TLS-only bucket policy.
* DynamoDB point-in-time recovery — lock table loss during a concurrent apply is
  recoverable.
* Access is granted per role: developers get read-only on state, the CI role gets
  read/write scoped to `landing-zone/<env>/*`.

## What must never happen

* Committing `terraform.tfstate` (git-ignored, verified by `scripts/preflight.py`).
* Sharing one state file between environments.
* Editing state by hand on the S3 console. Use `terraform state` subcommands and
  record the change in the PR.
