#!/usr/bin/env python3
"""Deployment preflight validation.

Runs the checks a careful engineer would run before asking for an apply
approval, and refuses to bless a production deployment without an explicit
authorisation flag.

Checks
------
1. Tooling available (terraform, python) and Terraform version >= 1.5.
2. Environment directory structure and initialisation state.
3. terraform.tfvars sanity: environment matches its directory, guard rails
   (`zero_cost_mode`, `offline_plan_mode`) are present.
4. Repository hygiene: no state/plan/key files, .gitignore covers them.
5. No long-lived AWS access keys in the environment (OIDC preferred).
6. `terraform fmt -check` and `terraform validate`.
7. Production authorisation gate.

Usage
-----
    python scripts/preflight.py --environment dev
    python scripts/preflight.py --environment production --i-approve-production

Exit codes
----------
    0  all required checks passed
    1  at least one FAIL
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eawlz_core as core  # noqa: E402

LOG = logging.getLogger("preflight")

REQUIRED_GITIGNORE_PATTERNS = (
    "*.tfstate",
    "*.tfplan",
    ".terraform",
    ".env",
    "backend.tf",
)


@dataclass
class Check:
    name: str
    status: str  # PASS | FAIL | WARN | SKIP
    detail: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="preflight",
        description="Validate readiness before a Terraform plan/apply.",
        epilog="Read-only: never runs apply. Production requires --i-approve-production.",
    )
    parser.add_argument("--environment", required=True, choices=["dev", "staging", "production"])
    parser.add_argument("--repo", default=None, help="Repository root (default: auto-detect).")
    parser.add_argument("--skip-validate", action="store_true", help="Skip terraform validate (faster).")
    parser.add_argument(
        "--i-approve-production",
        action="store_true",
        help="Acknowledge that a production change has been reviewed and cost-approved.",
    )
    parser.add_argument("--json", dest="json_out", default=None, help="Write checks as JSON.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def check_tooling() -> list[Check]:
    checks: list[Check] = []
    available, version = core.terraform_available()
    if not available:
        checks.append(Check("terraform installed", "FAIL", version))
    else:
        parts = version.split(".")
        try:
            major, minor = int(parts[0]), int(parts[1])
            ok = (major, minor) >= (1, 5)
        except (ValueError, IndexError):
            ok = False
        checks.append(
            Check(
                "terraform version >= 1.5",
                "PASS" if ok else "FAIL",
                f"found {version}",
            )
        )

    checks.append(Check("python >= 3.9", "PASS" if sys.version_info >= (3, 9) else "FAIL", sys.version.split()[0]))

    for tool in ("checkov", "trivy"):
        found = subprocess.run(  # noqa: S603,S607 - fixed tool names
            ["where" if os.name == "nt" else "which", tool],
            capture_output=True,
            text=True,
            check=False,
        )
        checks.append(
            Check(
                f"optional scanner: {tool}",
                "PASS" if found.returncode == 0 else "WARN",
                "available" if found.returncode == 0 else "not installed (CI installs it)",
            )
        )
    return checks


def check_environment(env_dir: Path, environment: str) -> list[Check]:
    checks: list[Check] = []

    if not env_dir.is_dir():
        return [Check("environment directory", "FAIL", f"missing: {env_dir}")]

    tf_files = sorted(env_dir.glob("*.tf"))
    checks.append(
        Check("terraform files present", "PASS" if tf_files else "FAIL", f"{len(tf_files)} .tf file(s)")
    )
    checks.append(
        Check(
            "initialised (.terraform/)",
            "PASS" if (env_dir / ".terraform").is_dir() else "WARN",
            "terraform init has been run" if (env_dir / ".terraform").is_dir() else "run `terraform init` first",
        )
    )

    tfvars_path = env_dir / "terraform.tfvars"
    if not tfvars_path.is_file():
        checks.append(Check("terraform.tfvars", "FAIL", "missing - environment values are required"))
        return checks

    values = core.parse_simple_tfvars(tfvars_path.read_text(encoding="utf-8"))
    declared = values.get("environment")
    checks.append(
        Check(
            "environment matches directory",
            "PASS" if declared == environment else "FAIL",
            f"tfvars declares '{declared}', directory is '{environment}'",
        )
    )

    for guard in ("zero_cost_mode", "offline_plan_mode"):
        present = guard in values
        checks.append(
            Check(
                f"guard rail: {guard}",
                "PASS" if present else "WARN",
                f"{values.get(guard)}" if present else "not declared - relying on the variable default",
            )
        )

    if environment == "production" and values.get("zero_cost_mode") is True:
        checks.append(
            Check(
                "production is in zero-cost mode",
                "WARN",
                "apply would create nothing; set zero_cost_mode = false during the change window",
            )
        )

    account = values.get("aws_account_id")
    checks.append(
        Check(
            "aws_account_id configured",
            "PASS" if account and account != "111122223333" else "WARN",
            "placeholder value - replace before a real deployment" if account == "111122223333" else str(account),
        )
    )
    return checks


def check_repo_hygiene(repo_root: Path) -> list[Check]:
    checks: list[Check] = []

    # Generated artefacts and provider caches are git-ignored: a local plan file
    # is not a commit candidate, so it must not fail preflight.
    ignored_roots = {".terraform", "artifacts", ".tools", ".scanner-cache", "node_modules", ".git"}

    offenders = [
        core.relpath(path, repo_root)
        for path in repo_root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in core.FORBIDDEN_TRACKED_SUFFIXES
        and not any(part in ignored_roots for part in path.relative_to(repo_root).parts)
    ]
    checks.append(
        Check(
            "no state/plan/key files in tree",
            "PASS" if not offenders else "FAIL",
            "clean" if not offenders else f"{len(offenders)} file(s): {', '.join(offenders[:5])}",
        )
    )

    gitignore = repo_root / ".gitignore"
    if not gitignore.is_file():
        checks.append(Check(".gitignore present", "FAIL", "missing"))
    else:
        content = gitignore.read_text(encoding="utf-8")
        missing = [pattern for pattern in REQUIRED_GITIGNORE_PATTERNS if pattern not in content]
        checks.append(
            Check(
                ".gitignore covers state/plan/secrets",
                "PASS" if not missing else "FAIL",
                "all patterns present" if not missing else f"missing: {', '.join(missing)}",
            )
        )

    # Long-lived keys are exactly what this project avoids; flag them loudly.
    long_lived = [name for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY") if os.environ.get(name)]
    checks.append(
        Check(
            "no long-lived AWS keys in environment",
            "PASS" if not long_lived else "WARN",
            "none set" if not long_lived else f"{', '.join(long_lived)} set - prefer OIDC/SSO",
        )
    )
    return checks


def check_terraform(env_dir: Path, skip_validate: bool) -> list[Check]:
    checks: list[Check] = []
    try:
        fmt = core.run_terraform(["fmt", "-check", "-recursive", "-no-color"], env_dir, timeout=120)
    except core.TerraformError as exc:
        return [Check("terraform fmt", "FAIL", str(exc))]
    checks.append(
        Check(
            "terraform fmt -check",
            "PASS" if fmt.returncode == 0 else "FAIL",
            "formatted" if fmt.returncode == 0 else "unformatted files (run terraform fmt -recursive)",
        )
    )

    if skip_validate:
        checks.append(Check("terraform validate", "SKIP", "disabled by --skip-validate"))
        return checks

    if not (env_dir / ".terraform").is_dir():
        checks.append(Check("terraform validate", "SKIP", "not initialised"))
        return checks

    try:
        validate = core.run_terraform(["validate", "-no-color"], env_dir, timeout=180)
    except core.TerraformError as exc:
        checks.append(Check("terraform validate", "FAIL", str(exc)))
        return checks
    checks.append(
        Check(
            "terraform validate",
            "PASS" if validate.returncode == 0 else "FAIL",
            "valid" if validate.returncode == 0 else core.strip_ansi(validate.stderr)[-300:],
        )
    )
    return checks


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )

    try:
        repo_root = Path(args.repo).resolve() if args.repo else core.find_repo_root(Path(__file__).resolve())
    except FileNotFoundError as exc:
        LOG.error("%s", exc)
        return 1

    env_dir = repo_root / "environments" / args.environment
    checks: list[Check] = []
    checks.extend(check_tooling())
    checks.extend(check_environment(env_dir, args.environment))
    checks.extend(check_repo_hygiene(repo_root))
    checks.extend(check_terraform(env_dir, args.skip_validate))

    if args.environment == "production":
        checks.append(
            Check(
                "production authorisation",
                "PASS" if args.i_approve_production else "FAIL",
                "acknowledged"
                if args.i_approve_production
                else "requires --i-approve-production after change/cost review",
            )
        )

    failures = [c for c in checks if c.status == "FAIL"]
    warnings = [c for c in checks if c.status == "WARN"]

    core.emit(f"PREFLIGHT — {args.environment}")
    core.emit("=" * (12 + len(args.environment)))
    core.emit(core.format_table(["CHECK", "STATUS", "DETAIL"], [(c.name, c.status, c.detail) for c in checks]))
    core.emit()
    core.emit(f"Summary: {len(checks) - len(failures) - len(warnings)} passed, {len(warnings)} warning(s), {len(failures)} failure(s)")

    if args.json_out:
        import json

        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(
                {
                    "environment": args.environment,
                    "checks": [c.__dict__ for c in checks],
                    "failures": len(failures),
                    "warnings": len(warnings),
                    "status": "fail" if failures else "pass",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    if failures:
        LOG.error("Preflight failed. Resolve the FAIL rows before planning or applying.")
        return 1
    LOG.info("Preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
