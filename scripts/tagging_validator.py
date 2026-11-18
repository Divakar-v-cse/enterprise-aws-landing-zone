#!/usr/bin/env python3
"""Tagging policy validator.

Verifies that every taggable resource in a Terraform plan carries the mandatory
cost-allocation and ownership tags. Missing tags silently break chargeback
reports and backup selection, so this runs in CI before any plan is approved.

Usage
-----
    terraform plan -out=tfplan
    terraform show -json tfplan > plan.json
    python scripts/tagging_validator.py --plan plan.json

Exit codes
----------
    0  every taggable resource is compliant
    1  violations found, or the plan could not be read
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eawlz_core as core  # noqa: E402

LOG = logging.getLogger("tagging")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tagging_validator",
        description="Check Terraform-planned resources for mandatory tags.",
        epilog="Generate the plan JSON with: terraform show -json tfplan > plan.json",
    )
    parser.add_argument("--plan", required=True, help="Path to `terraform show -json` plan output.")
    parser.add_argument(
        "--required-tags",
        default=",".join(core.REQUIRED_TAGS),
        help=f"Comma-separated required tags (default: {','.join(core.REQUIRED_TAGS)}).",
    )
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--output", default=None, help="Optional report file path.")
    parser.add_argument("--no-fail", action="store_true", help="Report only, always exit 0.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )

    required = [tag.strip() for tag in args.required_tags.split(",") if tag.strip()]
    if not required:
        LOG.error("--required-tags produced an empty list; refusing to validate nothing.")
        return 1

    try:
        summary = core.load_plan_json(args.plan)
    except (FileNotFoundError, core.PlanFormatError) as exc:
        LOG.error("%s", exc)
        return 1

    if not summary.changes:
        LOG.warning("Plan contains no resource changes - nothing to validate.")

    violations = core.check_required_tags(summary, required=required)
    total = len([c for c in summary.mutating if c.type not in core.TAG_EXEMPT_TYPES])

    if args.format == "json":
        payload = {
            "plan": str(args.plan),
            "required_tags": required,
            "taggable_resources": total,
            "violations": [
                {"address": v.address, "type": v.resource_type, "missing": list(v.missing)}
                for v in violations
            ],
            "status": "fail" if violations else "pass",
        }
        rendered = json.dumps(payload, indent=2)
    else:
        lines = [
            "TAGGING POLICY REPORT",
            "=====================",
            f"Plan                 : {args.plan}",
            f"Required tags        : {', '.join(required)}",
            f"Taggable resources   : {total}",
            f"Violations           : {len(violations)}",
            "",
        ]
        if violations:
            rows = [(v.address, v.resource_type, ", ".join(v.missing)) for v in violations]
            lines.append(core.format_table(["RESOURCE", "TYPE", "MISSING TAGS"], rows))
            lines.append("")
            lines.append(
                "Fix: add the missing keys to the module's `tags` argument or to the "
                "environment's `local.common_tags`. Provider `default_tags` already "
                "supplies Project/Environment/ManagedBy/Owner/CostCenter, so a "
                "violation usually means a resource was created outside the modules."
            )
        else:
            lines.append("All taggable resources carry the mandatory tags.")
        lines.append("")
        lines.append(f"RESULT: {'FAIL' if violations else 'PASS'}")
        rendered = "\n".join(lines)

    core.emit(rendered)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            rendered if args.format == "text" else json.dumps(json.loads(rendered), indent=2),
            encoding="utf-8",
        )

    if violations and not args.no_fail:
        LOG.error("%d resource(s) missing required tags.", len(violations))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
