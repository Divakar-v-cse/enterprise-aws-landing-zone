"""Core domain logic for the landing zone tooling.

Everything in this module is pure Python: no AWS SDK, no Terraform execution,
no network. The CLI scripts under ``scripts/`` are thin wrappers that add
argument parsing, logging and exit codes, which means the interesting behaviour
can be unit tested with fixtures.

Design rules
------------
1. Never mutate infrastructure. This library only *reads* and *reports*.
2. Never claim more than the evidence supports. A Terraform plan is a proposal,
   not a verified drift assessment; the wording of every report reflects that.
3. Fail loudly with actionable messages instead of silently degrading.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Tags the tagging policy requires on every taggable resource.
REQUIRED_TAGS: tuple[str, ...] = (
    "Project",
    "Environment",
    "ManagedBy",
    "Owner",
    "CostCenter",
)

#: Resource types that legitimately cannot carry user tags.
TAG_EXEMPT_TYPES: frozenset[str] = frozenset(
    {
        "aws_s3_bucket_policy",
        "aws_s3_bucket_versioning",
        "aws_s3_bucket_public_access_block",
        "aws_s3_bucket_ownership_controls",
        "aws_s3_bucket_server_side_encryption_configuration",
        "aws_s3_bucket_lifecycle_configuration",
        "aws_s3_bucket_logging",
        "aws_route",
        "aws_route_table_association",
        "aws_iam_role_policy",
        "aws_iam_role_policy_attachment",
        "aws_iam_policy_attachment",
        "aws_network_acl_rule",
        "aws_vpc_endpoint_route_table_association",
    }
)

#: Actions that are safe/expected in a Terraform plan.
VALID_PLAN_ACTIONS: frozenset[str] = frozenset(
    {"create", "read", "update", "delete", "no-op", "forget"}
)

#: Patterns that indicate a credential. Kept as compiled regexes so the scanner
#: can be reused for files, diffs and strings.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("AWS access key ID", re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA)[0-9A-Z]{16}\b")),
    ("AWS secret access key", re.compile(r"(?i)aws_?secret_?access_?key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("GitLab token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Stripe secret key", re.compile(r"\bsk_live_[0-9A-Za-z]{20,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("Generic assigned secret", re.compile(r"(?i)\b(?:password|passwd|secret|api_key|apikey|token)\s*[=:]\s*['\"][^'\"\s]{8,}['\"]")),
)

#: Files that are allowed to contain secret-like strings (documentation, tests,
#: and the scanner itself). Matched against POSIX-style relative paths.
SECRET_SCAN_ALLOWLIST: tuple[str, ...] = (
    "docs/TROUBLESHOOTING.md",
    "security/SECURITY_REPORT.md",
    "scripts/secret_scan.py",
    "scripts/lib/eawlz_core.py",
    "tests/test_secret_scan.py",
    ".gitignore",
    ".gitleaks.toml",
)

#: File extensions that must never enter the repository.
FORBIDDEN_TRACKED_SUFFIXES: tuple[str, ...] = (
    ".tfstate",
    ".tfstate.backup",
    ".tfplan",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
)


class PlanFormatError(ValueError):
    """Raised when a ``terraform show -json`` document is not usable."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def strip_ansi(text: str) -> str:
    """Remove ANSI colour codes so logs stay readable in files and CI."""
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)


