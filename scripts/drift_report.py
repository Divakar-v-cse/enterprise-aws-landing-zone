#!/usr/bin/env python3
"""Infrastructure drift reporting (plan-based).

What this does
--------------
1. Runs ``terraform init`` (optional) and ``terraform plan -detailed-exitcode``
   in an environment directory, or analyses a plan JSON you already produced.
2. Converts the plan into a readable report: creates, in-place updates,
   replacements and destroys, with attribute-level diffs for updates.
3. Classifies each change as ``new-resource``, ``drift-candidate`` or
   ``intentional-change-unverified`` based on whether the resource exists in
   ``prior_state``.

What this does NOT do
---------------------
* It does not apply anything. ``terraform apply`` is refused by the tooling.
* It does not *prove* drift. A Terraform plan is a **proposal** derived from
  three inputs: configuration, state, and (if refresh is enabled) live API data.
  The plan document cannot tell you whether a diff came from a provider-side
  change or from somebody editing the configuration. Every diff is therefore
  reported as a *drift candidate* that a human must confirm.

Usage
-----
    python scripts/drift_report.py --environment dev
    python scripts/drift_report.py --plan-json plan.json --markdown drift.md
    python scripts/drift_report.py --environment production --strict

Exit codes
----------
    0  no changes proposed
    1  error (invalid input, terraform failure)
    2  changes detected (same convention as `terraform plan -detailed-exitcode`)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eawlz_core as core  # noqa: E402

LOG = logging.getLogger("drift")

CLASS_NEW = "new-resource"
CLASS_DRIFT = "drift-candidate"
CLASS_INTENT = "intentional-change-unverified"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drift_report",
        description="Report planned changes and drift candidates for one environment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "A plan is a proposal, not proof of drift. Confirm each drift candidate\n"
            "against the change history before acting. This tool never applies."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--environment", help="Environment directory name (dev, staging, production).")
    source.add_argument("--plan-json", help="Existing `terraform show -json` plan to analyse.")
    parser.add_argument("--repo", default=None, help="Repository root (default: auto-detect).")
    parser.add_argument("--skip-init", action="store_true", help="Do not run `terraform init`.")
    parser.add_argument(
        "--timeout", type=int, default=600, help="Terraform timeout in seconds (default 600)."
    )
    parser.add_argument("--markdown", default=None, help="Write a Markdown report here.")
    parser.add_argument("--json", dest="json_out", default=None, help="Write the machine report here.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 2 on ANY mutating change (default: exit 2 only when the plan is non-empty).",
    )
    parser.add_argument("--format", choices=["text", "json"], default="text", help="stdout format.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def run_plan(environment_dir: Path, skip_init: bool, timeout: int) -> tuple[dict, int]:
    """Run init + plan, returning (plan_document, terraform_exit_code)."""
    if not environment_dir.is_dir():
        raise FileNotFoundError(f"Environment directory not found: {environment_dir}")

    if not skip_init and not (environment_dir / ".terraform").is_dir():
        LOG.info("Initialising %s", environment_dir)
        init = core.run_terraform(["init", "-input=false", "-no-color", "-upgrade=false"], environment_dir, timeout)
        if init.returncode != 0:
            raise core.TerraformError(
                "terraform init failed:\n" + core.strip_ansi(init.stderr)[-2000:]
            )

    plan_file = environment_dir / ".drift-plan.tfplan"
    LOG.info("Running terraform plan (read-only) in %s", environment_dir)
    plan = core.run_terraform(
        ["plan", "-input=false", "-no-color", "-detailed-exitcode", f"-out={plan_file.name}"],
        environment_dir,
        timeout,
    )
    if plan.returncode not in (0, 2):
        raise core.TerraformError("terraform plan failed:\n" + core.strip_ansi(plan.stderr)[-2000:])

    show = core.run_terraform(["show", "-json", plan_file.name], environment_dir, timeout)
    if show.returncode != 0:
        raise core.TerraformError("terraform show -json failed:\n" + core.strip_ansi(show.stderr)[-2000:])

    document = json.loads(show.stdout)
    try:
        plan_file.unlink()  # never leave plan artefacts (they can embed secrets)
    except OSError:
        LOG.warning("Could not remove temporary plan file %s", plan_file)
    return document, plan.returncode


def classify(document: dict, summary: core.PlanSummary) -> dict[str, object]:
    """Split planned changes into new resources vs drift candidates."""
    prior = core.count_prior_resources(document)
    existing = prior > 0

    entries = []
    for change in summary.changes:
        if not change.is_mutating:
            continue
        if change.is_create:
            category = CLASS_NEW
        elif existing:
            category = CLASS_DRIFT
        else:
            category = CLASS_INTENT

        diffs = (
            core.attribute_diff(change.before or {}, change.after or {})
            if change.is_update_in_place or change.action_label == "replace"
            else []
        )
        entries.append(
            {
                "address": change.address,
                "type": change.type,
                "action": change.action_label,
                "category": category,
                "module": change.module,
                "attribute_changes": diffs[:25],
                "attribute_change_count": len(diffs),
            }
        )

    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["category"]] = counts.get(entry["category"], 0) + 1

    return {
        "existing_resources_in_state": prior,
        "state_present": existing,
        "counts": counts,
        "entries": sorted(entries, key=lambda e: (e["category"], e["address"])),
        "assessment": (
            "Plan was compared against existing state: updates/destroys are DRIFT CANDIDATES "
            "and must be confirmed against change history."
            if existing
            else "No prior state: every change is initial provisioning, not drift."
        ),
    }


def render_markdown(report: dict) -> str:
    meta = report["meta"]
    analysis = report["analysis"]
    lines = [
        f"# Drift report — {meta['environment']}",
        "",
        f"Generated: `{meta['generated_at']}`  ",
        f"Terraform: `{meta['terraform_version']}` · source: `{meta['source']}`  ",
        f"State resource count: **{analysis['existing_resources_in_state']}**",
        "",
        "> A Terraform plan is a **proposal**, not a verified drift assessment. "
        "Updates and destroys against existing state are labelled *drift candidates* "
        "because the plan cannot distinguish provider-side drift from a configuration "
        "change. Confirm each one against `git log` and CloudTrail before acting.",
        "",
        "## Summary",
        "",
        "| Action | Count |",
        "|---|---|",
    ]
    for action, count in report["summary"].items():
        lines.append(f"| {action} | {count} |")
    if not report["summary"]:
        lines.append("| (no changes) | 0 |")

    lines.extend(["", f"**Assessment:** {analysis['assessment']}", ""])

    if analysis["entries"]:
        lines.extend(["## Planned changes", "", "| Resource | Action | Classification | Attrs changed |", "|---|---|---|---|"])
        for entry in analysis["entries"]:
            lines.append(
                f"| `{entry['address']}` | {entry['action']} | {entry['category']} | "
                f"{entry['attribute_change_count']} |"
            )

        detailed = [e for e in analysis["entries"] if e["attribute_changes"]]
        if detailed:
            lines.extend(["", "## Attribute-level differences", ""])
            for entry in detailed:
                lines.append(f"### `{entry['address']}` ({entry['action']})")
                lines.append("")
                lines.append("| Attribute | Before | After |")
                lines.append("|---|---|---|")
                for diff in entry["attribute_changes"]:
                    lines.append(
                        f"| `{diff['attribute']}` | {diff['before']} | {diff['after']} |"
                    )
                lines.append("")
    else:
        lines.extend(["## Planned changes", "", "No mutating changes were proposed.", ""])

    lines.extend(
        [
            "## How to act on this report",
            "",
            "1. For each `drift-candidate`, check whether the change is expected "
            "(`git log -p <module>`) or unmanaged (`aws cloudtrail lookup-events`).",
            "2. Unmanaged change in a security-relevant attribute (IAM policy, security "
            "group ingress, public access block) is an incident: follow "
            "`docs/DISASTER_RECOVERY.md` §Security event.",
            "3. Only then run the approved apply workflow. This tool never applies.",
            "",
            "---",
            "",
            "Estimates and classifications are based solely on the Terraform plan "
            "document produced in this run.",
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
        repo_root = Path(args.repo).resolve() if args.repo else core.find_repo_root(Path(__file__).resolve())
    except FileNotFoundError as exc:
        LOG.error("%s", exc)
        return 1

    environment = args.environment or "external-plan"
    try:
        if args.plan_json:
            summary = core.load_plan_json(args.plan_json)
            document = json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
            source = str(args.plan_json)
        else:
            environment_dir = repo_root / "environments" / environment
            document, plan_code = run_plan(environment_dir, args.skip_init, args.timeout)
            summary = core.load_plan_json_from_document(document)
            source = f"terraform plan ({environment})"
            LOG.info("terraform plan exit code: %d", plan_code)
    except (FileNotFoundError, core.PlanFormatError, core.TerraformError) as exc:
        LOG.error("%s", exc)
        return 1

    analysis = classify(document, summary)
    report = {
        "meta": {
            "environment": environment,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "terraform_version": summary.terraform_version,
            "format_version": summary.format_version,
            "source": source,
            "tool": "scripts/drift_report.py",
        },
        "summary": summary.by_action(),
        "analysis": analysis,
        "outputs": sorted(summary.outputs.keys()),
    }

    if args.format == "json":
        core.emit(json.dumps(report, indent=2, default=str))
    else:
        core.emit(f"DRIFT REPORT — {environment}")
        core.emit("=" * (15 + len(environment)))
        core.emit(f"Source              : {source}")
        core.emit(f"Terraform version   : {summary.terraform_version}")
        core.emit(f"State resources     : {analysis['existing_resources_in_state']}")
        core.emit(f"Planned action mix  : {report['summary'] or 'no changes'}")
        core.emit(f"Classification      : {analysis['counts'] or 'none'}")
        core.emit()
        if analysis["entries"]:
            core.emit(
                core.format_table(
                    ["RESOURCE", "ACTION", "CLASSIFICATION", "ATTRS"],
                    [
                        (e["address"], e["action"], e["category"], e["attribute_change_count"])
                        for e in analysis["entries"][:40]
                    ],
                )
            )
            if len(analysis["entries"]) > 40:
                core.emit(f"... {len(analysis['entries']) - 40} more (see --markdown/--json output)")
        else:
            core.emit("No mutating changes were proposed.")
        core.emit()
        core.emit(f"Assessment: {analysis['assessment']}")

    if args.markdown:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text(render_markdown(report), encoding="utf-8")
        LOG.info("Markdown report written to %s", args.markdown)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        LOG.info("JSON report written to %s", args.json_out)

    has_changes = bool(analysis["entries"]) or (args.strict and bool(summary.changes))
    return 2 if has_changes else 0


if __name__ == "__main__":
    raise SystemExit(main())
