"""Tests for plan parsing, tagging validation and cost estimation with fixtures."""

import json
from pathlib import Path

import pytest

from lib import eawlz_core as core

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def plan():
    return core.load_plan_json(FIXTURES / "plan-with-drift.json")


def test_plan_summary_counts_actions(plan):
    assert plan.terraform_version == "1.15.8"
    assert plan.by_action()["create"] == 2
    assert plan.by_action()["update"] == 1
    assert plan.by_action()["delete"] == 1
    assert len(plan.mutating) == 4


def test_destroy_and_replace_detection(plan):
    assert [c.type for c in plan.destroys] == ["aws_s3_bucket"]
    assert plan.changes[0].action_label == "update"


def test_prior_state_detection():
    document = json.loads((FIXTURES / "plan-with-drift.json").read_text(encoding="utf-8"))
    assert core.count_prior_resources(document) == 2
    empty = json.loads((FIXTURES / "plan-initial.json").read_text(encoding="utf-8"))
    assert core.count_prior_resources(empty) == 0


def test_tagging_violations_detected():
    summary = core.load_plan_json(FIXTURES / "plan-with-drift.json")
    violations = core.check_required_tags(summary)
    addresses = {v.address for v in violations}
    assert "module.networking.aws_vpc.main" in addresses
    missing = next(v.missing for v in violations if v.address == "module.networking.aws_vpc.main")
    assert "CostCenter" in missing and "Owner" in missing


def test_tagging_ignores_destroyed_resources():
    summary = core.load_plan_json(FIXTURES / "plan-with-drift.json")
    violations = core.check_required_tags(summary)
    assert all("old-bucket" not in v.address for v in violations)


def test_cost_estimate_includes_nat_and_compute():
    summary = core.load_plan_json(FIXTURES / "plan-initial.json")
    catalog = core.load_pricing_catalog(Path(__file__).resolve().parents[1] / "scripts" / "lib" / "pricing_catalog.json")
    items = core.estimate_monthly_cost(summary, catalog)
    drivers = {item.resource_type for item in items}
    assert "aws_nat_gateway" in drivers
    assert "aws_instance" in drivers
    totals = core.cost_totals(items)
    assert totals["total"] > 0
    assert round(totals["total"], 2) == totals["total"]


def test_cost_estimate_unknown_instance_type_is_flagged():
    summary = core.load_plan_json(FIXTURES / "plan-initial.json")
    catalog = core.load_pricing_catalog(Path(__file__).resolve().parents[1] / "scripts" / "lib" / "pricing_catalog.json")
    items = core.estimate_monthly_cost(summary, catalog)
    unknown = [i for i in items if "not in catalogue" in i.assumption]
    assert unknown, "an instance type missing from the catalogue must be reported, not silently priced at 0"
