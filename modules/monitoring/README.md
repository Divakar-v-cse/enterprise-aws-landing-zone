# Module: monitoring

Observability and audit layer: retained log groups, a free CloudWatch dashboard,
optional per-instance alarms, and an optional multi-region CloudTrail trail with
log file validation.

## Cost matrix

| Resource | Default | Billing notes |
|---|---|---|
| `aws_cloudwatch_log_group` | created | 5 GB ingest free, then ~\$0.50/GB; storage ~\$0.03/GB-month |
| `aws_cloudwatch_dashboard` | created (3 dashboards free) | free |
| `aws_cloudwatch_metric_alarm` | `enable_alarms = false` | ~\$0.10/alarm-month (10 free) |
| `aws_sns_topic` | only with alarms | first 1,000 email notifications free |
| `aws_cloudtrail` | `enable_cloudtrail = false` | first copy of management events free; S3 storage billed |
| CloudTrail S3 bucket | only with trail | storage + requests |

## Retention policy

| Stream class | Retention | Rationale |
|---|---|---|
| application (`/eawlz-*/app`) | 30 days | debugging window, keeps cost bounded |
| system (`/eawlz-*/system`) | 30 days | bootstrap and OS logs |
| audit (`/eawlz-*/audit`) | 365 days | security investigations and compliance |

`log_retention_days` / `audit_log_retention_days` are validated against the exact
retention values CloudWatch Logs accepts, so an invalid value fails at `plan`
rather than at `apply`.

## CloudTrail design

* Multi-region trail (`is_multi_region_trail = true`) — an attacker cannot hide by
  operating in another region.
* `enable_log_file_validation = true` — digest files prove logs were not altered.
* Bucket policy scoped with `aws:SourceArn` (confused-deputy protection) and a
  TLS-only deny.
* Management events only. Data events are the highest-volume, highest-cost
  events; enable them selectively per bucket once a real audit requirement exists.

## Plan-time note

`instance_count` (not `instance_ids`) drives `count`, because instance IDs are
unknown until apply. Using `length(instance_ids)` would fail with
"count cannot be determined until apply" on the first plan.
