# policies/

Policy-as-code artefacts: the reviewable source of truth for every permission
this landing zone grants, plus scanner and budget configuration.

```
policies/
├── iam/                    # rendered from modules/iam/policies (verified identical)
│   ├── ec2-app-policy.json.tftpl
│   ├── permission-boundary.json.tftpl
│   ├── github-oidc-trust.json.tftpl
│   └── ci-terraform-deploy-policy.json.tftpl
├── budgets/budget.json     # AWS Budgets definition + alert thresholds
├── scanners/checkov.yaml   # accepted-risk register for the static scanner
├── scanners/trivy.yaml     # trivy IaC scan configuration
└── tagging/tagging-policy.json  # mandatory tag definitions and enforcement level
```

## Why the IAM policies appear twice

Terraform modules must be self-contained: a module that reads
`../../policies/...` breaks the moment it is consumed from a registry or a
different repository layout. So the canonical copy lives inside the module
(`modules/iam/policies/`) and this directory holds a reviewable mirror.

Drift between the two is prevented by a test, not by convention:

```bash
python -m pytest tests/test_policy_sync.py -q
```

If the copies differ the test fails with the exact diff. Edit the module copy,
then re-copy:

```bash
cp modules/iam/policies/*.tftpl policies/iam/
```

## Linting

```bash
python scripts/policy_lint.py
```

Rules (see the script docstring): no `Allow * on *`, no service-wide IAM grants,
`Principal: "*"` only inside Deny statements, guardrail documents must contain at
least one explicit Deny, `Version` must be `2012-10-17`.

## Templates are JSON, not HCL strings

`*.json.tftpl` files are real JSON with `${terraform_expression}` holes, rendered
with `templatefile()`. This keeps the policy reviewable as JSON in a PR while
still allowing account IDs and ARNs to be injected per environment.
