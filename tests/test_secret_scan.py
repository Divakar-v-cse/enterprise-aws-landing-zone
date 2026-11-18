"""Tests for the secret scanner.

Fixture secrets are assembled at runtime so this test file does not itself
contain a literal credential that other scanners would flag.
"""

from lib import eawlz_core as core

FAKE_AWS_KEY = "AKIA" + "Q" * 16
FAKE_SECRET = "password = " + chr(34) + "S3cr3t-Value-For-Test-Only" + chr(34)


def test_detects_aws_access_key_id():
    findings = core.scan_text_for_secrets(f"key: {FAKE_AWS_KEY}", "x.tf")
    assert findings and findings[0].rule == "AWS access key ID"
    assert FAKE_AWS_KEY not in findings[0].excerpt


def test_detects_assigned_secret():
    findings = core.scan_text_for_secrets(FAKE_SECRET, "x.tf")
    assert findings


def test_detects_private_key_block():
    text = "-----BEGIN " + "RSA PRIVATE KEY-----"
    assert core.scan_text_for_secrets(text)


def test_clean_terraform_has_no_findings():
    text = 'resource "aws_s3_bucket" "b" { bucket = "example" }'
    assert core.scan_text_for_secrets(text) == []


def test_placeholder_is_not_a_secret():
    text = 'variable "aws_access_key" { default = "" }'
    assert core.scan_text_for_secrets(text) == []


def test_should_scan_file_skips_binaries_and_terraform_cache(tmp_path):
    root = tmp_path
    binary = root / "image.png"
    binary.write_bytes(b"\x89PNG")
    assert not core.should_scan_file(binary, root)

    cached = root / ".terraform" / "x.tf"
    cached.parent.mkdir()
    cached.write_text("x", encoding="utf-8")
    assert not core.should_scan_file(cached, root)

    source = root / "main.tf"
    source.write_text("x", encoding="utf-8")
    assert core.should_scan_file(source, root)
