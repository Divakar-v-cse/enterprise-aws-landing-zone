# Installation

## 1. Tools

| Tool | Version used | Required |
|---|---|---|
| Terraform | 1.15.8 (>= 1.5) | yes |
| Python | 3.12 (>= 3.9) | yes |
| Git | 2.44 | yes |
| Checkov | 3.4.5 | recommended |
| Trivy | 0.76.2 | recommended |
| TFLint | 0.53.0 | recommended |
| AWS CLI | v2 | deployment only |

Pinned versions live in [`cicd/tool-versions.txt`](../cicd/tool-versions.txt).

## 2. Windows (PowerShell, run as your normal user)

```powershell
winget install --id Hashicorp.Terraform -e
winget install --id Python.Python.3.12 -e
winget install --id Git.Git -e
winget install --id TerraformLinters.tflint -e

python -m pip install --upgrade pip checkov==3.4.5 pillow pyyaml pytest

# Trivy ships as a release zip; keep the binary inside the ignored .tools folder
$tmp = "$env:TEMP\trivy"
New-Item -ItemType Directory -Force $tmp | Out-Null
Invoke-WebRequest "https://github.com/aquasecurity/trivy/releases/download/v0.76.2/trivy_0.76.2_windows-64bit.zip" -OutFile "$tmp\trivy.zip"
Expand-Archive "$tmp\trivy.zip" -DestinationPath $tmp -Force
New-Item -ItemType Directory -Force .tools | Out-Null
Copy-Item "$tmp\trivy.exe" .tools/trivy.exe
```

## 3. Linux and macOS

Use your distribution packages or the official install scripts for Terraform,
TFLint and Trivy, then:

```bash
python3 -m pip install --user --upgrade checkov==3.4.5 pytest pyyaml
```

Package manager commands require elevated privileges on most systems; the exact
invocation depends on your distribution and is deliberately not hard-coded here.

## 4. Verify the install

```bash
git clone https://github.com/Divakar-v-cse/enterprise-aws-landing-zone.git
cd enterprise-aws-landing-zone

python -m pytest tests -q
cd environments/dev
terraform init
terraform validate
terraform plan
```

Expected: `Success! The configuration is valid.` followed by
`Plan: 46 to add, 0 to change, 0 to destroy.` No AWS credentials are needed for
that plan.

## 5. AWS credentials (deployment only)

```bash
aws configure sso
aws sso login --profile landing-zone
export AWS_PROFILE=landing-zone     # PowerShell: $env:AWS_PROFILE = "landing-zone"
```

Then set `offline_plan_mode = false` in the environment's tfvars. Never create
long-lived access keys; CI authenticates with OIDC.

## 6. Common install problems

| Symptom | Fix |
|---|---|
| `terraform: command not found` | Re-open the shell and check `PATH` |
| Provider checksum mismatch | Remove the environment's `.terraform` folder and re-run `terraform init` |
| `checkov: command not found` | Invoke `python -m checkov.main` |
| `ModuleNotFoundError: yaml` | `python -m pip install pyyaml` |
| Trivy cache permission error | `export TRIVY_CACHE_DIR=$PWD/.scanner-cache/trivy` |
