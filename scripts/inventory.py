#!/usr/bin/env python3
"""Infrastructure inventory from a Terraform plan or state.

Produces a deterministic inventory (JSON + Markdown) of what the configuration
intends to create, grouped by module and resource type. Useful for change review,
cost review and asset registers.

This reads Terraform JSON only. It never calls AWS, so it cannot report resources
that exist in the account but are missing from Terraform (that is what
``drift_report.py`` is for, within its documented limits).

Usage
-----
    terraform show -json tfplan > plan.json
    python scripts/inventory.py --plan plan.json --markdown inventory.md

Exit codes
----------
    0  inventory produced
    1  input could not be read
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eawlz_core as core  # noqa: E402

LOG = logging.getLogger("inventory")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inventory",
        description="Build an inventory of planned (or current) Terraform resources.",
    )
    parser.add_argument("--plan", help="Plan JSON from `terraform show -json <planfile>`.")
    parser.add_argument("--state", help="State JSON from `terraform show -json` (current resources).")
    parser.add_argument("--markdown", default=None, help="Write a Markdown inventory to this path.")
    parser.add_argument("--json", dest="json_out", default=None, help="Write raw inventory JSON here.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def inventory_from_plan(summary: core.PlanSummary) -> dict[str, object]:
    resources = []
    for change in summary.changes:
        if not change.is_mutating or change.is_destroy:
            continue
        resources.append(
            {
                "address": change.address,
                "module": change.module,
                "type": change.type,
                "name": change.name,
                "action": change.action_label,
            }
        )
    return _summarise(resources, source="plan")


def inventory_from_state(state: dict) -> dict[str, object]:
    resources = []
    for item in core.iter_state_resources(state):
        if item["mode"] != "managed":
            continue
        address = item["address"]
        module = address.split(".", 1)[0] if address.startswith("module.") else "root"
        resources.append(
            {
                "address": address,
                "module": module,
                "type": item["type"],
                "name": item["name"],
                "action": "exists",
            }
        )
    return _summarise(resources, source="state")


def _summarise(resources: list[dict[str, str]], source: str) -> dict[str, object]:
    by_type = Counter(r["type"] for r in resources)
    by_module: dict[str, int] = defaultdict(int)
    for resource in resources:
        by_module[resource["module"]] += 1

    return {
        "source": source,
        "resource_count": len(resources),
        "by_type": dict(sorted(by_type.items())),
        "by_module": dict(sorted(by_module.items())),
        "resources": sorted(resources, key=lambda r: r["address"]),
    }


def render_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# Infrastructure inventory",
        "",
        f"Source: `{payload['source']}` · resources: **{payload['resource_count']}**",
        "",
        "## Resources by type",
        "",
        "| Resource type | Count |",
        "|---|---|",
    ]
    for resource_type, count in payload["by_type"].items():  # type: ignore[union-attr]
        lines.append(f"| `{resource_type}` | {count} |")

    lines.extend(["", "## Resources by module", "", "| Module | Count |", "|---|---|"])
    for module, count in payload["by_module"].items():  # type: ignore[union-attr]
        lines.append(f"| `{module}` | {count} |")

    lines.extend(["", "## Resource list", "", "| Address | Type | Action |", "|---|---|---|"])
    for resource in payload["resources"]:  # type: ignore[union-attr]
        lines.append(f"| `{resource['address']}` | `{resource['type']}` | {resource['action']} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )

    if not args.plan and not args.state:
        LOG.error("Provide --plan or --state (run `terraform show -json` first).")
        return 1

    try:
        if args.plan:
            payload = inventory_from_plan(core.load_plan_json(args.plan))
        else:
            payload = inventory_from_state(core.load_state_json(args.state))
    except (FileNotFoundError, core.PlanFormatError) as exc:
        LOG.error("%s", exc)
        return 1

    core.emit(
        core.format_table(
            ["TYPE", "COUNT"],
            [(f"`{k}`", v) for k, v in payload["by_type"].items()],  # type: ignore[union-attr]
        )
    )
    core.emit()
    core.emit(
        f"Total resources: {payload['resource_count']} "
        f"(source: {payload['source']})"
    )

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        LOG.info("JSON inventory written to %s", args.json_out)

    if args.markdown:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text(render_markdown(payload), encoding="utf-8")
        LOG.info("Markdown inventory written to %s", args.markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
