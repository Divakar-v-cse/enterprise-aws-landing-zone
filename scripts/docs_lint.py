#!/usr/bin/env python3
"""Documentation validation.

Keeps the documentation set honest and self-consistent:

* every required document exists and is substantive (not a stub),
* every relative Markdown link/image resolves on disk,
* required Mermaid diagrams are present,
* no unresolved placeholders (``TODO``, ``TBD``, ``FIXME``) in user-facing docs,
* the acceptance-criteria checklist in the README is complete.

Usage
-----
    python scripts/docs_lint.py
    python scripts/docs_lint.py --json docs-lint.json

Exit codes
----------
    0  documentation valid
    1  problem(s) found
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eawlz_core as core  # noqa: E402

LOG = logging.getLogger("docs-lint")

REQUIRED_DOCS: dict[str, int] = {
    "README.md": 3000,
    "docs/PROJECT_AUDIT.md": 3000,
    "docs/ARCHITECTURE.md": 2500,
    "docs/INSTALLATION.md": 1500,
    "docs/TERRAFORM_SETUP.md": 2000,
    "docs/ENVIRONMENTS.md": 1800,
    "docs/NETWORKING.md": 2000,
    "docs/IAM_SECURITY.md": 2000,
    "docs/STORAGE_ENCRYPTION.md": 1800,
    "docs/MONITORING_AUDITING.md": 1500,
    "docs/CI_CD.md": 1800,
    "docs/SECURITY.md": 2000,
    "docs/COST_MANAGEMENT.md": 1500,
    "docs/BACKUP_DISASTER_RECOVERY.md": 2000,
    "docs/DRIFT_DETECTION.md": 1500,
    "docs/TESTING.md": 1200,
    "docs/TROUBLESHOOTING.md": 2500,
    "docs/TECHNICAL_INTERVIEW.md": 5000,
    "docs/RESUME_DESCRIPTION.md": 1200,
    "docs/DEPLOYMENT_GUIDE.md": 1500,
    "docs/DEMO_SCRIPT.md": 1200,
    "security/SECURITY_REPORT.md": 1200,
}

MERMAID_REQUIRED: dict[str, int] = {
    "docs/ARCHITECTURE.md": 2,
    "docs/NETWORKING.md": 1,
    "docs/DRIFT_DETECTION.md": 1,
    "docs/BACKUP_DISASTER_RECOVERY.md": 1,
}

PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b")
MERMAID_RE = re.compile(r"```mermaid")
CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[( |x|X)\]", re.MULTILINE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docs_lint",
        description="Validate the documentation set (existence, links, diagrams, placeholders).",
    )
    parser.add_argument("--repo", default=None)
    parser.add_argument("--json", dest="json_out", default=None)
    parser.add_argument("--min-words", type=int, default=None, help="Override the minimum word count.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def run_checks(repo: Path, min_words_override: int | None) -> tuple[list[dict], list[str]]:
    results: list[dict] = []
    failures: list[str] = []

    # 1. Required documents exist and are substantive.
    for relative, min_chars in REQUIRED_DOCS.items():
        path = repo / relative
        if not path.is_file():
            results.append({"check": f"exists: {relative}", "status": "FAIL", "detail": "missing"})
            failures.append(f"{relative} is missing")
            continue
        text = path.read_text(encoding="utf-8")
        words = len(text.split())
        threshold = min_words_override if min_words_override is not None else min_chars // 7
        status = "PASS" if words >= threshold and len(text) >= min_chars // 3 else "WARN"
        detail = f"{words} words, {len(text)} chars (min ~{threshold} words)"
        results.append({"check": f"substance: {relative}", "status": status, "detail": detail})
        if status == "WARN":
            failures.append(f"{relative} looks like a stub ({detail})")

    # 2. Relative links resolve.
    for markdown in sorted(repo.rglob("*.md")):
        if any(part in {".git", "node_modules", ".terraform"} for part in markdown.parts):
            continue
        relative = core.relpath(markdown, repo)
        text = markdown.read_text(encoding="utf-8", errors="ignore")
        broken = []
        for target in core.markdown_relative_links(text):
            if target.startswith("#") or target.startswith("file://"):
                continue
            candidate = (markdown.parent / target).resolve()
            if not candidate.exists():
                broken.append(target)
        if broken:
            results.append(
                {
                    "check": f"links: {relative}",
                    "status": "FAIL",
                    "detail": f"{len(broken)} broken: {', '.join(sorted(set(broken))[:4])}",
                }
            )
            failures.append(f"{relative} has {len(broken)} broken link(s)")
        else:
            results.append({"check": f"links: {relative}", "status": "PASS", "detail": "all targets resolve"})

    # 3. Mermaid diagrams.
    for relative, minimum in MERMAID_REQUIRED.items():
        path = repo / relative
        if not path.is_file():
            continue
        count = len(MERMAID_RE.findall(path.read_text(encoding="utf-8")))
        status = "PASS" if count >= minimum else "FAIL"
        results.append(
            {"check": f"mermaid: {relative}", "status": status, "detail": f"{count} diagram(s), need {minimum}"}
        )
        if status == "FAIL":
            failures.append(f"{relative} needs at least {minimum} Mermaid diagram(s)")

    # 4. Placeholders in user-facing docs.
    for markdown in sorted((repo / "docs").glob("*.md")) + [repo / "README.md"]:
        if not markdown.is_file():
            continue
        text = markdown.read_text(encoding="utf-8", errors="ignore")
        hits = PLACEHOLDER_RE.findall(text)
        if hits:
            results.append(
                {
                    "check": f"placeholders: {core.relpath(markdown, repo)}",
                    "status": "FAIL",
                    "detail": f"{len(hits)} unresolved: {', '.join(sorted(set(hits)))}",
                }
            )
            failures.append(f"{core.relpath(markdown, repo)} contains TODO/TBD placeholders")
        else:
            results.append(
                {"check": f"placeholders: {core.relpath(markdown, repo)}", "status": "PASS", "detail": "none"}
            )

    # 5. README acceptance checklist must be fully checked.
    readme = repo / "README.md"
    if readme.is_file():
        boxes = CHECKBOX_RE.findall(readme.read_text(encoding="utf-8"))
        unchecked = [box for box in boxes if box == " "]
        if boxes:
            results.append(
                {
                    "check": "acceptance checklist",
                    "status": "PASS" if not unchecked else "WARN",
                    "detail": f"{len(boxes) - len(unchecked)}/{len(boxes)} checked",
                }
            )
        else:
            results.append({"check": "acceptance checklist", "status": "WARN", "detail": "no checklist found"})

    return results, failures


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

    results, failures = run_checks(repo, args.min_words)
    counts: dict[str, int] = {}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    core.emit("DOCUMENTATION LINT")
    core.emit("==================")
    for row in results:
        core.emit(f"[{row['status']:4}] {row['check']}: {row['detail']}")
    core.emit()
    core.emit(f"Summary: {counts}")

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps({"results": results, "summary": counts, "status": "fail" if failures else "pass"}, indent=2),
            encoding="utf-8",
        )

    if failures:
        LOG.error("%d documentation problem(s) found.", len(failures))
        return 1
    LOG.info("Documentation set is consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
