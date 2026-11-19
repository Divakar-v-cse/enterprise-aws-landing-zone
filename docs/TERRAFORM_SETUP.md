# Terraform setup

## 1. Layout of an environment root

```text
environments/<env>/
  versions.tf          required_version + provider constraints
  providers.tf         provider config, default_tags, offline switches
  variables.tf         validated inputs, environment self-guard
  main.tf              composition only, no resources
  outputs.tf           values for operators and CI
  terraform.tfvars     environment values (committed, no secrets)
  backend.tf.example   S3 + DynamoDB backend template (backend.tf is ignored)
```

## 2. Version constraints

```hcl
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = ">= 5.40.0, < 7.0.0" }
  }
}
```

The upper bound is deliberate: a provider major release can change resource
schemas. `.terraform.lock.hcl` is committed so every machine and CI resolve
identical provider builds for every platform.

## 3. Offline plan mode

`offline_plan_mode = true` (the dev default) sets:

```hcl
skip_credentials_validation = var.offline_plan_mode
skip_requesting_account_id  = var.offline_plan_mode
skip_metadata_api_check     = var.offline_plan_mode
```

The AWS provider otherwise calls STS to resolve the account even for a plan that
creates nothing, which fails without credentials. With these switches and no data
sources in the configuration, `plan` makes zero network calls. That is why the
availability zones, region and account ID are inputs rather than lookups.

The provider still builds a credential chain even when validation is skipped, so
on a machine with no AWS configuration at all (a fresh CI runner) `plan` fails at
provider configuration with `No valid credential sources found`. Supply throwaway
values for the chain — no call is made when validation is skipped:

```bash
export AWS_ACCESS_KEY_ID=offline-validation
export AWS_SECRET_ACCESS_KEY=offline-validation-placeholder
export AWS_EC2_METADATA_DISABLED=true
```

These are placeholders, not credentials: they cannot authenticate anything.

Set it to `false` before any real deployment, otherwise the provider cannot read
actual infrastructure and the plan is meaningless.

## 4. Remote state

The local backend is the default so validation needs no prerequisites. For real use:

```bash
cd bootstrap
terraform init
terraform apply

cd ../environments/dev
cp backend.tf.example backend.tf   # paste the bootstrap output, set the key
terraform init -migrate-state
```

`backend.tf` is git-ignored so one engineer's bucket name cannot leak into another
checkout. Locking uses the DynamoDB table (`LockID`); Terraform 1.10+ also supports
S3 native locking, but DynamoDB works with every provider version this project
supports.

## 5. State security

| Risk | Control |
|---|---|
| State in git | `.gitignore`, `preflight.py` check, repository test assertion |
| Unauthorised read | Bucket policy is TLS-only, access via IAM only |
| Tampering | Versioning plus DynamoDB point-in-time recovery |
| Concurrent applies | DynamoDB lock plus CI concurrency group per environment |
| Stuck lock | Documented `terraform force-unlock` procedure |

State files can contain secrets (generated passwords, tokens). Treat the bucket as
confidential, never as documentation.

## 6. Daily commands

```bash
terraform fmt -recursive -check
terraform init -backend=false && terraform validate
tflint --init && tflint --recursive
python -m pytest tests -q
python scripts/run_all_checks.py
```

## 7. Input validation

Every input that can be wrong fails at plan time, not apply time:

```hcl
variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "environment must be one of: dev, staging, production."
  }
}
```

Each environment also pins its own name (`var.environment == "dev"`), so copying
`production/terraform.tfvars` into `dev/` fails immediately instead of quietly
building production-shaped development infrastructure.
