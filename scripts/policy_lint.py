#!/usr/bin/env python3
"""IAM policy-as-code validation.

Parses every policy document in ``policies/`` and every Terraform policy
template in ``modules/iam/policies/`` and applies least-privilege lint rules.

Rules
-----
PL001  Document must be valid JSON after template rendering.
PL002  Statement must declare Version "2012-10-17".
PL003  Allow with Action "*" and Resource "*" is forbidden (effective admin).
PL004  Allow on iam:*/organizations:*/account:* is forbidden.
PL005  Principal "*" is only allowed inside a Deny statement.
PL006  Allow with NotAction is flagged (implicitly grants everything else).
PL007  Conditional allow on s3:PutObject should not use a wildcard bucket resource.
PL008  Guardrail documents must contain at least one explicit Deny.

Usage
-----
    python scripts/policy_lint.py
    python scripts/policy_lint.py --json security/raw/policy-lint.json

Exit codes
----------
    0  no violations (warnings allowed)
    1  violations found or a document could not be parsed
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eawlz_core as core  # noqa: E402

LOG = logging.getLogger("policy-lint")

TEMPLATE_VAR_RE = re.compile(r"\$\{([^}]+)\}")
PRIVILEGED_SERVICES = ("iam:", "organizations:", "account:", "sso:", "sso-admin:")

#: Documents that are expected to carry explicit Deny guard rails.
GUARDRAIL_DOCUMENTS = ("permission-boundary", "ci-terraform-deploy", "ec2-app-policy")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="policy_lint",
        description="Lint IAM policy JSON documents and Terraform policy templates.",
    )
    parser.add_argument("--repo", default=None)
    parser.add_argument("--json", dest="json_out", default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def render_template(text: str) -> str:
    """Substitute Terraform template expressions with safe dummy values.

    ``${jsonencode(x)}`` renders as a JSON array (it appears unquoted in the
    templates), every other expression renders as a quoted placeholder string.
    """
    def replace(match: re.Match[str]) -> str:
        expression = match.group(1).strip()
        if expression.startswith("jsonencode("):
            return '["us-east-1"]'
        return "placeholder-value"

    # jsonencode() may appear unquoted, so handle it before generic replacement.
    text = re.sub(r"\$\{(jsonencode\([^}]*\))\}", lambda m: '["us-east-1"]', text)
    return TEMPLATE_VAR_RE.sub(replace, text)


def load_documents(repo: Path) -> list[tuple[str, Any]]:
    """Load policy JSON documents plus rendered Terraform templates."""
    documents: list[tuple[str, Any]] = []

    # Only IAM policy documents: budget/tagging/scanner configs are not policies.
    for path in sorted(repo.glob("policies/iam/**/*.json")):
        relative = core.relpath(path, repo)
        try:
            documents.append((relative, json.loads(path.read_text(encoding="utf-8"))))
        except json.JSONDecodeError as exc:
            documents.append((relative, exc))

    for path in sorted(repo.glob("modules/**/policies/*.tftpl")):
        relative = core.relpath(path, repo)
        rendered = render_template(path.read_text(encoding="utf-8"))
        try:
            documents.append((relative, json.loads(rendered)))
        except json.JSONDecodeError as exc:
            documents.append((relative, exc))

    return documents


def listify(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def lint_document(name: str, document: Any) -> list[tuple[str, str, str]]:
    findings: list[tuple[str, str, str]] = []

    if isinstance(document, Exception):
        findings.append(("PL001", "FAIL", f"{name}: invalid JSON after rendering ({document})"))
        return findings

    if not isinstance(document, dict):
        findings.append(("PL001", "FAIL", f"{name}: policy root must be an object"))
        return findings

    if document.get("Version") != "2012-10-17":
        findings.append(("PL002", "FAIL", f"{name}: Version must be '2012-10-17'"))

    statements = document.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]
    if not isinstance(statements, list) or not statements:
        findings.append(("PL001", "FAIL", f"{name}: no Statement entries"))
        return findings

    has_deny = False
    for index, statement in enumerate(statements):
        if not isinstance(statement, dict):
            findings.append(("PL001", "FAIL", f"{name}: statement {index} is not an object"))
            continue

        effect = str(statement.get("Effect", "")).lower()
        actions = [str(a) for a in listify(statement.get("Action"))]
        not_actions = [str(a) for a in listify(statement.get("NotAction"))]
        resources = [str(r) for r in listify(statement.get("Resource"))]
        sid = statement.get("Sid", f"statement-{index}")

        if effect == "deny":
            has_deny = True

        if effect == "allow":
            if "*" in actions and "*" in resources:
                findings.append(("PL003", "FAIL", f"{name}#{sid}: Allow '*' on '*' is effective admin"))
            # Only *service-wide* grants are a violation: a scoped action such as
            # iam:CreateRole is legitimate for the CI role that manages modules.
            if any(
                action == "*" or any(action == f"{svc}*" for svc in PRIVILEGED_SERVICES)
                for action in actions
            ):
                findings.append(
                    ("PL004", "FAIL", f"{name}#{sid}: Allow on privileged service actions ({actions[:3]})")
                )
            if not_actions:
                findings.append(
                    ("PL006", "WARN", f"{name}#{sid}: Allow with NotAction grants everything else")
                )

        principals = statement.get("Principal")
        if principals is not None:
            flat = json.dumps(principals)
            if '"*"' in flat and effect != "deny":
                findings.append(
                    ("PL005", "FAIL", f"{name}#{sid}: Principal '*' used outside a Deny statement")
                )

        for action in actions:
            if action.startswith("s3:PutObject") and any(r.strip() == "*" for r in resources):
                findings.append(
                    (
                        "PL007",
                        "WARN",
                        f"{name}#{sid}: PutObject on a whole-bucket wildcard - scope to a prefix",
                    )
                )

    if any(marker in name for marker in GUARDRAIL_DOCUMENTS) and not has_deny:
        findings.append(("PL008", "FAIL", f"{name}: guardrail document has no explicit Deny statement"))

    return findings


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

    documents = load_documents(repo)
    if not documents:
        LOG.error("No policy documents found under policies/ or modules/*/policies/.")
        return 1

    all_findings: list[tuple[str, str, str]] = []
    for name, document in documents:
        findings = lint_document(name, document)
        all_findings.extend(findings)
        status = "FAIL" if any(f[1] == "FAIL" for f in findings) else "PASS"
        core.emit(f"[{status:4}] {name}")

    failures = [f for f in all_findings if f[1] == "FAIL"]
    warnings = [f for f in all_findings if f[1] == "WARN"]

    core.emit()
    if all_findings:
        core.emit(core.format_table(["RULE", "SEVERITY", "DETAIL"], all_findings))
    else:
        core.emit("No policy lint findings.")
    core.emit()
    core.emit(f"Documents: {len(documents)} · failures: {len(failures)} · warnings: {len(warnings)}")

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(
                {
                    "documents": len(documents),
                    "findings": [{"rule": r, "severity": s, "detail": d} for r, s, d in all_findings],
                    "status": "fail" if failures else "pass",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    if failures:
        LOG.error("%d policy violation(s) found.", len(failures))
        return 1
    LOG.info("All policy documents passed least-privilege lint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
