#!/usr/bin/env python3
"""Repository secret scanner.

Scans the working tree for credential-shaped strings (AWS keys, private keys,
tokens, assigned passwords) and for files that must never be committed
(*.tfstate, *.tfplan, private keys).

This is a defence-in-depth helper, not a replacement for GitHub secret scanning
or gitleaks: it has no history awareness and no entropy model beyond the regexes
in ``scripts/lib/eawlz_core.py``.

Usage
-----
    python scripts/secret_scan.py                     # scan the repo
    python scripts/secret_scan.py --format json \
        --output security/raw/secret-scan.json
    python scripts/secret_scan.py --path . --include-allowlisted  # self-test

Exit codes
----------
    0  no findings
    1  findings or scan error
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eawlz_core as core  # noqa: E402

LOG = logging.getLogger("secret-scan")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="secret_scan",
        description="Scan the repository for committed credentials and forbidden files.",
        epilog="Findings are reported with the secret redacted so the report itself is safe to commit.",
    )
    parser.add_argument("--path", default=None, help="Path to scan (default: repository root).")
    parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format (default: text)."
    )
    parser.add_argument("--output", default=None, help="Write the report to this file as well as stdout.")
    parser.add_argument(
        "--include-allowlisted",
        action="store_true",
        help="Also scan files that normally contain example secrets (docs/tests).",
    )
    parser.add_argument(
        "--no-fail", action="store_true", help="Always exit 0 (report-only mode for exploration)."
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return parser


def scan(root: Path, include_allowlisted: bool) -> dict[str, object]:
    """Scan every eligible file under ``root``."""
    findings: list[dict[str, object]] = []
    forbidden: list[str] = []
    scanned = 0
    skipped = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = core.relpath(path, root)

        # Generated artefacts and provider caches are git-ignored, so a local
        # plan file is not a commit candidate. Flagging it would train people
        # to ignore the scanner.
        ignored_parts = {".terraform", "artifacts", ".tools", ".scanner-cache", "node_modules"}
        if any(part in ignored_parts for part in path.relative_to(root).parts):
            skipped += 1
            continue

        if path.suffix.lower() in core.FORBIDDEN_TRACKED_SUFFIXES:
            forbidden.append(relative)
            continue

        if not core.should_scan_file(path, root):
            skipped += 1
            continue
        if not include_allowlisted and core.is_allowlisted(relative):
            skipped += 1
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:  # unreadable file should not abort the scan
            LOG.debug("unreadable file %s: %s", relative, exc)
            skipped += 1
            continue

        scanned += 1
        for finding in core.scan_text_for_secrets(text, relative):
            findings.append(
                {
                    "path": finding.path,
                    "line": finding.line,
                    "rule": finding.rule,
                    "excerpt": finding.excerpt,
                }
            )

    return {
        "scanner": "secret_scan.py",
        "root": str(root),
        "files_scanned": scanned,
        "files_skipped": skipped,
        "findings": findings,
        "forbidden_files": forbidden,
        "status": "fail" if findings or forbidden else "pass",
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )

    try:
        root = Path(args.path).resolve() if args.path else core.find_repo_root(Path(__file__).resolve())
    except FileNotFoundError as exc:
        LOG.error("%s", exc)
        return 1

    LOG.info("Scanning %s", root)
    report = scan(root, args.include_allowlisted)

    if args.format == "json":
        rendered = json.dumps(report, indent=2)
    else:
        lines = [
            "SECRET SCAN REPORT",
            "==================",
            f"Root            : {report['root']}",
            f"Files scanned   : {report['files_scanned']}",
            f"Files skipped   : {report['files_skipped']} (binary, vendor, allowlisted)",
            f"Findings        : {len(report['findings'])}",
            f"Forbidden files : {len(report['forbidden_files'])}",
            "",
        ]
        if report["forbidden_files"]:
            lines.append("Files that must never be committed:")
            lines.extend(f"  - {item}" for item in report["forbidden_files"])
            lines.append("")
        if report["findings"]:
            rows = [(f["path"], f["line"], f["rule"], f["excerpt"]) for f in report["findings"]]
            lines.append(core.format_table(["FILE", "LINE", "RULE", "REDACTED MATCH"], rows))
        else:
            lines.append("No credential patterns matched.")
        lines.append("")
        lines.append(f"RESULT: {'FAIL' if report['status'] == 'fail' else 'PASS'}")
        rendered = "\n".join(lines)

    core.emit(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2) if args.format == "json" else rendered + "\n",
            encoding="utf-8",
        )
        LOG.info("Report written to %s", output_path)

    if report["status"] == "fail":
        LOG.error(
            "Secret scan failed: %d finding(s), %d forbidden file(s).",
            len(report["findings"]),
            len(report["forbidden_files"]),
        )
        return 0 if args.no_fail else 1
    LOG.info("Secret scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
