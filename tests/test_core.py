"""Unit tests for scripts/lib/eawlz_core.py (pure logic, no AWS, no Terraform)."""

import json

import pytest

from lib import eawlz_core as core


def test_parse_simple_tfvars_reads_scalars_lists_and_comments():
    text = '''
    project_name = "eawlz"   # inline comment
    zero_cost_mode = true
    instance_count = 0
    retention = 14
    cidrs = ["10.0.0.0/20", "10.0.16.0/20"]
    # full line comment
    '''
    values = core.parse_simple_tfvars(text)
    assert values["project_name"] == "eawlz"
    assert values["zero_cost_mode"] is True
    assert values["instance_count"] == 0
    assert values["retention"] == 14
    assert values["cidrs"] == ["10.0.0.0/20", "10.0.16.0/20"]
    assert "zero_cost_mode" in values


def test_format_table_aligns_columns():
    rendered = core.format_table(["A", "BB"], [("1", "2")])
    lines = rendered.splitlines()
    assert lines[0].startswith("A")
    assert set(lines[1]) <= {"-", "+", " "}
    assert "1" in lines[2]


def test_redact_keeps_prefix_and_hides_value():
    # Assembled at runtime so this file never contains a literal credential.
    fake_key = "AKIA" + "Z" * 16
    redacted = core.redact(fake_key)
    assert redacted.startswith("AKIA")
    assert "ZZZZZZZZ" not in redacted


def test_attribute_diff_finds_scalar_and_nested_changes():
    before = {"tags": {"Environment": "dev"}, "cidr": "10.0.0.0/16"}
    after = {"tags": {"Environment": "prod"}, "cidr": "10.0.0.0/16"}
    changes = core.attribute_diff(before, after)
    assert any(c["attribute"] == "tags.Environment" for c in changes)
    assert all(c["attribute"] != "cidr" for c in changes)


def test_attribute_diff_redacts_sensitive_values():
    changes = core.attribute_diff({"password": "a"}, {"password": "b"})
    assert changes and changes[0]["before"] == "(redacted)"
    assert changes[0]["after"] == "(redacted)"


def test_attribute_diff_reports_absent_keys():
    changes = core.attribute_diff({"a": 1}, {"a": 1, "b": 2})
    assert changes == [{"attribute": "b", "before": "(absent)", "after": "2"}]


def test_markdown_links_ignore_external_targets():
    text = "[a](docs/A.md) [b](https://x.y/z) ![i](screenshots/p.png)"
    assert core.markdown_relative_links(text) == ["docs/A.md", "screenshots/p.png"]


def test_is_allowlisted_matches_known_documents():
    assert core.is_allowlisted("docs/TROUBLESHOOTING.md")
    assert not core.is_allowlisted("environments/dev/main.tf")


def test_terraform_guard_refuses_apply(tmp_path):
    with pytest.raises(core.TerraformError):
        core.run_terraform(["apply", "-auto-approve"], tmp_path)


def test_terraform_guard_refuses_unknown_verb(tmp_path):
    with pytest.raises(core.TerraformError):
        core.run_terraform(["rm", "-rf"], tmp_path)


def test_load_plan_json_rejects_state_documents(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"format_version": "1.0"}), encoding="utf-8")
    with pytest.raises(core.PlanFormatError):
        core.load_plan_json(path)


def test_load_plan_json_rejects_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(core.PlanFormatError):
        core.load_plan_json(path)
