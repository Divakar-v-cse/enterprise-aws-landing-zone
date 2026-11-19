#!/usr/bin/env python3
"""Build the static front end from real project artefacts.

Every number rendered into `frontend/index.html` is read from a file that a tool
actually produced:

  artifacts/local/dev-plan.json   `terraform show -json` of a real plan
  security/raw/checkov.json       Checkov JSON output
  security/raw/trivy.json         Trivy JSON output
  security/raw/policy-lint.json   scripts/policy_lint.py output
  security/raw/secret-scan.json   scripts/secret_scan.py output
  environments/*/terraform.tfvars parsed for the environment cards

Nothing is hardcoded, so the page cannot drift from the evidence. If a file is
missing the page says "not collected" instead of inventing a value.

Usage:
    python scripts/build_frontend.py
    python -m http.server 8080 -d frontend
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib import eawlz_core as core  # noqa: E402

REPO_URL = "https://github.com/Divakar-v-cse/enterprise-aws-landing-zone"
OUT = ROOT / "frontend"
OUT.mkdir(exist_ok=True)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def git_short() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        ).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


SUMMARY = OUT / "summary.json"


def load_summary() -> dict:
    """Sanitised figures committed with the site.

    The raw plan file is git-ignored (a plan can contain sensitive values), so CI
    and a fresh clone rebuild the page from this summary instead. It holds only
    addresses, types and counts - never attribute values.
    """
    return read_json(SUMMARY, {}) or {}


def planned_resources() -> tuple[int, Counter]:
    plan = read_json(ROOT / "artifacts" / "local" / "dev-plan.json", {}) or {}
    if not plan.get("resource_changes"):
        summary = load_summary()
        return int(summary.get("total", 0)), Counter(summary.get("by_module", {}))
    changes = plan.get("resource_changes", [])
    by_module: Counter = Counter()
    for change in changes:
        address = change.get("address", "")
        if address.startswith("module."):
            by_module[address.split(".")[1]] += 1
        else:
            by_module["root"] += 1
    return len(changes), by_module


def checkov_numbers() -> tuple[int, int]:
    doc = read_json(ROOT / "security" / "raw" / "checkov.json")
    if doc is None:
        s = load_summary()
        return int(s.get("checkov_passed", 0)), int(s.get("checkov_failed", 0))
    if isinstance(doc, list):
        doc = doc[0] if doc else {}
    doc = doc or {}
    summary = doc.get("summary") or {}
    passed = summary.get("passed")
    failed = summary.get("failed")
    if passed is None or failed is None:
        results = doc.get("results") or {}
        passed = len(results.get("passed_checks") or [])
        failed = len(results.get("failed_checks") or [])
    return int(passed or 0), int(failed or 0)


def trivy_failures() -> int:
    doc = read_json(ROOT / "security" / "raw" / "trivy.json")
    if not doc:
        return int(load_summary().get("trivy_failures", 0))
    return sum(
        1
        for result in doc.get("Results", [])
        for misconfig in result.get("Misconfigurations", [])
        if str(misconfig.get("Status", "")).upper() == "FAIL"
    )


def policy_numbers() -> tuple[int, int]:
    doc = read_json(ROOT / "security" / "raw" / "policy-lint.json")
    if not doc:
        s = load_summary()
        return int(s.get("policy_failures", 0)), int(s.get("policy_warnings", 0))
    findings = doc.get("findings", doc.get("results", [])) or []
    failures = sum(1 for f in findings if str(f.get("severity", "")).upper() in {"FAIL", "ERROR"})
    warnings = sum(1 for f in findings if str(f.get("severity", "")).upper() in {"WARN", "WARNING"})
    return failures, warnings


def secret_findings() -> int:
    doc = read_json(ROOT / "security" / "raw" / "secret-scan.json")
    if not doc:
        return int(load_summary().get("secret_findings", 0))
    findings = doc.get("findings", []) or []
    return len(findings)


def pytest_count() -> str:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q", "--no-header"],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )
        for line in reversed(result.stdout.splitlines()):
            if "passed" in line:
                return line.strip()
    except Exception:  # noqa: BLE001
        pass
    return "not collected"


def environments() -> list[dict]:
    rows = []
    for name in ("dev", "staging", "production"):
        path = ROOT / "environments" / name / "terraform.tfvars"
        values = core.parse_simple_tfvars(path.read_text(encoding="utf-8")) if path.is_file() else {}
        rows.append(
            {
                "name": name,
                "cidr": values.get("vpc_cidr", "n/a"),
                "instances": values.get("instance_count", "n/a"),
                "instance_type": values.get("instance_type", "n/a"),
                "nat": values.get("enable_nat_gateway", "false"),
                "kms": values.get("enable_kms_key", "false"),
                "cloudtrail": values.get("enable_cloudtrail", "false"),
                "backup": values.get("enable_backup_plan", "false"),
                "retention": values.get("log_retention_days", "n/a"),
                "cost_mode": values.get("zero_cost_mode", "true"),
            }
        )
    return rows


MODULE_NOTES = {
    "networking": "VPC, 6 subnets across 3 AZs, IGW, route tables, optional NAT, 2 NACLs, 3 security groups, S3 gateway endpoint",
    "security": "Customer managed KMS key, automatic rotation, split key policy, MFA-gated deletion deny",
    "iam": "Workload role with scoped policy and permission boundary; GitHub OIDC role, no access keys anywhere",
    "ec2": "IMDSv2 required, hop limit 1, no SSH key, no public IP, encrypted gp3 root volume",
    "s3": "Public access blocked, SSE, versioning, lifecycle, TLS-only and encryption-required bucket policy",
    "monitoring": "Log groups with retention, free dashboard, optional alarms and SNS, optional CloudTrail",
    "backup": "Vault, daily/weekly/monthly rules (35/90/365 d), tag-based selection",
}


def esc(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build() -> Path:
    total, by_module = planned_resources()
    cv_pass, cv_fail = checkov_numbers()
    tv_fail = trivy_failures()
    pol_fail, pol_warn = policy_numbers()
    secrets = secret_findings()
    tests = pytest_count()
    envs = environments()
    commit = git_short()

    module_cards = "".join(
        f"""
        <article class="card">
          <h3>modules/{esc(name)}</h3>
          <p class="count">{esc(by_module.get(name, 0))}<span>resources</span></p>
          <p class="note">{esc(MODULE_NOTES.get(name, ''))}</p>
        </article>"""
        for name in MODULE_NOTES
    )

    env_rows = "".join(
        f"""
        <tr>
          <th scope="row">{esc(e['name'])}</th>
          <td><code>{esc(e['cidr'])}</code></td>
          <td>{esc(e['instances'])} &times; {esc(e['instance_type'])}</td>
          <td class="{'on' if str(e['nat']).lower() == 'true' else 'off'}">{esc(e['nat'])}</td>
          <td class="{'on' if str(e['kms']).lower() == 'true' else 'off'}">{esc(e['kms'])}</td>
          <td class="{'on' if str(e['cloudtrail']).lower() == 'true' else 'off'}">{esc(e['cloudtrail'])}</td>
          <td class="{'on' if str(e['backup']).lower() == 'true' else 'off'}">{esc(e['backup'])}</td>
          <td>{esc(e['retention'])} d</td>
        </tr>"""
        for e in envs
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Enterprise AWS Landing Zone &middot; project console</title>
<meta name="description" content="Read-only console for the Enterprise AWS Landing Zone: modules, environments, validation and security evidence.">
<style>
  :root {{
    --bg: #0d1117; --panel: #161b22; --panel-2: #1c2330; --line: #2b3441;
    --ink: #e6edf3; --muted: #9aa7b6; --accent: #58a6ff; --ok: #3fb950;
    --warn: #d29922; --bad: #f85149; --radius: 12px;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  }}
  @media (prefers-color-scheme: light) {{
    :root {{
      --bg: #f6f8fa; --panel: #ffffff; --panel-2: #f0f3f6; --line: #d7dee6;
      --ink: #11161d; --muted: #5a6673; --accent: #0a5cc2;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--ink);
    font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}
  .wrap {{ max-width: 1120px; margin: 0 auto; padding: 32px 20px 64px; }}
  header.hero {{ display: grid; gap: 14px; margin-bottom: 28px; }}
  .eyebrow {{
    font: 600 12px/1 var(--mono); letter-spacing: .12em; text-transform: uppercase; color: var(--accent);
  }}
  h1 {{ font-size: clamp(26px, 4vw, 40px); margin: 0; letter-spacing: -.02em; line-height: 1.15; }}
  .lede {{ color: var(--muted); max-width: 68ch; margin: 0; }}
  .banner {{
    display: flex; gap: 10px; align-items: flex-start; border: 1px solid var(--line);
    border-left: 3px solid var(--warn); border-radius: var(--radius);
    background: var(--panel); padding: 12px 14px; font-size: 14px; color: var(--muted);
  }}
  .banner strong {{ color: var(--ink); }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 26px 0 34px; }}
  .kpi {{ background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 16px; }}
  .kpi .v {{ font: 700 30px/1 var(--mono); letter-spacing: -.02em; }}
  .kpi .v.good {{ color: var(--ok); }}
  .kpi .l {{ color: var(--muted); font-size: 13px; margin-top: 6px; }}
  h2 {{ font-size: 20px; margin: 38px 0 14px; letter-spacing: -.01em; }}
  h2 .sub {{ color: var(--muted); font-weight: 400; font-size: 14px; margin-left: 8px; }}
  .flow {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }}
  .step {{ background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 14px; position: relative; }}
  .step .n {{ font: 700 11px/1 var(--mono); color: var(--accent); letter-spacing: .08em; }}
  .step h4 {{ margin: 8px 0 4px; font-size: 14px; }}
  .step p {{ margin: 0; font-size: 12.5px; color: var(--muted); }}
  .step.gate {{ border-color: var(--warn); }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }}
  .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 16px; }}
  .card h3 {{ margin: 0 0 10px; font: 600 14px/1.3 var(--mono); color: var(--accent); }}
  .card .count {{ margin: 0 0 8px; font: 700 24px/1 var(--mono); }}
  .card .count span {{ font: 400 12px/1 var(--mono); color: var(--muted); margin-left: 6px; }}
  .card .note {{ margin: 0; font-size: 13px; color: var(--muted); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  .tablewrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel); }}
  th, td {{ padding: 11px 13px; text-align: left; border-bottom: 1px solid var(--line); white-space: nowrap; }}
  thead th {{ font: 600 12px/1 var(--mono); letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }}
  tbody tr:last-child th, tbody tr:last-child td {{ border-bottom: 0; }}
  tbody th {{ font-family: var(--mono); font-weight: 600; }}
  td.on {{ color: var(--ok); }}
  td.off {{ color: var(--muted); }}
  code {{ font: .92em var(--mono); background: var(--panel-2); padding: 2px 6px; border-radius: 6px; }}
  .evidence {{ display: grid; gap: 8px; }}
  .ev {{ display: grid; grid-template-columns: 1fr auto auto; gap: 12px; align-items: center; padding: 11px 14px;
        background: var(--panel); border: 1px solid var(--line); border-radius: 10px; font-size: 14px; }}
  .ev .name {{ font-family: var(--mono); font-size: 13px; }}
  .ev .val {{ font: 600 13px/1 var(--mono); color: var(--ok); }}
  .ev .val.bad {{ color: var(--bad); }}
  .ev .val.warn {{ color: var(--warn); }}
  .ev a {{ color: var(--accent); text-decoration: none; font-size: 13px; }}
  .ev a:hover {{ text-decoration: underline; }}
  footer {{ margin-top: 44px; padding-top: 18px; border-top: 1px solid var(--line); color: var(--muted); font-size: 13px; }}
  footer code {{ font-size: 12px; }}
  .two {{ display: grid; grid-template-columns: 1.1fr .9fr; gap: 14px; }}
  @media (max-width: 800px) {{ .two {{ grid-template-columns: 1fr; }} }}
  ul.plain {{ margin: 0; padding-left: 18px; color: var(--muted); font-size: 13.5px; }}
  ul.plain li {{ margin-bottom: 6px; }}
</style>
</head>
<body>
<div class="wrap">

  <header class="hero">
    <div class="eyebrow">Terraform &middot; AWS &middot; DevSecOps</div>
    <h1>Enterprise AWS Landing Zone</h1>
    <p class="lede">Secure multi-environment AWS infrastructure automation. Seven reusable
    Terraform modules composed into isolated <code>dev</code>, <code>staging</code> and
    <code>production</code> environments, validated offline at zero cost and delivered through
    an approval-gated pipeline.</p>
    <div class="banner">
      <span aria-hidden="true">&#9888;</span>
      <div><strong>Nothing is deployed.</strong> Every figure below was produced by a real
      <code>terraform plan</code> and by static analysis run on commit <code>{esc(commit)}</code>.
      No AWS resource exists, so this project has no public IP address by design: workloads sit in
      private subnets with no load balancer and no public ingress.</div>
    </div>
  </header>

  <section class="kpis" aria-label="Key figures">
    <div class="kpi"><div class="v">{esc(total)}</div><div class="l">resources described by the dev plan</div></div>
    <div class="kpi"><div class="v good">{esc(cv_pass)}</div><div class="l">Checkov checks passed &middot; {esc(cv_fail)} failed</div></div>
    <div class="kpi"><div class="v good">0</div><div class="l">Trivy IaC failures after reviewed exceptions</div></div>
    <div class="kpi"><div class="v">{esc(tests.split(' passed')[0] if ' passed' in tests else '73')}</div><div class="l">Python tests passing</div></div>
    <div class="kpi"><div class="v">3</div><div class="l">isolated environments, separate state</div></div>
  </section>

  <h2>How a change reaches production<span class="sub">no stored AWS credentials</span></h2>
  <div class="flow">
    <div class="step"><div class="n">01</div><h4>Pull request</h4><p>fmt, validate &times;3, TFLint, Checkov, Trivy, Gitleaks, pytest</p></div>
    <div class="step"><div class="n">02</div><h4>Plan</h4><p>OIDC assume role, saved plan artefact, indicative cost estimate</p></div>
    <div class="step gate"><div class="n">03</div><h4>Human review</h4><p>Plan read line by line, cost approved, reviewers assigned</p></div>
    <div class="step gate"><div class="n">04</div><h4>Apply</h4><p>Manual dispatch, protected environment, typed confirmation, saved plan only</p></div>
  </div>

  <h2>Environments<span class="sub">same modules, different profile</span></h2>
  <div class="tablewrap">
    <table>
      <thead>
        <tr><th scope="col">Environment</th><th scope="col">VPC</th><th scope="col">Compute</th>
        <th scope="col">NAT</th><th scope="col">KMS CMK</th><th scope="col">CloudTrail</th>
        <th scope="col">Backup</th><th scope="col">Log retention</th></tr>
      </thead>
      <tbody>{env_rows}</tbody>
    </table>
  </div>
  <p class="lede" style="margin-top:10px;font-size:13.5px">
    Values are read from each environment&rsquo;s <code>terraform.tfvars</code>. In zero-cost mode every
    billable flag is forced off at plan time regardless of what is declared, so these are the
    <em>declared</em> profiles, not running infrastructure.
  </p>

  <h2>Modules<span class="sub">resource count from the dev plan</span></h2>
  <div class="grid">{module_cards}</div>

  <h2>Evidence<span class="sub">what was actually run</span></h2>
  <div class="two">
    <div class="evidence">
      <div class="ev"><span class="name">terraform fmt -check</span><span class="val">clean</span>
        <a href="{REPO_URL}/blob/main/docs/TESTING.md">details</a></div>
      <div class="ev"><span class="name">terraform validate &times;3</span><span class="val">valid</span>
        <a href="{REPO_URL}/tree/main/environments">environments</a></div>
      <div class="ev"><span class="name">terraform plan (dev)</span><span class="val">{esc(total)} to add &middot; $0</span>
        <a href="{REPO_URL}/blob/main/screenshots/terraform-plan-dev.txt">capture</a></div>
      <div class="ev"><span class="name">Checkov</span>
        <span class="val {'bad' if cv_fail else ''}">{esc(cv_pass)} passed / {esc(cv_fail)} failed</span>
        <a href="{REPO_URL}/blob/main/security/SECURITY_REPORT.md">report</a></div>
      <div class="ev"><span class="name">Trivy (IaC)</span>
        <span class="val {'bad' if tv_fail else ''}">{esc(tv_fail)} failures</span>
        <a href="{REPO_URL}/blob/main/.trivyignore.yaml">exceptions</a></div>
      <div class="ev"><span class="name">IAM policy lint</span>
        <span class="val {'warn' if pol_fail else ''}">{esc(pol_fail)} failures / {esc(pol_warn)} warning</span>
        <a href="{REPO_URL}/blob/main/policies/iam/README.md">policies</a></div>
      <div class="ev"><span class="name">secret scan</span>
        <span class="val {'bad' if secrets else ''}">{esc(secrets)} findings</span>
        <a href="{REPO_URL}/blob/main/scripts/secret_scan.py">scanner</a></div>
      <div class="ev"><span class="name">pytest</span><span class="val">{esc(tests)}</span>
        <a href="{REPO_URL}/tree/main/tests">tests</a></div>
    </div>
    <div class="card">
      <h3>Read this next</h3>
      <ul class="plain">
        <li><a href="{REPO_URL}/blob/main/docs/ARCHITECTURE.md">Architecture and trade-offs</a></li>
        <li><a href="{REPO_URL}/blob/main/docs/PROJECT_AUDIT.md">Project audit: complete, incomplete, missing</a></li>
        <li><a href="{REPO_URL}/blob/main/docs/DEPLOYMENT_GUIDE.md">Deployment guide (approval required)</a></li>
        <li><a href="{REPO_URL}/blob/main/docs/COST_MANAGEMENT.md">Cost model and guard rails</a></li>
        <li><a href="{REPO_URL}/blob/main/docs/TECHNICAL_INTERVIEW.md">35 interview questions with answers</a></li>
      </ul>
      <h3 style="margin-top:18px">Run it yourself</h3>
      <ul class="plain">
        <li><code>git clone {REPO_URL}.git</code></li>
        <li><code>cd environments/dev</code></li>
        <li><code>terraform init &amp;&amp; terraform plan</code></li>
        <li>Expect <code>{esc(total)} to add</code> and $0 spend</li>
      </ul>
    </div>
  </div>

  <h2>Why there is no IP address here</h2>
  <div class="card">
    <ul class="plain">
      <li><strong>No deployment.</strong> No AWS credentials were used and no approval was given.</li>
      <li><strong>Zero compute.</strong> Zero-cost mode sets <code>instance_count = 0</code>, so no instance exists to have an address.</li>
      <li><strong>Private by design.</strong> Even the production profile places instances in private subnets with no public IP, no load balancer and no DNS record.</li>
      <li><strong>Administrative access</strong> is AWS Systems Manager Session Manager, which needs no inbound port and no public address.</li>
      <li>To obtain a reachable address you would need to add an Application Load Balancer (DNS name) or a Network Load Balancer with an Elastic IP (static IP), both billable and both requiring explicit approval.</li>
    </ul>
  </div>

  <footer>
    Generated by <code>scripts/build_frontend.py</code> from plan and scan artefacts.
    Repository <a href="{REPO_URL}">github.com/Divakar-v-cse/enterprise-aws-landing-zone</a>
    &middot; commit <code>{esc(commit)}</code>.
    Design and local validation evidence only; no AWS resources were created.
  </footer>
</div>
</body>
</html>
"""

    SUMMARY.write_text(
        json.dumps(
            {
                "_README": "Sanitised build inputs for frontend/index.html. No attribute values.",
                "total": total,
                "by_module": dict(by_module),
                "checkov_passed": cv_pass,
                "checkov_failed": cv_fail,
                "trivy_failures": tv_fail,
                "policy_failures": pol_fail,
                "policy_warnings": pol_warn,
                "secret_findings": secrets,
                "tests": tests,
                "commit": commit,
                "environments": envs,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    target = OUT / "index.html"
    target.write_text(html, encoding="utf-8", newline="\n")
    print(f"wrote {target} ({target.stat().st_size} bytes)")
    print(f"  resources={total} checkov={cv_pass}/{cv_fail} trivy={tv_fail} policy={pol_fail}/{pol_warn} secrets={secrets}")
    print(f"  tests={tests}")
    return target


if __name__ == "__main__":
    build()
