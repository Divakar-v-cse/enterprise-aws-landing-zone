# Monitoring and auditing

## 1. CloudWatch

| Component | Setting | Cost |
|---|---|---|
| Log groups | One per stream class: app, system, audit | 5 GB ingest free, then ~\$0.50/GB |
| Retention | 14 d dev · 30 d staging · 90 d prod app · 365 d audit | ~\$0.03/GB-month |
| Dashboard | `eawlz-<env>-overview` (CPU, network, error query) | free (3 dashboards) |
| Alarms | CPU > threshold, status-check failed, per instance | ~\$0.10/alarm-month, opt-in |
| SNS topic | Alarm delivery, encrypted with `alias/aws/sns` or CMK | free tier covers email |
| Flow logs | VPC-level, opt-in | ingest + storage |

Alarms are opt-in (`enable_alarms`) and forced off in zero-cost mode. The dashboard
is free, so it is always created — a dashboard nobody pays for is the cheapest
useful observability you can ship.

## 2. CloudTrail

| Setting | Value | Why |
|---|---|---|
| Multi-region | `true` | An actor cannot hide by using another region |
| Log file validation | `true` | Digest files prove logs were not altered |
| Global service events | `true` | IAM/STS changes are captured |
| Event selection | Management events only | Data events are the highest-volume cost |
| Retention | Glacier IR at 90 d, expire at 365 d | Audit window with a bounded bill |
| Bucket policy | `aws:SourceArn` condition + TLS deny | Confused-deputy and transport protection |
| KMS | CMK when the environment has one | Encryption at rest for audit data |

CloudTrail is opt-in because it is billable beyond the free copy of management
events. Staging and production enable it; dev does not.

## 3. What you can answer with this telemetry

| Question | Source |
|---|---|
| Who changed an IAM policy at 02:14? | CloudTrail `UpdateAssumeRolePolicy` / `PutRolePolicy` |
| Did anyone disable logging? | CloudTrail `StopLogging` (and the deny guardrail that prevents it) |
| Which instance is saturated? | CloudWatch `CPUUtilization` per instance |
| Did the app throw after deploy? | Log Insights query on the app group |
| Was there an S3 policy change? | CloudTrail `PutBucketPolicy` |

## 4. What is deliberately missing

| Gap | Reason | Next step |
|---|---|---|
| CloudTrail → CloudWatch Logs metric filters | Ingestion cost; scheduled with detection engineering | Add filters for root login, MFA changes, ingress 0.0.0.0/0 |
| GuardDuty / Security Hub | Not enabled (cost + account-level scope) | Enable at organisation level |
| AWS Config rules | Out of scope for a zero-cost validation profile | Add conformance packs in a real account |
| Centralised log archive account | Single-account scope | Organisation trail into a dedicated account |
| SLO dashboards | No application yet | Add with the first workload |

## 5. Operating the dashboard

```bash
# After a real deployment (requires credentials)
aws cloudwatch list-dashboards --query 'DashboardEntries[].DashboardName'
echo "https://$AWS_REGION.console.aws.amazon.com/cloudwatch/home?region=$AWS_REGION#dashboards:name=eawlz-production-overview"
```

Nothing in this section has been executed against AWS; it documents the intended
operating procedure.
