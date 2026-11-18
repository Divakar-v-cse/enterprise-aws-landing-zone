"""Repository contract tests: structure, policy sync, docs and workflow validity."""

import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

MODULES = ["networking", "security", "iam", "ec2", "s3", "monitoring", "backup"]
ENVIRONMENTS = ["dev", "staging", "production"]

REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    ".gitignore",
    "Makefile",
    ".env.example",
    ".tflint.hcl",
    "bootstrap/main.tf",
    "bootstrap/README.md",
    "examples/minimal-vpc/main.tf",
    "docs/PROJECT_AUDIT.md",
    "docs/ARCHITECTURE.md",
    "docs/INSTALLATION.md",
    "docs/TERRAFORM_SETUP.md",
    "docs/ENVIRONMENTS.md",
    "docs/NETWORKING.md",
    "docs/IAM_SECURITY.md",
    "docs/STORAGE_ENCRYPTION.md",
    "docs/MONITORING_AUDITING.md",
    "docs/CI_CD.md",
    "docs/SECURITY.md",
    "docs/COST_MANAGEMENT.md",
    "docs/BACKUP_DISASTER_RECOVERY.md",
    "docs/DRIFT_DETECTION.md",
    "docs/TESTING.md",
    "docs/TROUBLESHOOTING.md",
    "docs/TECHNICAL_INTERVIEW.md",
    "docs/RESUME_DESCRIPTION.md",
    "docs/DEPLOYMENT_GUIDE.md",
    "docs/DEMO_SCRIPT.md",
    "diagrams/aws-landing-zone-architecture.mmd",
    "diagrams/aws-landing-zone-architecture.png",
    "security/SECURITY_REPORT.md",
]


@pytest.mark.parametrize("relative", REQUIRED_FILES)
def test_required_file_exists(relative):
    path = REPO / relative
    assert path.is_file(), f"missing {relative}"
    assert path.stat().st_size > 200, f"{relative} looks empty"


@pytest.mark.parametrize("module", MODULES)
def test_module_contract(module):
    base = REPO / "modules" / module
    for filename in ("main.tf", "variables.tf", "outputs.tf", "versions.tf", "README.md"):
        assert (base / filename).is_file(), f"{module} missing {filename}"
    variables = (base / "variables.tf").read_text(encoding="utf-8")
    for block in re.findall(r"variable \"([a-z0-9_]+)\"", variables):
        assert f'"{block}"' in variables


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_environment_isolation(environment):
    base = REPO / "environments" / environment
    for filename in ("main.tf", "variables.tf", "outputs.tf", "providers.tf", "terraform.tfvars", "README.md"):
        assert (base / filename).is_file(), f"{environment} missing {filename}"

    tfvars = (base / "terraform.tfvars").read_text(encoding="utf-8")
    assert f'environment  = "{environment}"' in tfvars
    assert "zero_cost_mode" in tfvars

    # Every environment must get its own, non-overlapping VPC range.
    cidr = re.search(r'vpc_cidr\s*=\s*"([0-9.]+)/', tfvars)
    assert cidr, f"{environment} must declare vpc_cidr"
    expected = {"dev": "10.10.", "staging": "10.20.", "production": "10.30."}[environment]
    assert cidr.group(1).startswith(expected), f"{environment} VPC CIDR collides with another environment"


def test_policy_copies_match_module_templates():
    for template in sorted((REPO / "modules" / "iam" / "policies").glob("*.tftpl")):
        mirror = REPO / "policies" / "iam" / template.name
        assert mirror.is_file(), f"{mirror} missing - copy it from the module"
        assert mirror.read_text(encoding="utf-8") == template.read_text(encoding="utf-8"), (
            f"{template.name} differs between modules/iam/policies and policies/iam. "
            "Edit the module copy, then re-copy it."
        )


def test_workflows_are_valid_yaml_with_expected_triggers():
    workflows = sorted((REPO / ".github" / "workflows").glob("*.yml"))
    assert workflows, "no GitHub Actions workflows found"
    for workflow in workflows:
        document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        assert "on" in document or True in document
        assert "jobs" in document
        for job in document["jobs"].values():
            assert "runs-on" in job
            assert job.get("steps")


def test_deploy_workflow_requires_manual_dispatch_and_approval():
    deploy = REPO / ".github" / "workflows" / "terraform-apply.yml"
    text = deploy.read_text(encoding="utf-8")
    assert "workflow_dispatch" in text, "deployment must never run automatically"
    assert "environment:" in text, "deployment must bind to a protected GitHub Environment"
    assert "pull_request" not in text, "deployment must not trigger on pull requests"
    assert "confirm_apply" in text, "deployment must require an explicit confirmation input"


def test_gitignore_blocks_state_and_secrets():
    content = (REPO / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("*.tfstate", "*.tfplan", ".env", "*.pem", "backend.tf"):
        assert pattern in content


def test_no_state_or_plan_files_committed():
    """State, plan and key files must never sit in the tree outside ignored dirs."""
    ignored_roots = {".terraform", "artifacts", ".tools", ".scanner-cache", "node_modules", ".git"}
    offenders = [
        path for path in REPO.rglob("*")
        if path.is_file()
        and path.suffix in {".tfstate", ".tfplan", ".pem", ".key"}
        and not any(part in ignored_roots for part in path.relative_to(REPO).parts)
    ]
    assert offenders == [], f"forbidden files present: {offenders}"


def test_pricing_catalog_is_valid_json_with_disclaimer():
    catalog = json.loads((REPO / "scripts" / "lib" / "pricing_catalog.json").read_text(encoding="utf-8"))
    assert "NOT A BILL" in " ".join(catalog["_README"])
    assert catalog["hours_per_month"] == 730
    assert catalog["prices"]["ec2_hourly_usd"]["t3.micro"] > 0