def human_bytes(count: int) -> str:
    """Format a byte count using binary units."""
    value = float(count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


def format_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Render a plain-text table that is readable in a terminal and in a log."""
    string_rows = [[str(cell) for cell in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in string_rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def line(cells: Sequence[str]) -> str:
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)).rstrip()

    separator = "-+-".join("-" * w for w in widths)
    output = [line(headers), separator]
    output.extend(line(row) for row in string_rows)
    return "\n".join(output)


# ---------------------------------------------------------------------------
# Terraform JSON model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResourceChange:
    """One entry from ``plan.resource_changes``."""

    address: str
    mode: str
    type: str
    name: str
    provider_name: str
    module: str
    actions: tuple[str, ...]
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    after_unknown: dict[str, Any] | None = None

    @property
    def action_label(self) -> str:
        """Human readable action, e.g. ``create`` or ``replace``."""
        if self.actions == ("create", "delete") or self.actions == ("delete", "create"):
            return "replace"
        if not self.actions:
            return "no-op"
        return ",".join(self.actions)

    @property
    def is_create(self) -> bool:
        return self.actions == ("create",)

    @property
    def is_destroy(self) -> bool:
        return "delete" in self.actions

    @property
    def is_update_in_place(self) -> bool:
        return self.actions == ("update",)

    @property
    def is_mutating(self) -> bool:
        """True when applying the plan would change real infrastructure."""
        return any(a in {"create", "update", "delete"} for a in self.actions)


@dataclass
class PlanSummary:
    """Aggregated view of a Terraform plan document."""

    terraform_version: str
    format_version: str
    changes: list[ResourceChange] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)

    def by_action(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for change in self.changes:
            counts[change.action_label] = counts.get(change.action_label, 0) + 1
        return dict(sorted(counts.items()))

    def by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for change in self.changes:
            counts[change.type] = counts.get(change.type, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

    @property
    def mutating(self) -> list[ResourceChange]:
        return [c for c in self.changes if c.is_mutating]

    @property
    def destroys(self) -> list[ResourceChange]:
        return [c for c in self.changes if c.is_destroy]

    @property
    def replacements(self) -> list[ResourceChange]:
        return [c for c in self.changes if c.action_label == "replace"]


def load_plan_json(path: str | Path) -> PlanSummary:
    """Load a ``terraform show -json <plan>`` document.

    Raises:
        FileNotFoundError: the plan JSON does not exist.
        PlanFormatError: the document is not a Terraform plan JSON.
    """
    plan_path = Path(path)
    if not plan_path.is_file():
        raise FileNotFoundError(f"Plan JSON not found: {plan_path}")

    try:
        document = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanFormatError(
            f"{plan_path} is not valid JSON ({exc.msg} at line {exc.lineno}). "
            "Generate it with: terraform show -json tfplan > plan.json"
        ) from exc

    return load_plan_json_from_document(document, source=str(plan_path))


def load_plan_json_from_document(document: Any, source: str = "<memory>") -> PlanSummary:
    """Build a :class:`PlanSummary` from an already-parsed plan document."""
    if not isinstance(document, dict):
        raise PlanFormatError(f"{source} must contain a JSON object.")

    if "resource_changes" not in document and "planned_values" not in document:
        raise PlanFormatError(
            f"{source} does not look like a Terraform plan (no resource_changes/"
            "planned_values). Did you pass a state file instead of a plan?"
        )

    summary = PlanSummary(
        terraform_version=str(document.get("terraform_version", "unknown")),
        format_version=str(document.get("format_version", "unknown")),
    )

    for raw in document.get("resource_changes", []) or []:
        change = raw.get("change", {}) or {}
        summary.changes.append(
            ResourceChange(
                address=raw.get("address", ""),
                mode=raw.get("mode", "managed"),
                type=raw.get("type", ""),
                name=raw.get("name", ""),
                provider_name=raw.get("provider_name", ""),
                module=raw.get("module_address", "") or "root",
                actions=tuple(change.get("actions", []) or []),
                before=change.get("before"),
                after=change.get("after"),
                after_unknown=change.get("after_unknown"),
            )
        )

    summary.outputs = (document.get("planned_values", {}) or {}).get("outputs", {}) or {}
    return summary


def load_state_json(path: str | Path) -> dict[str, Any]:
    """Load ``terraform show -json`` state output (read-only inspection)."""
    state_path = Path(path)
    if not state_path.is_file():
        raise FileNotFoundError(f"State JSON not found: {state_path}")
    try:
        document = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanFormatError(f"{state_path} is not valid JSON: {exc.msg}") from exc
    if not isinstance(document, dict):
        raise PlanFormatError(f"{state_path} must contain a JSON object.")
    return document


def iter_state_resources(state: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield every managed resource in a state document, including child modules."""

    def walk(module: dict[str, Any], prefix: str) -> Iterator[dict[str, Any]]:
        for resource in module.get("resources", []) or []:
            address = f"{prefix}{resource.get('address', '')}" if prefix else resource.get("address", "")
            yield {
                "address": address,
                "mode": resource.get("mode", "managed"),
                "type": resource.get("type", ""),
                "name": resource.get("name", ""),
                "provider": resource.get("provider_name", ""),
                "values": resource.get("values", {}) or {},
            }
        for child in module.get("child_modules", []) or []:
            yield from walk(child, prefix)

    root = state.get("values", {}).get("root_module", {}) or {}
    yield from walk(root, "")


# ---------------------------------------------------------------------------
# Tagging policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TagViolation:
    address: str
    resource_type: str
    missing: tuple[str, ...]


def extract_tags(change: ResourceChange) -> dict[str, str]:
    """Return the effective tags for a planned resource.

    Terraform exposes both ``tags`` and ``tags_all``; ``tags_all`` includes
    provider ``default_tags`` and is therefore the authoritative view.
    """
    for key in ("tags_all", "tags"):
        candidate = (change.after or {}).get(key)
        if isinstance(candidate, dict) and candidate:
            return {str(k): str(v) for k, v in candidate.items()}
    return {}


def check_required_tags(
    summary: PlanSummary,
    required: Sequence[str] = REQUIRED_TAGS,
    exempt_types: frozenset[str] = TAG_EXEMPT_TYPES,
) -> list[TagViolation]:
    """Find planned resources that are missing required tags.

    Only resources that would exist after the plan are considered; deletions and
    read-only data sources are ignored.
    """
    violations: list[TagViolation] = []
    for change in summary.changes:
        if change.mode != "managed" or not change.is_mutating:
            continue
        if change.is_destroy:
            continue
        if change.type in exempt_types:
            continue

        tags = extract_tags(change)
        if not tags:
            # A resource type that simply does not support tags is not a
            # violation, but a tagged type with no tags at all is.
            continue

        missing = tuple(sorted(tag for tag in required if tag not in tags))
        if missing:
            violations.append(
                TagViolation(address=change.address, resource_type=change.type, missing=missing)
            )
    return violations


# ---------------------------------------------------------------------------
# Attribute diffing (drift reporting)
# ---------------------------------------------------------------------------

#: Attribute names that must never appear verbatim in a committed report.
SENSITIVE_ATTRIBUTE_HINTS: tuple[str, ...] = (
    "password",
    "secret",
    "token",
    "private_key",
    "access_key",
    "credential",
    "connection_string",
)


def is_sensitive_attribute(name: str) -> bool:
    """True when an attribute name looks like it carries a credential."""
    lowered = name.lower()
    return any(hint in lowered for hint in SENSITIVE_ATTRIBUTE_HINTS)


def _short(value: Any, limit: int = 120) -> str:
    text = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def attribute_diff(before: Any, after: Any, attribute: str = "", depth: int = 0) -> list[dict[str, str]]:
    """Return attribute-level differences between two Terraform objects.

    Nested maps are compared one level deep (two for security groups, which is
    where most accidental drift lives). Values that look like credentials are
    redacted so reports can be committed safely.
    """
    changes: list[dict[str, str]] = []
    if depth > 2:
        return changes

    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            if key in {"tags_all"}:
                continue
            nested = f"{attribute}.{key}" if attribute else key
            if key not in before:
                changes.append({"attribute": nested, "before": "(absent)", "after": _short(after[key])})
            elif key not in after:
                changes.append({"attribute": nested, "before": _short(before[key]), "after": "(absent)"})
            elif isinstance(before[key], (dict, list)) and isinstance(after[key], (dict, list)):
                changes.extend(attribute_diff(before[key], after[key], nested, depth + 1))
            elif before[key] != after[key]:
                if is_sensitive_attribute(key):
                    changes.append({"attribute": nested, "before": "(redacted)", "after": "(redacted)"})
                else:
                    changes.append(
                        {"attribute": nested, "before": _short(before[key]), "after": _short(after[key])}
                    )
        return changes

    if before != after:
        if is_sensitive_attribute(attribute):
            return [{"attribute": attribute or "value", "before": "(redacted)", "after": "(redacted)"}]
        changes.append(
            {"attribute": attribute or "value", "before": _short(before), "after": _short(after)}
        )
    return changes


def count_prior_resources(document: dict[str, Any]) -> int:
    """Count resources recorded in ``prior_state`` (i.e. existing infrastructure)."""
    prior = (document.get("prior_state", {}) or {}).get("values", {}).get("root_module")
    if not prior:
        return 0
    return sum(1 for _ in iter_state_resources(document.get("prior_state", {})))


# ---------------------------------------------------------------------------
# Cost awareness (indicative only)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostLineItem:
    address: str
    resource_type: str
    driver: str
    monthly_usd: float
    assumption: str


def load_pricing_catalog(path: str | Path) -> dict[str, Any]:
    """Load the indicative price catalogue shipped with the toolkit."""
    catalog_path = Path(path)
    if not catalog_path.is_file():
        raise FileNotFoundError(f"Pricing catalogue not found: {catalog_path}")
    return json.loads(catalog_path.read_text(encoding="utf-8"))


def estimate_monthly_cost(
    summary: PlanSummary, catalog: dict[str, Any]
) -> list[CostLineItem]:
    """Estimate monthly cost of *planned* resources from a static catalogue.

    IMPORTANT: these are planning estimates from a checked-in price table, not a
    bill, not a quote, and not region-accurate. They exist to catch the "I just
    planned a NAT Gateway and three m7i.large instances" mistake before apply.
    """
    items: list[CostLineItem] = []
    hours = float(catalog.get("hours_per_month", 730))
    prices = catalog.get("prices", {})

    ec2_hourly = prices.get("ec2_hourly_usd", {})
    volume_gb = prices.get("ebs_gp3_per_gb_month_usd", 0.08)
    nat_hourly = prices.get("nat_gateway_hourly_usd", 0.045)
    nat_processing = prices.get("nat_gateway_per_gb_usd", 0.045)
    eip_hourly = prices.get("eip_hourly_usd", 0.005)
    kms_monthly = prices.get("kms_key_month_usd", 1.0)
    alarm_monthly = prices.get("cloudwatch_alarm_month_usd", 0.10)
    backup_gb = prices.get("backup_warm_per_gb_month_usd", 0.05)

    for change in summary.changes:
        if not change.is_create:
            continue
        after = change.after or {}

        if change.type == "aws_instance":
            instance_type = str(after.get("instance_type", "unknown"))
            hourly = float(ec2_hourly.get(instance_type, 0.0))
            monthly = hourly * hours
            note = (
                f"{instance_type} at ${hourly:.4f}/h x {hours:.0f}h"
                if hourly
                else f"{instance_type} not in catalogue - verify with AWS Pricing Calculator"
            )
            items.append(CostLineItem(change.address, change.type, "compute", monthly, note))

            root = after.get("root_block_device")
            volumes = root if isinstance(root, list) else [root] if isinstance(root, dict) else []
            for volume in volumes:
                size = float(volume.get("volume_size", 0) or 0)
                if size:
                    items.append(
                        CostLineItem(
                            change.address,
                            "aws_ebs_volume",
                            "storage",
                            size * float(volume_gb),
                            f"gp3 {size:.0f} GiB at ${volume_gb}/GB-month",
                        )
                    )

        elif change.type == "aws_nat_gateway":
            items.append(
                CostLineItem(
                    change.address,
                    change.type,
                    "network",
                    nat_hourly * hours,
                    f"${nat_hourly}/h x {hours:.0f}h, excludes data processing "
                    f"(${nat_processing}/GB)",
                )
            )

        elif change.type == "aws_eip":
            items.append(
                CostLineItem(
                    change.address,
                    change.type,
                    "network",
                    eip_hourly * hours,
                    f"${eip_hourly}/h while associated to a running NAT Gateway",
                )
            )

        elif change.type == "aws_kms_key":
            items.append(
                CostLineItem(
                    change.address, change.type, "security", kms_monthly, "1 CMK, rotation included"
                )
            )

        elif change.type == "aws_cloudwatch_metric_alarm":
            items.append(
                CostLineItem(
                    change.address, change.type, "observability", alarm_monthly, "1 standard alarm"
                )
            )

        elif change.type == "aws_backup_plan":
            items.append(
                CostLineItem(
                    change.address,
                    change.type,
                    "resilience",
                    0.0,
                    f"plan itself is free; budget assumes ${backup_gb}/GB-month for stored "
                    "recovery points (size dependent)",
                )
            )

        elif change.type == "aws_cloudtrail":
            items.append(
                CostLineItem(
                    change.address,
                    change.type,
                    "audit",
                    0.0,
                    "first copy of management events is free; S3 storage billed separately",
                )
            )

    return items


def cost_totals(items: Iterable[CostLineItem]) -> dict[str, float]:
    """Sum estimated cost per driver plus a grand total."""
    totals: dict[str, float] = {}
    for item in items:
        totals[item.driver] = totals.get(item.driver, 0.0) + item.monthly_usd
    totals["total"] = sum(item.monthly_usd for item in items)
    return {key: round(value, 2) for key, value in totals.items()}


# ---------------------------------------------------------------------------
# Secret scanning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SecretFinding:
    path: str
    line: int
    rule: str
    excerpt: str


def redact(secret: str, keep: int = 4) -> str:
    """Keep a short prefix so a finding is actionable without leaking the value."""
    if len(secret) <= keep:
        return "*" * len(secret)
    return secret[:keep] + "*" * min(len(secret) - keep, 12)


def scan_text_for_secrets(text: str, path: str = "<memory>") -> list[SecretFinding]:
    """Scan a text blob line by line for credential patterns.

    The excerpt is redacted: reports are committed to git, so they must never
    contain the secret they are reporting.
    """
    findings: list[SecretFinding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if len(line) > 4000:  # defensive: minified/binary-ish line
            continue
        for rule, pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if match:
                findings.append(
                    SecretFinding(
                        path=path,
                        line=line_number,
                        rule=rule,
                        excerpt=redact(match.group(0)),
                    )
                )
                break
    return findings


def is_allowlisted(relative_path: str, allowlist: Sequence[str] = SECRET_SCAN_ALLOWLIST) -> bool:
    """True when a path is allowlisted for secret scanning."""
    normalised = relative_path.replace("\\", "/")
    return any(normalised == entry or normalised.endswith("/" + entry) for entry in allowlist)


def should_scan_file(path: Path, root: Path) -> bool:
    """Decide whether a file is in scope for a repository secret scan."""
    relative = path.relative_to(root).as_posix()
    if any(part in {".git", ".terraform", "node_modules", "__pycache__", ".pytest_cache", ".tools"} for part in path.parts):
        return False
    if relative.startswith("artifacts/"):
        return False
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".exe", ".tfplan", ".ico", ".woff", ".woff2"}:
        return False
    try:
        return path.stat().st_size <= 2_000_000
    except OSError:
        return False


# ---------------------------------------------------------------------------
# HCL / tfvars parsing (just enough for preflight checks)
# ---------------------------------------------------------------------------

_SCALAR_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")


def parse_simple_tfvars(text: str) -> dict[str, Any]:
    """Parse a flat ``key = value`` tfvars file.

    Supports strings, booleans, numbers and single-line lists of scalars. This is
    deliberately *not* an HCL parser: preflight checks only need to read the
    guard-rail flags, and adding a real HCL dependency would break the
    zero-dependency promise of the toolkit.
    """
    values: dict[str, Any] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        match = _SCALAR_RE.match(line)
        if not match:
            continue
        key, raw = match.group(1), match.group(2)

        # A quoted value may be followed by an inline comment: "dev"  # note
        if raw.startswith('"'):
            closing = raw.find('"', 1)
            if closing != -1:
                values[key] = raw[1:closing]
                continue

        if "#" in raw:
            raw = raw.split("#", 1)[0].strip()
        if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
            values[key] = raw[1:-1]
        elif raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            items = [item.strip().strip('"') for item in inner.split(",") if item.strip()] if inner else []
            values[key] = items
        elif raw.lower() in {"true", "false"}:
            values[key] = raw.lower() == "true"
        else:
            try:
                values[key] = int(raw)
            except ValueError:
                try:
                    values[key] = float(raw)
                except ValueError:
                    values[key] = raw
    return values


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")


def markdown_relative_links(text: str) -> list[str]:
    """Return relative link targets (ignoring http(s), mailto and anchors)."""
    targets: list[str] = []
    for match in list(_LINK_RE.finditer(text)) + list(_IMAGE_RE.finditer(text)):
        target = match.group(1).split("#", 1)[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "tel:")):
            continue
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        targets.append(target)
    return targets


