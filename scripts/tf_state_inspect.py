#!/usr/bin/env python3
"""Terraform state inspection (read-only).

Summarises what Terraform believes it owns: resource counts, providers, modules
and outputs, plus a warning list for sensitive outputs. It never prints raw
attribute values, so it is safe to paste into a review or CI log.

Usage
-----
    terraform show -json > state.json
    python scripts/tf_state_inspect.py --state state.json
    python scripts/tf_state_inspect.py --environment dev      # runs terraform show -json

Exit codes
----------
    0  state read successfully
    1  state missing/unreadable or terraform failed
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eawlz_core as core  # noqa: E402

LOG = logging.getLogger("state-inspect")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tf_state_inspect",
        description="Inspect Terraform state without exposing attribute values.",
        epilog="Read-only: runs `terraform show -json` at most, never `state rm`/`mv`/`push`.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--state", help="Path to state JSON produced by `terraform show -json`.")
    source.add_argument("--environment", help="Environment directory to inspect directly.")
    parser.add_argument("--repo", default=None, help="Repository root (default: auto-detect).")
    parser.add_argument("--json", dest="json_out", default=None, help="Write JSON summary here.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def summarise(state: dict) -> dict[str, object]:
    resources = list(core.iter_state_resources(state))
    managed = [r for r in resources if r["mode"] == "managed"]
    data_sources = [r for r in resources if r["mode"] == "data"]

    outputs = state.get("values", {}).get("outputs", {}) or {}
    sensitive_outputs = sorted(name for name, meta in outputs.items() if (meta or {}).get("sensitive"))

    return {
        "terraform_version": state.get("terraform_version", "unknown"),
        "serial": state.get("serial", "unknown"),
        "lineage_present": bool(state.get("lineage")),
        "managed_resources": len(managed),
        "data_sources": len(data_sources),
        "by_type": dict(Counter(r["type"] for r in managed).most_common()),
        "by_module": dict(Counter(
            r["address"].rsplit(".", 1)[0] if "." in r["address"] else "root" for r in managed
        ).most_common()),
        "providers": sorted({r["provider"] for r in managed if r["provider"]}),
        "outputs": sorted(outputs.keys()),
        "sensitive_outputs": sensitive_outputs,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )

    try:
        if args.state:
            state = core.load_state_json(args.state)
            source = args.state
        else:
            repo_root = Path(args.repo).resolve() if args.repo else core.find_repo_root(Path(__file__).resolve())
            env_dir = repo_root / "environments" / args.environment
            if not env_dir.is_dir():
                LOG.error("Environment directory not found: %s", env_dir)
                return 1
            if not (env_dir / ".terraform").is_dir():
                LOG.error(
                    "%s is not initialised - run `terraform init` there first.", env_dir
                )
                return 1
            LOG.info("Reading state from %s", env_dir)
            result = core.run_terraform(["show", "-json"], env_dir, timeout=120)
            if result.returncode != 0:
                LOG.error("terraform show failed: %s", core.strip_ansi(result.stderr)[-1500:])
                return 1
            state = json.loads(result.stdout)
            source = f"{env_dir} (live state)"
    except (FileNotFoundError, core.PlanFormatError, core.TerraformError) as exc:
        LOG.error("%s", exc)
        return 1

    summary = summarise(state)

    if args.format == "json":
        core.emit(json.dumps(summary, indent=2))
    else:
        core.emit("TERRAFORM STATE SUMMARY")
        core.emit("=======================")
        core.emit(f"Source              : {source}")
        core.emit(f"Terraform version   : {summary['terraform_version']}")
        core.emit(f"Serial              : {summary['serial']}")
        core.emit(f"Managed resources   : {summary['managed_resources']}")
        core.emit(f"Data sources        : {summary['data_sources']}")
        core.emit(f"Providers           : {', '.join(summary['providers']) or 'none'}")
        core.emit(f"Outputs             : {', '.join(summary['outputs']) or 'none'}")
        if summary["sensitive_outputs"]:
            core.emit(f"Sensitive outputs   : {', '.join(summary['sensitive_outputs'])}")
        core.emit()
        if summary["by_type"]:
            core.emit(
                core.format_table(
                    ["RESOURCE TYPE", "COUNT"], list(summary["by_type"].items())  # type: ignore[union-attr]
                )
            )
        else:
            core.emit("State contains no managed resources (empty or fresh environment).")
        core.emit()
        core.emit(
            "Reminder: state files can contain secrets in plaintext. Never commit them; "
            "the remote S3 backend encrypts them at rest."
        )

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        LOG.info("Summary written to %s", args.json_out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
