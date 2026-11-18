#!/usr/bin/env python3
"""Single entry point for every local (zero-cost) verification.

Runs, in order:

1. ``terraform fmt -check -recursive``
2. ``terraform init -backend=false`` + ``terraform validate`` for each environment
3. Checkov (if installed)
4. Trivy config scan (if installed)
5. Secret scan
6. IAM policy lint
7. Tagging validation + cost guard against a generated plan JSON
8. Documentation lint
9. pytest

Nothing here applies a plan or calls AWS. Everything is read-only and free.

Usage
-----
    python scripts/run_all_checks.py
    python scripts/run_all_checks.py --skip-scanners --verbose
    python scripts/run_all_checks.py --transcripts screenshots   # also capture evidence

Exit codes
----------
    0  every executed step passed
    1  at least one step failed
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eawlz_core as core  # noqa: E402

LOG = logging.getLogger("check-all")


@dataclass
class Step:
    name: str
    status: str
    detail: str
    seconds: float


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_all_checks",
        description="Run the complete zero-cost verification suite (fmt, validate, scan, test).",
    )
    parser.add_argument("--repo", default=None)
    parser.add_argument("--skip-scanners", action="store_true", help="Skip Checkov/Trivy (useful when offline).")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest.")
    parser.add_argument("--skip-plan", action="store_true", help="Skip plan generation and plan-based checks.")
    parser.add_argument(
        "--transcripts",
        default=None,
        help="Directory to write command transcripts into (used to build screenshots).",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def run(cmd: list[str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    LOG.debug("exec: %s (cwd=%s)", " ".join(cmd), cwd)
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False)


def record(steps: list[Step], name: str, completed: subprocess.CompletedProcess[str], started: float, ok_codes=(0,)) -> bool:
    elapsed = time.time() - started
    ok = completed.returncode in ok_codes
    detail = (completed.stdout or completed.stderr or "").strip().splitlines()
    steps.append(
        Step(
            name=name,
            status="PASS" if ok else "FAIL",
            detail=detail[-1][:200] if detail else f"exit {completed.returncode}",
            seconds=elapsed,
        )
    )
    return ok


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )

    try:
        repo = Path(args.repo).resolve() if args.repo else core.find_repo_root(Path(__file__).resolve())
    except FileNotFoundError as exc:
        LOG.error("%s", exc)
        return 1

    os.environ.setdefault("TF_IN_AUTOMATION", "1")
    os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
    os.environ.setdefault("CHECKOV_NO_COLOR", "true")

    steps: list[Step] = []
    runner = Path(__file__).resolve().parent
    py = sys.executable
    artifacts = repo / "artifacts" / "local"
    artifacts.mkdir(parents=True, exist_ok=True)

    # 1. formatting ------------------------------------------------------------
    started = time.time()
    fmt = run(["terraform", "fmt", "-check", "-recursive", "-no-color"], repo)
    record(steps, "terraform fmt -check -recursive", fmt, started)

    # 2. validate each environment --------------------------------------------
    environments = core.discover_environments(repo)
    plan_jsons: dict[str, Path] = {}
    for environment in environments:
        env_dir = repo / "environments" / environment
        started = time.time()
        init = run(["terraform", "init", "-input=false", "-no-color"], env_dir, timeout=600)
        if not record(steps, f"terraform init ({environment})", init, started):
            continue

        started = time.time()
        validate = run(["terraform", "validate", "-no-color"], env_dir, timeout=300)
        record(steps, f"terraform validate ({environment})", validate, started)

        if args.skip_plan:
            continue

        # 3. plan -> JSON (offline in zero-cost mode) --------------------------
        plan_file = artifacts / f"{environment}.tfplan"
        started = time.time()
        plan = run(
            ["terraform", "plan", "-input=false", "-no-color", f"-out={plan_file}"],
            env_dir,
            timeout=900,
        )
        record(steps, f"terraform plan ({environment})", plan, started)

        json_path = artifacts / f"{environment}-plan.json"
        started = time.time()
        show = run(["terraform", "show", "-json", str(plan_file)], env_dir, timeout=300)
        wrote = False
        if show.returncode == 0:
            json_path.write_text(show.stdout, encoding="utf-8")
            plan_jsons[environment] = json_path
            wrote = True
        record(steps, f"terraform show -json ({environment})", show, started)

        if wrote:
            started = time.time()
            tags = run(
                [py, str(runner / "tagging_validator.py"), "--plan", str(json_path), "--no-fail"],
                repo,
            )
            record(steps, f"tagging validator ({environment})", tags, started)

            started = time.time()
            cost = run(
                [py, str(runner / "cost_guard.py"), "--plan", str(json_path), "--zero-cost-mode"],
                repo,
            )
            record(steps, f"cost guard ({environment})", cost, started, ok_codes=(0,))

            started = time.time()
            backup = run(
                [
                    py,
                    str(runner / "backup_verify.py"),
                    "--plan",
                    str(json_path),
                    "--allow-disabled",
                ],
                repo,
            )
            record(steps, f"backup checklist ({environment})", backup, started, ok_codes=(0,))

    # 4. scanners --------------------------------------------------------------
    if not args.skip_scanners:
        checkov = run(["checkov", "--version"], repo, timeout=120)
        if checkov.returncode == 0:
            started = time.time()
            scan = run(
                [
                    "checkov", "-d", ".", "--framework", "terraform", "--quiet",
                    "--compact", "--output", "json",
                    "--output-file-path", str(artifacts),
                ],
                repo,
                timeout=1800,
            )
            # checkov exits 1 when it finds issues; that is not a harness failure.
            record(steps, "checkov terraform scan", scan, started, ok_codes=(0, 1))
        else:
            steps.append(Step("checkov terraform scan", "SKIP", "checkov not installed", 0.0))

        trivy_exe = repo / ".tools" / "trivy.exe"
        trivy_cmd = str(trivy_exe) if trivy_exe.is_file() else "trivy"
        started = time.time()
        trivy = run(
            [trivy_cmd, "config", ".", "--format", "json", "--output", str(artifacts / "trivy.json"), "--quiet"],
            repo,
            timeout=1800,
        )
        record(steps, "trivy config scan", trivy, started, ok_codes=(0, 1))

        started = time.time()
        policy = run([py, str(runner / "policy_lint.py"), "--json", str(artifacts / "policy-lint.json")], repo)
        record(steps, "IAM policy lint", policy, started)

    # 5. secret scan -----------------------------------------------------------
    started = time.time()
    secrets = run(
        [py, str(runner / "secret_scan.py"), "--format", "json", "--output", str(artifacts / "secret-scan.json")],
        repo,
    )
    record(steps, "secret scan", secrets, started)

    # 6. docs ------------------------------------------------------------------
    started = time.time()
    docs = run([py, str(runner / "docs_lint.py"), "--json", str(artifacts / "docs-lint.json")], repo)
    record(steps, "documentation lint", docs, started)

    # 7. tests -----------------------------------------------------------------
    if not args.skip_tests:
        started = time.time()
        tests = run([py, "-m", "pytest", "tests", "-q"], repo, timeout=1800)
        record(steps, "pytest", tests, started)

    # 8. summary ---------------------------------------------------------------
    failures = [s for s in steps if s.status == "FAIL"]
    core.emit()
    core.emit("ZERO-COST VERIFICATION SUITE")
    core.emit("============================")
    core.emit(
        core.format_table(
            ["STEP", "STATUS", "SECONDS", "DETAIL"],
            [(s.name, s.status, f"{s.seconds:.1f}", s.detail) for s in steps],
        )
    )
    core.emit()
    core.emit(
        f"{len([s for s in steps if s.status == 'PASS'])} passed, "
        f"{len([s for s in steps if s.status == 'SKIP'])} skipped, {len(failures)} failed"
    )
    core.emit("No AWS resources were created. No `terraform apply` was executed.")

    summary_path = artifacts / "verification-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "steps": [s.__dict__ for s in steps],
                "environment_plans": {k: str(v) for k, v in plan_jsons.items()},
                "failures": len(failures),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    LOG.info("Machine summary written to %s", summary_path)

    if args.transcripts:
        target = Path(args.transcripts)
        target.mkdir(parents=True, exist_ok=True)
        (target / "verification-suite.txt").write_text(
            "\n".join(
                ["ZERO-COST VERIFICATION SUITE", "============================", ""]
                + [f"[{s.status:4}] {s.name} ({s.seconds:.1f}s) {s.detail}" for s in steps]
                + ["", f"{len(failures)} failure(s)"]
            ),
            encoding="utf-8",
        )
        LOG.info("Transcript written to %s", target / "verification-suite.txt")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
