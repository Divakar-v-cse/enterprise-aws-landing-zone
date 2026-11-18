# GitHub push report

## 1. Repository

| Field | Value |
|---|---|
| URL | https://github.com/Divakar-v-cse/enterprise-aws-landing-zone |
| Owner / repo | `Divakar-v-cse` / `enterprise-aws-landing-zone` |
| Branch | `main` |
| First commit | `f94dc2c216d4733425ab18305912479f7943fa5d` |
| Commit subject | `Complete enterprise AWS landing zone automation` |
| Remote state before push | empty repository (fetch succeeded, zero heads) |
| Push method | `git push -u origin main`, no force, no history rewrite |
| Push result | success, `* [new branch] main -> main` |

Remote verified after push: `git ls-remote --heads origin` returned
`f94dc2c216d4733425ab18305912479f7943fa5d refs/heads/main`, identical to the local
`HEAD`.

## 2. Contents pushed

| Category | Count | Notes |
|---|---|---|
| Tracked files | 213 | 29,042 insertions |
| Terraform files | 45 | 7 modules + 3 environments + bootstrap + example |
| Documentation | 20 in `docs/` (+ README, LICENSE, module READMEs) | all internally linked |
| Python tooling | 13 CLIs + 1 library + catalogue | 73 tests |
| Workflows | 5 | validate, security, plan, apply, docs |
| Diagrams | 2 | `.mmd` source and rendered `.png` |
| Screenshots | 7 PNG + 7 transcripts | real captured terminal output |
| Security evidence | report + raw scanner JSON | reproducible |

## 3. Modules completed

| Module | Files | Verified |
|---|---|---|
| `networking` | main/variables/outputs/versions/README | `terraform validate` |
| `security` (KMS) | same | `terraform validate` |
| `iam` | + 4 policy templates | validate + policy lint |
| `ec2` | + user-data template | validate |
| `s3` | main/variables/outputs/versions/README | validate + Checkov |
| `monitoring` | same | validate + Checkov |
| `backup` | same | validate |

## 4. Validation results (executed locally)

| Command | Result |
|---|---|
| `terraform fmt -recursive -check` | exit 0, clean |
| `terraform init -backend=false` × 3 | success |
| `terraform validate` × 3 | `Success! The configuration is valid.` |
| `terraform plan` dev | 46 to add, 0 to change, 0 to destroy |
| `terraform plan` staging | 46 to add |
| `terraform plan` production profile | 72 to add |
| `python -m pytest tests -q` | **73 passed** |
| `python scripts/docs_lint.py` | 87 checks pass, 1 warning (no README checklist) |
| `python scripts/policy_lint.py` | 0 failures, 1 warning |

## 5. Security scan results

| Scanner | Result |
|---|---|
| Checkov 3.4.5 (75 resources) | **202 passed, 0 failed**, 13 documented skips |
| Trivy 0.76.2 IaC | **0 failures**, 5 dated accepted risks |
| `secret_scan.py` | 0 findings, 0 forbidden files |
| `policy_lint.py` | 0 violations across 4 policy documents |
| Gitleaks | configured (`.gitleaks.toml`), runs in CI; not executed locally |

Full detail: [../security/SECURITY_REPORT.md](../security/SECURITY_REPORT.md)

## 6. CI/CD status

| Workflow | Status |
|---|---|
| `terraform-validate.yml` | committed, valid YAML, **not yet executed on GitHub** |
| `security-scan.yml` | committed, valid YAML, not yet executed |
| `terraform-plan.yml` | committed, requires repository variables to authenticate |
| `terraform-apply.yml` | committed, manual dispatch only, approval gated |
| `docs-and-reports.yml` | committed, valid YAML, not yet executed |

The first run appears under the repository's Actions tab. `terraform-plan` and
`terraform-apply` need these repository variables before they can reach AWS:

| Variable | Purpose |
|---|---|
| `AWS_ROLE_TO_ASSUME` | ARN of the OIDC role created by `modules/iam` |
| `AWS_REGION` | e.g. `us-east-1` |
| `TF_STATE_BUCKET` | state bucket from `bootstrap/` |

Until those exist, the validate, security and docs workflows run fully offline and
the plan workflow still produces an artefact using the local backend.

## 7. AWS deployment status

**Not deployed.** No AWS credentials were used, `terraform apply` was never
executed, and no resource exists in any account. Everything above is local
validation and static analysis. Any deployment requires explicit authorisation plus
the approval gate described in [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).

## 8. Security check before push

| Check | Result |
|---|---|
| `.gitignore` covers state, plans, keys, `.env`, `backend.tf`, venvs | yes |
| Terraform state files staged | none |
| Plan files staged | none (`artifacts/` ignored) |
| Private keys / `.pem` / `.p12` staged | none |
| `.env` staged | none; `.env.example` contains placeholders only |
| AWS credentials staged | none; no access keys exist in the repository |
| Secret scan | 0 findings |
| Gitleaks allowlist | limited to docs, fixtures and the scanner implementation |

## 9. Remaining issues

| Item | Severity | Note |
|---|---|---|
| TFLint not executed locally | medium | Not installed in this environment; the workflow runs it on every PR |
| No AWS deployment | expected | Requires authorisation; plan-only evidence |
| CI not yet executed on GitHub | medium | Starts on the next push; requires the repository variables above |
| README has no acceptance checklist | low | `docs_lint` warns; content covered by PROJECT_AUDIT |
| CI deploy policy not tag-conditioned | medium | Documented hardening step in IAM_SECURITY.md |
| No restore test executed | medium | RPO/RTO are targets, not measurements |
| No cross-region backup copy | low | Documented as next step |

## 10. Reproduce this report

```bash
git clone https://github.com/Divakar-v-cse/enterprise-aws-landing-zone.git
cd enterprise-aws-landing-zone
python -m pytest tests -q
python scripts/run_all_checks.py
```
