output "app_log_group_names" {
  description = "Application log group names created."
  value       = [for lg in aws_cloudwatch_log_group.app : lg.name]
}

output "audit_log_group_names" {
  description = "Audit log group names created."
  value       = [for lg in aws_cloudwatch_log_group.audit : lg.name]
}

output "dashboard_name" {
  description = "CloudWatch dashboard name."
  value       = aws_cloudwatch_dashboard.this.dashboard_name
}

output "alarm_topic_arn" {
  description = "SNS topic ARN for alarm notifications, or null when alarms are disabled."
  value       = try(aws_sns_topic.alarms[0].arn, null)
}

output "alarm_names" {
  description = "CloudWatch alarm names created."
  value       = concat([for a in aws_cloudwatch_metric_alarm.cpu_high : a.alarm_name], [for a in aws_cloudwatch_metric_alarm.status_check_failed : a.alarm_name])
}

output "cloudtrail_arn" {
  description = "CloudTrail trail ARN, or null when disabled."
  value       = try(aws_cloudtrail.this[0].arn, null)
}

output "cloudtrail_bucket" {
  description = "S3 bucket receiving CloudTrail logs, or null when disabled."
  value       = try(aws_s3_bucket.cloudtrail[0].id, null)
}
