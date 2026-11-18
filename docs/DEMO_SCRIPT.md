# Demo script (4 minutes)

Record at 1080p with a readable terminal font (14 pt or larger, dark theme). No
AWS console footage: nothing is deployed, so showing a console would be fabrication.

## 0:00–0:25 — Problem and scope

> "This is an AWS landing zone platform: three isolated environments, seven
> Terraform modules, and a pipeline that never holds a long-lived credential.
> Everything you will see runs at zero cost, because no infrastructure is created."

Show the repository tree:

```bash
ls
tree -L 2 environments modules | head -40
```

## 0:25–1:10 — Validate all three environments

```bash
terraform fmt -recursive -check && echo "FORMAT OK"
for e in dev staging production; do
  (cd environments/$e && terraform init -backend=false -input=false >/dev/null && terraform validate -no-color)
done
```

Say: "Three independent roots, one module set. Validate requires no credentials."

## 1:10–2:00 — Plan without spending anything

```bash
cd environments/dev
terraform plan -no-color | tail -25
```

Point at `Plan: 46 to add` and `zero_cost_mode = true`. Then show the guard:

```bash
cd ../production
terraform plan -var zero_cost_mode=false -var instance_count=0 -var offline_plan_mode=true | tail -5
```

Say: "72 resources here — NAT per AZ, KMS, CloudTrail, backups. Still a plan, still
zero cost, and every billable flag is one edit away from off."

## 2:00–2:45 — Security scanning

```bash
cd ../..
python -m checkov.main -d . --framework terraform --config-file policies/scanners/checkov.yaml --compact --quiet | tail -12
python scripts/policy_lint.py | tail -8
python scripts/secret_scan.py | tail -6
```

Say: "202 passed, zero failed, and every skip is a dated accepted risk with a written
justification — not a silent exemption."

## 2:45–3:25 — Tests and drift

```bash
python -m pytest tests -q
python scripts/drift_report.py --environment dev --markdown reports/drift-dev.md | tail -12
```

Say: "The drift report labels candidates, not 'verified drift' — a plan cannot prove
that distinction, so the tool does not pretend it can."

## 3:25–4:00 — Pipeline and close

Open `.github/workflows/terraform-apply.yml` and scroll to the `environment:` and
`confirm_apply` guard.

Say: "Deployment is manual, binds to a protected GitHub Environment, and applies a
saved plan. No stored AWS keys anywhere — OIDC only. Nothing in this repository has
been deployed to AWS: that is the next step, with your authorisation."

## Do not

* Show an AWS console, CloudWatch graph or CloudTrail event: none exist.
* Claim a deployment, a restore test, or a TFLint run (it is not installed here).
* Speed up the terminal so output cannot be read.
