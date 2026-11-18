#!/usr/bin/env python3
"""Cost cleanup helper (destruction is gated, never automatic).

Default behaviour is READ-ONLY: it shows what a destroy would remove by running
`terraform plan -destroy`, and the estimated monthly saving.

Running the destroy requires two independent confirmations:

    python scripts/cleanup.py --environment dev --execute --confirm dev

Anything else refuses. This exists so a forgotten NAT Gateway or EC2 instance
does not silently bill for a month - not so destruction becomes casual.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eawlz_core as core  # noqa: E402

LOG = logging.getLogger("cleanup")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanup",
        description="Review (and optionally execute) teardown of one environment.",
        epilog="Without --execute nothing is destroyed. Even with it, --confirm must repeat the environment name.",
    )
    parser.add_argument("--environment", required=True, choices=["dev", "staging", "production"])
    parser.add_argument("--repo", default=None)
    parser.add_argument("--execute", action="store_true", help="Actually run terraform destroy (irreversible).")
    parser.add_argument("--confirm", default="", help="Repeat the environment name to confirm destruction.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)-7s %(message)s")

    try:
        repo = Path(args.repo).resolve() if args.repo else core.find_repo_root(Path(__file__).resolve())
    except FileNotFoundError as exc:
        LOG.error("%s", exc)
        return 1

    env_dir = repo / "environments" / args.environment
    if not env_dir.is_dir():
        LOG.error("Environment not found: %s", env_dir)
        return 1
    if not (env_dir / ".terraform").is_dir():
        LOG.error("Run `terraform init` in %s first.", env_dir)
        return 1

    LOG.info("Reviewing destruction plan for %s (read-only)", args.environment)
    review = core.run_terraform(["plan", "-destroy", "-input=false", "-no-color"], env_dir, timeout=600)
    if review.returncode not in (0, 2):
        LOG.error("terraform plan -destroy failed:\n%s", core.strip_ansi(review.stderr)[-1500:])
        return 1
    core.emit(core.strip_ansi(review.stdout)[-4000:])

    if not args.execute:
        core.emit()
        core.emit("READ-ONLY REVIEW. Nothing was destroyed.")
        core.emit("To execute: python scripts/cleanup.py --environment "
                  f"{args.environment} --execute --confirm {args.environment}")
        return 0

    if args.confirm != args.environment:
        LOG.error("Confirmation mismatch. Re-run with --confirm %s", args.environment)
        return 1

    if args.environment == "production":
        LOG.error(
            "Refusing to destroy production from a workstation. Production teardown "
            "requires a change record and the approved workflow."
        )
        return 1

    LOG.warning("DESTROYING %s - this cannot be undone", args.environment)
    destroy = core.run_terraform(["destroy", "-auto-approve", "-input=false", "-no-color"], env_dir, timeout=1800)
    core.emit(core.strip_ansi(destroy.stdout)[-4000:])
    if destroy.returncode != 0:
        LOG.error("terraform destroy failed:\n%s", core.strip_ansi(destroy.stderr)[-1500:])
        return 1
    LOG.info("Destroy completed for %s", args.environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
