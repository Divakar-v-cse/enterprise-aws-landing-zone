#!/usr/bin/env python3
"""Aggregate scanner output into security/SECURITY_REPORT.md.

Consumes the JSON produced by:

* Checkov (Terraform static analysis)
* Trivy (IaC misconfiguration scanning)
* scripts/secret_scan.py
* scripts/policy_lint.py

and renders a single, reviewable Markdown report. The report only states what
the scanners actually returned — it never claims a clean bill of health for a
scanner that did not run.

Usage
-----
    checkov -d . -o json --output-file-path security/raw
    trivy config . --format json -o security/raw/trivy.json
    python scripts/secret_scan.py --format json --output security/raw/secret-scan.json
    python scripts/policy_lint.py --json security/raw/policy-lint.json
    python scripts/security_report.py

Exit codes
----------
    0  report written
    1  a supplied input could not be parsed
    2  --strict and failures were found
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eawlz_core as core  # noqa: E402

LOG = logging.getLogger("security-report")

SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="security_report",
        description="Merge Checkov / Trivy / secret-scan / policy-lint output into one report.",
    )
    parser.add_argument("--checkov", default="security/raw/checkov.json")
    parser.add_argument("--trivy", default="security/raw/trivy.json")
    parser.add_argument("--secret-scan", default="security/raw/secret-scan.json")
    parser.add_argument("--policy-lint", default="security/raw/policy-lint.json")
    parser.add_argument("--output", default="security/SECURITY_REPORT.md")
    parser.add_argument("--repo", default=None)
    parser.add_argument("--strict", action="store_true", help="Exit 2 when any scanner reports failures.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def _load(path: Path) -> Any | None:
    if not path.is_file():
        LOG.warning("Input not found, section will be marked as not run: %s", path)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        LOG.error("Could not parse %s: %s", path, exc)
        raise


def parse_checkov(document: Any) -> dict[str, Any] | None:
    """Normalise Checkov's JSON output (single-document or list form)."""
    if document is None:
        return None
    if isinstance(document, list):
        document = document[0] if document else {}
    results = (document or {}).get("results", {})
    failed = results.get("failed_checks", []) or []
    passed = results.get("passed_checks", []) or []
    skipped = results.get("skipped_checks", []) or []

    items = []
    for check in failed:
        items.append(
            {
                "id": check.get("check_id", "?"),
                "name": (check.get("check_name") or "").strip(),
                "file": str(check.get("file_path", "")).lstrip("/"),
                "line": (check.get("file_line_range") or [0])[0],
                "severity": str(check.get("severity") or "UNKNOWN").upper(),
                "resource": check.get("resource", ""),
            }
        )
    items.sort(key=lambda i: (SEVERITY_ORDER.index(i["severity"]) if i["severity"] in SEVERITY_ORDER else 4, i["id"]))
    return {
        "failed": items,
        "passed": len(passed),
        "skipped": len(skipped),
        "summary": (document or {}).get("summary", {}),
    }


def parse_trivy(document: Any) -> dict[str, Any] | None:
    if document is None:
        return None
    results = (document or {}).get("Results", []) or []
    items = []
    for result in results:
        for misconfig in result.get("Misconfigurations", []) or []:
            if str(misconfig.get("Status", "")).upper() not in {"FAIL", "FAILED"}:
                continue
            cause = misconfig.get("CauseMetadata") or {}
            items.append(
                {
                    "id": misconfig.get("ID") or misconfig.get("AVDID") or "?",
                    "title": misconfig.get("Title", ""),
                    "severity": str(misconfig.get("Severity", "UNKNOWN")).upper(),
                    "target": result.get("Target", ""),
                    "line": cause.get("StartLine", 0),
                    "resolution": misconfig.get("Resolution", ""),
                }
            )
    items.sort(key=lambda i: (SEVERITY_ORDER.index(i["severity"]) if i["severity"] in SEVERITY_ORDER else 4, i["id"]))
    return {"failed": items, "targets": len(results)}


def accepted_risks(checkov_config: Path) -> list[tuple[str, str]]:
    """Read skip-check IDs and their justifications from the Checkov config."""
    if not checkov_config.is_file():
        return []
    risks: list[tuple[str, str]] = []
    current_comment = ""
    for line in checkov_config.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            current_comment = stripped.lstrip("# ").strip()
            continue
        if stripped.startswith("- CKV_") or stripped.startswith("- BC_"):
            risks.append((stripped.lstrip("- ").strip(), current_comment))
            current_comment = ""
    return risks