# ---------------------------------------------------------------------------
# Terraform execution helper (read-only verbs only)
# ---------------------------------------------------------------------------

ALLOWED_TERRAFORM_VERBS: frozenset[str] = frozenset(
    {"init", "validate", "fmt", "plan", "show", "output", "version", "state", "providers"}
)

#: Verbs that mutate infrastructure. The toolkit refuses to run these.
FORBIDDEN_TERRAFORM_VERBS: frozenset[str] = frozenset({"apply", "destroy", "import", "taint"})


class TerraformError(RuntimeError):
    """Raised when a Terraform command fails or is refused."""


def run_terraform(
    args: Sequence[str],
    cwd: str | Path,
    timeout: int = 300,
    allow_plan: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a Terraform command with hard guard rails.

    ``apply``/``destroy``/``import``/``taint`` are refused outright: automation
    in this repository may observe and plan, never mutate. Humans apply through
    the approval workflow.
    """
    if not args:
        raise ValueError("run_terraform requires at least one argument")
    verb = args[0]
    if verb in FORBIDDEN_TERRAFORM_VERBS:
        raise TerraformError(
            f"Refusing to run `terraform {verb}`: automated tooling in this repository is "
            "read-only. Use the approved workflow in .github/workflows/terraform-apply.yml."
        )
    if verb not in ALLOWED_TERRAFORM_VERBS:
        raise TerraformError(f"Unsupported terraform verb '{verb}' for automated tooling.")
    if verb == "plan" and not allow_plan:
        raise TerraformError("terraform plan disabled by caller")

    try:
        completed = subprocess.run(  # noqa: S603 - fixed executable, validated verb
            ["terraform", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise TerraformError(
            "terraform executable not found on PATH. Install Terraform >= 1.5 "
            "and re-open the shell."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise TerraformError(
            f"terraform {verb} exceeded {timeout}s. Large plans may need a longer timeout."
        ) from exc
    return completed


def terraform_available() -> tuple[bool, str]:
    """Return (available, version-or-error) for the local Terraform binary."""
    try:
        completed = subprocess.run(
            ["terraform", "version", "-json"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "terraform not found"
    if completed.returncode != 0:
        return False, completed.stderr.strip() or "terraform version failed"
    try:
        payload = json.loads(completed.stdout)
        return True, payload.get("terraform_version", "unknown")
    except json.JSONDecodeError:
        return True, completed.stdout.splitlines()[0].strip() if completed.stdout else "unknown"


# ---------------------------------------------------------------------------
# Repository helpers
# ---------------------------------------------------------------------------


def find_repo_root(start: str | Path | None = None) -> Path:
    """Walk upwards until a directory containing ``modules/`` and ``environments/``."""
    current = Path(start or Path(__file__).resolve()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "modules").is_dir() and (candidate / "environments").is_dir():
            return candidate
    raise FileNotFoundError(
        "Repository root not found (looked for a directory containing both "
        "'modules/' and 'environments/'). Run this script from inside the repo."
    )


def discover_environments(root: str | Path) -> list[str]:
    """Return environment directory names sorted dev -> staging -> production."""
    environments_dir = Path(root) / "environments"
    if not environments_dir.is_dir():
        return []
    order = {"dev": 0, "staging": 1, "production": 2}
    names = [p.name for p in environments_dir.iterdir() if p.is_dir()]
    return sorted(names, key=lambda n: (order.get(n, 99), n))


def relpath(path: Path, root: Path) -> str:
    """POSIX-style path relative to the repository root."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def emit(message: str = "", *, stream: Any = None) -> None:
    """Write a line to stdout, flushing so CI logs stream in order."""
    print(message, file=stream or sys.stdout, flush=True)
