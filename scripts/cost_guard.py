#!/usr/bin/env python3
"""Cost-aware resource check.

Flags billable resources in a Terraform plan and estimates rough monthly cost
from the static catalogue in ``scripts/lib/pricing_catalog.json``.

**These numbers are indicative planning estimates, not an AWS bill, not a quote,
and not live pricing.** They exist to catch the "someone enabled 3 NAT Gateways
and 6 m7i.large instances in dev" mistake before apply.

Usage
-----
    terraform plan -json -out=tfplan > /dev/null
    terraform show -json tfplan > plan.json
    python scripts/cost_guard.py --plan plan.json --max-monthly-usd 50

Exit codes
----------
    0  estimate within budget (or --no-fail)
    1  estimate above budget, or unreadable input
    2  billable resources present in zero-cost mode
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eawlz_core as core  # noqa: E402

LOG = logging.getLogger("cost-guard")

DISCLAIMER = (
    "INDICATIVE ESTIMATE ONLY - generated from a static price catalogue, not from "
    "AWS billing data. Confirm with the AWS Pricing Calculator before approving spend."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cost_guard",
        description="Estimate and gate the monthly cost of a Terraform plan.",
        epilog=DISCLAIMER,
    )
    parser.add_argument("--plan", required=True, help="Plan JSON path.")
    parser.add_argument(
        "--catalog",
        default=None,
        help="Pricing catalogue path (default: scripts/lib/pricing_catalog.json).",
    )
    parser.add_argument(
        "--max-monthly-usd",
        type=float,
        default=None,
        help="Fail when the estimate exceeds this monthly amount.",
    )
    parser.add_argument(
        "--zero-cost-mode",
        action="store_true",
        help="Fail (exit 2) if ANY billable resource is planned - used by the zero-cost profile.",
    )
    parser.add_argument("--json", dest="json_out", default=None, help="Write JSON estimate here.")
    parser.add_argument("--no-fail", action="store_true", help="Report only.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )

    catalog_path = Path(args.catalog) if args.catalog else Path(__file__).resolve().parent / "lib" / "pricing_catalog.json"
    try:
        summary = core.load_plan_json(args.plan)
        catalog = core.load_pricing_catalog(catalog_path)
    except (FileNotFoundError, core.PlanFormatError) as exc:
        LOG.error("%s", exc)
        return 1

    items = core.estimate_monthly_cost(summary, catalog)
    totals = core.cost_totals(items)

    LOG.info("Plan: %s (%d resource changes)", args.plan, len(summary.changes))
    if items:
        core.emit(
            core.format_table(
                ["RESOURCE", "DRIVER", "USD/MONTH", "ASSUMPTION"],
                [
                    (item.address, item.driver, f"{item.monthly_usd:,.2f}", item.assumption)
                    for item in items
                ],
            )
        )
    else:
        core.emit("No billable resources detected in this plan.")

    core.emit()
    core.emit(
        "Estimated monthly total: ${:,.2f} (drivers: {})".format(
            totals["total"],
            ", ".join(f"{k}=${v:,.2f}" for k, v in totals.items() if k != "total") or "none",
        )
    )
    core.emit(DISCLAIMER)

    if args.json_out:
        payload = {
            "plan": str(args.plan),
            "catalog_version": catalog.get("catalog_version", "unknown"),
            "region_reference": catalog.get("region_reference", "unknown"),
            "currency": catalog.get("currency", "USD"),
            "items": [item.__dict__ for item in items],
            "totals": totals,
            "disclaimer": DISCLAIMER,
        }
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        LOG.info("JSON estimate written to %s", args.json_out)

    if args.no_fail:
        return 0

    if args.zero_cost_mode and items:
        LOG.error(
            "Zero-cost mode is enabled but %d billable resource(s) are planned. "
            "Set zero_cost_mode = true in terraform.tfvars, or remove the billable flags.",
            len(items),
        )
        return 2

    if args.max_monthly_usd is not None and totals["total"] > args.max_monthly_usd:
        LOG.error(
            "Estimated $%.2f/month exceeds the budget of $%.2f/month.",
            totals["total"],
            args.max_monthly_usd,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