def build_report(
    checkov: dict | None,
    trivy: dict | None,
    secrets: dict | None,
    policy: dict | None,
    risks: list[tuple[str, str]],
) -> str:
    today = date.today().isoformat()
    lines: list[str] = [
        "# Security scan report",
        "",
        f"Generated: **{today}** by `scripts/security_report.py`  ",
        "Scope: static analysis of the Terraform configuration in this repository. "
        "No AWS account was scanned, because no infrastructure was deployed.",
        "",
        "> This report reflects what the scanners returned on the date above. "
        "A passing scan is not proof of a secure deployment: static analysis cannot "
        "see runtime configuration, patch level, credentials or live IAM evaluation.",
        "",
        "## Tool summary",
        "",
        "| Tool | Scope | Result |",
        "|---|---|---|",
    ]

    if checkov:
        failed = len(checkov["failed"])
        lines.append(
            f"| Checkov | Terraform static analysis | {failed} failed / {checkov['passed']} passed / "
            f"{checkov['skipped']} skipped |"
        )
    else:
        lines.append("| Checkov | Terraform static analysis | not run in this environment |")

    if trivy:
        failed = len(trivy["failed"])
        lines.append(f"| Trivy (config) | IaC misconfiguration | {failed} failure(s) across {trivy['targets']} target(s) |")
    else:
        lines.append("| Trivy (config) | IaC misconfiguration | not run in this environment |")

    if secrets:
        findings = len(secrets.get("findings", []) or [])
        forbidden = len(secrets.get("forbidden_files", []) or [])
        lines.append(
            f"| secret_scan.py | Credentials in working tree | {findings} finding(s), {forbidden} forbidden file(s) |"
        )
    else:
        lines.append("| secret_scan.py | Credentials in working tree | not run |")

    if policy:
        findings = policy.get("findings", []) or []
        failures = len([f for f in findings if f.get("severity") == "FAIL"])
        lines.append(f"| policy_lint.py | IAM least privilege | {failures} violation(s), {len(findings) - failures} warning(s) |")
    else:
        lines.append("| policy_lint.py | IAM least privilege | not run |")

    lines.extend(["", "## Findings", ""])

    # --- Checkov ------------------------------------------------------------
    lines.append("### Checkov")
    lines.append("")
    if not checkov:
        lines.append("_Checkov did not run in this environment; see the CI workflow for the authoritative run._")
    elif not checkov["failed"]:
        lines.append("No failed checks.")
    else:
        lines.append("| ID | Severity | Check | File | Line |")
        lines.append("|---|---|---|---|---|")
        for item in checkov["failed"]:
            lines.append(
                f"| `{item['id']}` | {item['severity']} | {item['name']} | `{item['file']}` | {item['line']} |"
            )

    # --- Trivy --------------------------------------------------------------
    lines.extend(["", "### Trivy (IaC misconfiguration)", ""])
    if not trivy:
        lines.append("_Trivy did not run in this environment._")
    elif not trivy["failed"]:
        lines.append("No misconfigurations reported.")
    else:
        lines.append("| ID | Severity | Title | Target | Line |")
        lines.append("|---|---|---|---|---|")
        for item in trivy["failed"]:
            lines.append(
                f"| `{item['id']}` | {item['severity']} | {item['title']} | `{item['target']}` | {item['line']} |"
            )

    # --- Secrets ------------------------------------------------------------
    lines.extend(["", "### Secret scanning", ""])
    if not secrets:
        lines.append("_Secret scan did not run._")
    elif secrets.get("status") == "pass":
        lines.append(
            f"No credential patterns found across {secrets.get('files_scanned', 0)} files "
            f"({secrets.get('files_skipped', 0)} skipped: binaries, vendored code, allowlisted examples)."
        )
    else:
        lines.append("| File | Line | Rule | Redacted match |")
        lines.append("|---|---|---|---|")
        for finding in secrets.get("findings", []) or []:
            lines.append(
                f"| `{finding['path']}` | {finding['line']} | {finding['rule']} | `{finding['excerpt']}` |"
            )
        for item in secrets.get("forbidden_files", []) or []:
            lines.append(f"| `{item}` | – | forbidden file type | – |")

    # --- IAM policy lint ----------------------------------------------------
    lines.extend(["", "### IAM policy lint", ""])
    if not policy:
        lines.append("_Policy lint did not run._")
    elif not policy.get("findings"):
        lines.append(f"No findings across {policy.get('documents', 0)} policy document(s).")
    else:
        lines.append("| Rule | Severity | Detail |")
        lines.append("|---|---|---|")
        for finding in policy["findings"]:
            lines.append(f"| `{finding['rule']}` | {finding['severity']} | {finding['detail']} |")

    # --- Accepted risks -----------------------------------------------------
    lines.extend(["", "## Accepted risks and documented exceptions", ""])
    if risks:
        lines.append("| Check | Justification |")
        lines.append("|---|---|")
        for check_id, justification in risks:
            lines.append(f"| `{check_id}` | {justification or 'see policies/scanners/checkov.yaml'} |")
    else:
        lines.append("No skip rules configured.")

    lines.extend(
        [
            "",
            "## Known limitations of this report",
            "",
            "1. **No live account was scanned.** Account-level controls (SCPs, GuardDuty,",
            "   Security Hub, IAM Access Analyzer, Config rules) are out of scope because",
            "   the project is validated in zero-cost mode.",
            "2. **Static analysis only.** Runtime drift, patch state and credential",
            "   exposure at runtime are not visible here.",
            "3. **Version-pinned rules.** Scanner rule sets change between releases; the",
            "   versions used are recorded in the CI log and in `security/raw/`.",
            "4. **Passing this report does not authorise a deployment.** Deployment",
            "   requires the approval gate described in `docs/DEPLOYMENT.md`.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "python scripts/run_all_checks.py        # fmt, validate, scan, test",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


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

    try:
        checkov = parse_checkov(_load(repo / args.checkov))
        trivy = parse_trivy(_load(repo / args.trivy))
        secrets = _load(repo / args.secret_scan)
        policy = _load(repo / args.policy_lint)
    except json.JSONDecodeError:
        return 1

    risks = accepted_risks(repo / "policies" / "scanners" / "checkov.yaml")
    report = build_report(checkov, trivy, secrets, policy, risks)

    output = repo / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    LOG.info("Report written to %s (%d bytes)", output, len(report))

    totals = {
        "checkov_failed": len(checkov["failed"]) if checkov else 0,
        "trivy_failed": len(trivy["failed"]) if trivy else 0,
        "secret_findings": len((secrets or {}).get("findings", []) or []),
        "policy_failures": len([f for f in (policy or {}).get("findings", []) if f.get("severity") == "FAIL"]),
    }
    core.emit(
        core.format_table(["SCANNER", "FAILURES"], [(k, v) for k, v in totals.items()])
    )

    if args.strict and sum(totals.values()) > 0:
        LOG.error("Strict mode: %d total finding(s).", sum(totals.values()))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
