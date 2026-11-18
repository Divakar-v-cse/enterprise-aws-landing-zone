#!/usr/bin/env python3
"""Backup and recovery readiness checklist.

Audits the *configuration* of a Terraform plan against the landing zone's backup
standard, then prints a checklist a reviewer can sign off.

Scope and honesty
-----------------
This verifies **configuration**, not reality. It cannot prove that:

* a backup job actually ran,
* a recovery point exists and is restorable,
* the restore finished inside the RTO.

Those require a live restore test (`docs/DISASTER_RECOVERY.md` §4). The checklist
says so explicitly instead of implying a passing audit means recoverable data.

Usage
-----
    terraform show -json tfplan > plan.json
    python scripts/backup_verify.py --plan plan.json --min-retention-days 30

Exit codes
----------
    0  every required control present
    1  missing control(s)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eawlz_core as core  # noqa: E402

LOG = logging.getLogger("backup-verify")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backup_verify",
        description="Verify backup/DR configuration in a Terraform plan.",
        epilog="Configuration audit only - a live restore test is still required.",
    )
    parser.add_argument("--plan", required=True, help="Plan JSON path.")
    parser.add_argument(
        "--min-retention-days", type=int, default=30, help="Minimum acceptable backup retention (default 30)."
    )
    parser.add_argument("--require-cloudtrail", action="store_true", help="Fail if no CloudTrail trail is planned.")
    parser.add_argument("--require-kms", action="store_true", help="Fail if no customer managed KMS key is planned.")
    parser.add_argument(
        "--allow-disabled",
        action="store_true",
        help="Treat a deliberately disabled backup plan (zero-cost profile) as a warning, not a failure.",
    )
    parser.add_argument("--json", dest="json_out", default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def _resources(summary: core.PlanSummary, resource_type: str) -> list[core.ResourceChange]:
    return [
        change
        for change in summary.changes
        if change.type == resource_type and change.is_mutating and not change.is_destroy
    ]


def _retention_days(plan_resource: dict[str, Any]) -> list[int]:
    retentions: list[int] = []
    for rule in plan_resource.get("rule", []) or []:
        lifecycle = (rule or {}).get("lifecycle") or []
        if isinstance(lifecycle, dict):
            lifecycle = [lifecycle]
        for entry in lifecycle:
            value = (entry or {}).get("delete_after")
            if isinstance(value, (int, float)):
                retentions.append(int(value))
    return retentions


def run_checks(summary: core.PlanSummary, args: argparse.Namespace) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []

    def add(name: str, ok: bool, detail: str, required: bool = True) -> None:
        status = "PASS" if ok else ("FAIL" if required else "WARN")
        results.append((name, status, detail))

    vaults = _resources(summary, "aws_backup_vault")
    add("Backup vault defined", bool(vaults), f"{len(vaults)} vault(s)" if vaults else "no aws_backup_vault")

    plans = _resources(summary, "aws_backup_plan")
    add(
        "Backup plan defined",
        bool(plans),
        f"{len(plans)} plan(s)" if plans else "no aws_backup_plan (disabled in this profile)",
        required=not args.allow_disabled,
    )

    if plans:
        retentions = [day for plan in plans for day in _retention_days(plan.after or {})]
        longest = max(retentions) if retentions else 0
        add(
            f"Retention >= {args.min_retention_days} days",
            longest >= args.min_retention_days,
            f"longest rule retains {longest} day(s)",
            required=not args.allow_disabled,
        )
        rule_count = sum(len((p.after or {}).get("rule", []) or []) for p in plans)
        add("Multiple retention tiers", rule_count >= 2, f"{rule_count} rule(s) defined", required=False)

    selections = _resources(summary, "aws_backup_selection")
    add(
        "Resource selection defined",
        bool(selections),
        f"{len(selections)} selection(s)" if selections else "no aws_backup_selection - plan protects nothing",
        required=not args.allow_disabled,
    )

    roles = [r for r in _resources(summary, "aws_iam_role") if "backup" in r.name]
    add(
        "Backup service role defined",
        bool(roles),
        f"{len(roles)} role(s)" if roles else "no backup IAM role",
        required=not args.allow_disabled,
    )

    versioning = _resources(summary, "aws_s3_bucket_versioning")
    enabled_versioning = [
        r
        for r in versioning
        if any(
            (cfg or {}).get("status") == "Enabled"
            for cfg in ((r.after or {}).get("versioning_configuration") or [])
        )
    ]
    add(
        "S3 versioning enabled",
        bool(enabled_versioning),
        f"{len(enabled_versioning)}/{len(versioning)} bucket(s) versioned",
    )

    encryption = _resources(summary, "aws_s3_bucket_server_side_encryption_configuration")
    add(
        "S3 default encryption configured",
        bool(encryption),
        f"{len(encryption)} bucket(s) encrypted",
    )

    pab = _resources(summary, "aws_s3_bucket_public_access_block")
    fully_blocked = [
        r
        for r in pab
        if all(
            (r.after or {}).get(key) is True
            for key in ("block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets")
        )
    ]
    add(
        "S3 public access fully blocked",
        len(fully_blocked) == len(pab) and bool(pab),
        f"{len(fully_blocked)}/{len(pab)} bucket(s) fully blocked",
    )

    trails = _resources(summary, "aws_cloudtrail")
    validated = [t for t in trails if (t.after or {}).get("enable_log_file_validation") is True]
    add(
        "CloudTrail with log file validation",
        bool(validated),
        f"{len(validated)} validated trail(s)" if validated else "no validated trail planned",
        required=args.require_cloudtrail,
    )

    keys = _resources(summary, "aws_kms_key")
    rotating = [k for k in keys if (k.after or {}).get("enable_key_rotation") is True]
    add(
        "KMS key rotation enabled",
        bool(rotating),
        f"{len(rotating)} rotating key(s)" if rotating else "no customer managed key planned",
        required=args.require_kms,
    )

    instances = _resources(summary, "aws_instance")
    if instances:
        encrypted = []
        for instance in instances:
            root = (instance.after or {}).get("root_block_device") or []
            if isinstance(root, dict):
                root = [root]
            if any((device or {}).get("encrypted") is True for device in root):
                encrypted.append(instance)
        add(
            "Instance root volumes encrypted",
            len(encrypted) == len(instances),
            f"{len(encrypted)}/{len(instances)} instance(s) encrypted",
        )
    else:
        add("Instance root volumes encrypted", True, "no instances planned (zero-cost mode)", required=False)

    return results


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )

    try:
        summary = core.load_plan_json(args.plan)
    except (FileNotFoundError, core.PlanFormatError) as exc:
        LOG.error("%s", exc)
        return 1

    results = run_checks(summary, args)
    failures = [r for r in results if r[1] == "FAIL"]

    core.emit("BACKUP / RECOVERY READINESS CHECKLIST")
    core.emit("=====================================")
    core.emit(f"Plan: {args.plan}")
    core.emit()
    core.emit(core.format_table(["CONTROL", "STATUS", "EVIDENCE"], results))
    core.emit()
    core.emit(f"Result: {len(results) - len(failures)}/{len(results)} controls satisfied")
    core.emit()
    core.emit("What this audit does NOT prove:")
    core.emit("  - that any backup job has actually run")
    core.emit("  - that a recovery point exists and restores successfully")
    core.emit("  - that the restore completes within the documented RTO")
    core.emit("Run the restore test in docs/DISASTER_RECOVERY.md section 4 for those.")

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(
                {
                    "plan": args.plan,
                    "controls": [{"control": r[0], "status": r[1], "evidence": r[2]} for r in results],
                    "status": "fail" if failures else "pass",
                    "limitations": [
                        "configuration only",
                        "no restore test performed",
                        "no recovery point verification",
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    if failures:
        LOG.error("%d control(s) not satisfied.", len(failures))
        return 1
    LOG.info("Backup configuration checklist passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
