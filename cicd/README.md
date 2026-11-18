# cicd/

Reusable CI/CD assets. The GitHub Actions workflows in
[`.github/workflows/`](../.github/workflows) are the authoritative pipelines;
this directory holds the pieces they share and a script that reproduces the
pipeline locally.

| File | Purpose |
|---|---|
| `local-pipeline.ps1` | Runs the same ordered checks as CI on Windows |
| `local-pipeline.sh` | Same, for Linux/macOS runners |
| `tool-versions.txt` | Pinned tool versions used by CI and the docs |

## Pipeline order (and why)

```text
fmt -> init -backend=false -> validate -> tflint -> checkov -> trivy
    -> secret scan -> policy lint -> pytest -> docs lint -> plan -> (manual) apply
```

Fail fast on cheap checks before spending minutes on scanners, and never let a
scan run before `validate` proves the configuration parses.

## Secrets in CI

No AWS access keys exist in this repository. The plan and apply workflows assume
a role through GitHub OIDC (`id-token: write`), scoped by the trust policy in
`modules/iam/policies/github-oidc-trust.json.tftpl`. If OIDC is not configured,
the plan workflow still runs in zero-cost mode with no credentials.
