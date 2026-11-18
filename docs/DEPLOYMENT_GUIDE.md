# Deployment guide

## 1. Preconditions

| Requirement | Check |
|---|---|
| AWS account for the target environment | `aws sts get-caller-identity` |
| SSO or OIDC credentials | `aws sso login --profile <profile>` |
| Remote state bucket and lock table | `cd bootstrap && terraform output` |
| `backend.tf` present in the environment | `ls environments/production/backend.tf` |
| Cost estimate reviewed | `python scripts/cost_guard.py --plan plan.json` |
| Change record / approval | ticket reference in the PR |

## 2. Step 1 — preflight

```bash
python scripts/preflight.py --environment production
```

Fails on: missing state config, unformatted files, invalid configuration, forbidden
files in the tree, and (for production) a missing `--i-approve-production` flag after
review.

## 3. Step 2 — plan and review

```bash
cd environments/production
terraform init
terraform plan -out=deploy.tfplan
terraform show -no-color deploy.tfplan | tail -40
```

Read the plan, not just the counts. Specifically:

* any `-/+` (replacement) on a stateful resource,
* any security-group ingress change,
* any IAM policy change,
* any bucket policy or public-access change.

## 4. Step 3 — cost confirmation

```bash
terraform -chdir=environments/production show -json deploy.tfplan > ../../plan.json
python scripts/cost_guard.py --plan ../../plan.json --max-monthly-usd <approved-budget>
```

The estimate is indicative. For real approval, use the AWS Pricing Calculator with
the confirmed instance types and data volumes.

## 5. Step 4 — apply (approved path only)

```text
GitHub -> Actions -> "Terraform apply (manual, approval required)"
  environment: production
  confirm_apply: production        <- must match exactly
```

Required reviewers approve; the job then:

1. re-runs preflight,
2. requires `TF_STATE_BUCKET` (refuses local state),
3. plans, applies the saved plan,
4. posts outputs to the job summary.

Local `terraform apply` is not part of the supported path. If you must use it, you
own the consequences and you must still produce a plan artefact for review.

## 6. Step 5 — post-deployment verification

```bash
aws ec2 describe-vpcs --filters Name=tag:Environment,Values=production   --query 'Vpcs[].[VpcId,CidrBlock,State]' --output table
aws cloudtrail get-trail-status --name eawlz-production-trail
aws backup list-backup-plans --query 'BackupPlansList[].BackupPlanName'
aws s3api get-public-access-block --bucket <artifact-bucket>
```

Record the results in the change record. A green apply is not evidence that the
resources behave as intended.

## 7. Rollback

| Situation | Action |
|---|---|
| Bad configuration, no state change yet | Revert the commit, open a new PR |
| Applied but wrong | Re-apply the previous commit's plan artefact; do not hand-edit resources |
| Data corrupted | Restore from AWS Backup ([BACKUP_DISASTER_RECOVERY.md](BACKUP_DISASTER_RECOVERY.md)) |
| Partial apply failure | Fix forward: Terraform is idempotent, re-apply after correcting the error |

Never `terraform destroy` production to "start clean".

## 8. Deployment checklist (copy into the PR)

- [ ] Preflight passes for the target environment
- [ ] Plan reviewed line by line (replacements, IAM, SG, bucket policy)
- [ ] Cost estimate attached and approved
- [ ] Remote state configured, no local state in use
- [ ] Reviewers assigned (2 for production)
- [ ] Post-deployment verification commands run and recorded
- [ ] Rollback commit identified
