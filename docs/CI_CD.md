# CI/CD

## 1. Workflows

| Workflow | Trigger | What it does | Credentials |
|---|---|---|---|
| `terraform-validate.yml` | PR, push to main | fmt, init `-backend=false`, validate, offline plan, TFLint, pytest, docs lint, policy lint | none |
| `security-scan.yml` | PR, push, weekly cron | Checkov, Trivy (SARIF to code scanning), Gitleaks, repository secret scan, policy lint | none |
| `terraform-plan.yml` | `workflow_dispatch`, PR on env changes | OIDC assume role, init with S3 backend, plan artefact, cost estimate | OIDC (optional) |
| `terraform-apply.yml` | `workflow_dispatch` only | Guard on typed confirmation, preflight, plan, apply saved plan | OIDC (required) |
| `docs-and-reports.yml` | PR on markdown | docs lint, repository contract tests | none |

## 2. Ordering rationale

```text
fmt -> init -> validate -> tflint -> checkov -> trivy -> secrets -> policy -> pytest -> plan -> apply
```

Cheap and deterministic checks run first. A scan never runs before `validate`
proves the configuration parses, and no plan runs before the scanners pass. This
keeps PR feedback fast and prevents a broken commit from consuming OIDC tokens.

## 3. GitHub OIDC (no stored secrets)

```yaml
permissions:
  id-token: write
  contents: read
```

The plan and apply jobs assume a role only when the repository variable
`AWS_ROLE_TO_ASSUME` is set. The trust policy is in
[`modules/iam/policies/github-oidc-trust.json.tftpl`](../modules/iam/policies/github-oidc-trust.json.tftpl)
and restricts `sub` to this repository's `main` ref and its `staging` and
`production` environments. No AWS access key exists in GitHub, so there is nothing
to leak or rotate.

If OIDC is not configured, `terraform-plan.yml` still runs in zero-cost mode with
no credentials, which is what makes the workflow usable on a fork.

## 4. Approval gate for production

| Control | Setting |
|---|---|
| Trigger | `workflow_dispatch` only, never `pull_request` |
| Environment | job binds to the `production` GitHub Environment |
| Reviewers | at least 2 required reviewers, dismiss stale approvals |
| Branch policy | deployments only from `main` |
| Confirmation | operator types the environment name into `confirm_apply` |
| Apply input | the saved plan file from the same job, never a fresh plan |
| Concurrency | one apply per environment, no cancellation |

The guard job fails before any credential is requested if the typed confirmation
does not match the selected environment.

## 5. Artifacts

| Artifact | Retention | Contents |
|---|---|---|
| `tfplan-<env>-<run>` | 14 days | saved plan and human-readable plan text |
| `checkov-report` | 90 days (default) | JSON results used by the security report |
| `policy-lint` | 90 days | IAM policy findings |
| SARIF | code scanning | Trivy IaC findings in the Security tab |

Plan files can contain sensitive values; they are short-lived artefacts, never
committed.

## 6. Reproducing CI locally

```bash
bash cicd/local-pipeline.sh        # Linux/macOS
pwsh cicd/local-pipeline.ps1       # Windows
python scripts/run_all_checks.py   # Python orchestrator, same order
```

## 7. Failure handling

| Failure | Meaning | Action |
|---|---|---|
| `fmt` | Style drift | `terraform fmt -recursive`, commit |
| `validate` | Syntax or type error | Read the error, fix the module, re-run |
| Checkov | A control regressed | Fix it, or add a justified, dated skip in `policies/scanners/checkov.yaml` |
| Trivy | New misconfiguration | Same, with an expiry date in `.trivyignore.yaml` |
| Gitleaks | Possible credential | **Stop.** Rotate the credential, then purge history |
| Apply | Guard failed | Check the typed confirmation and the environment reviewers |
