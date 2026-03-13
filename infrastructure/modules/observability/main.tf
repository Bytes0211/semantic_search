terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

data "aws_region" "current" {
  current = true
}

locals {
  name_prefix = var.name_prefix != "" ? var.name_prefix : "${var.project}-${var.environment}-observability"

  common_tags = merge({
    Project     = var.project
    Environment = var.environment
    Module      = "observability"
  }, var.tags)

  default_alarm_thresholds = {
    search_latency_p95       = 900
    search_error_rate        = 2
    lambda_throttles         = 1
    ecs_unhealthy_host_count = 1
  }

  resolved_alarm_thresholds = merge(local.default_alarm_thresholds, var.alarm_thresholds)

  runtime_metrics_namespace = "SemanticSearch/Runtime"

  search_service_identifier  = try(var.metrics_sources.search_service, null)
  ingestion_queue_identifier = try(var.metrics_sources.ingestion_queue, null)
  vector_store_identifier    = try(var.metrics_sources.vector_store, null)
  embedding_job_identifier   = try(var.metrics_sources.embedding_job, null)

  ingestion_queue_name = (
    local.ingestion_queue_identifier == null ? null :
    (
      can(regex("^arn:aws:sqs", local.ingestion_queue_identifier)) ?
      element(split(":", local.ingestion_queue_identifier), length(split(":", local.ingestion_queue_identifier)) - 1) :
      local.ingestion_queue_identifier
    )
  )

  search_latency_widget = local.search_service_identifier == null ? null : {
    type   = "metric"
    x      = 0
    y      = 0
    width  = 12
    height = 6

    properties = {
      metrics = [
        [local.runtime_metrics_namespace, "QueryLatencyP95", "ServiceName", local.search_service_identifier]
      ]
      stat   = "Average"
      period = 60
      title  = "Search Runtime P95 Latency"
      view   = "timeSeries"
      yAxis = {
        left = {
          min = 0
        }
      }
    }
  }

  search_error_rate_widget = local.search_service_identifier == null ? null : {
    type   = "metric"
    x      = 12
    y      = 0
    width  = 12
    height = 6

    properties = {
      metrics = [
        [local.runtime_metrics_namespace, "QueryErrorRate", "ServiceName", local.search_service_identifier]
      ]
      stat   = "Average"
      period = 60
      title  = "Search Runtime Error Rate (%)"
      view   = "timeSeries"
      yAxis = {
        left = {
          min = 0
          max = 100
        }
      }
    }
  }

  ingestion_queue_depth_widget = local.ingestion_queue_name == null ? null : {
    type   = "metric"
    x      = 0
    y      = 6
    width  = 12
    height = 6

    properties = {
      metrics = [
        ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", local.ingestion_queue_name]
      ]
      stat   = "Average"
      period = 60
      title  = "Ingestion Queue Depth"
      view   = "timeSeries"
    }
  }

  dashboard_metric_widgets = [
    for widget in [
      local.search_latency_widget,
      local.search_error_rate_widget,
      local.ingestion_queue_depth_widget
    ] : widget if widget != null
  ]

  log_groups = [
    for key, group in var.log_group_names : {
      key   = key
      group = group
      query = try(var.widget_queries[key], "fields @timestamp, @message | sort @timestamp desc | limit 20")
    }
  ]

  log_widgets = [
    for idx, item in local.log_groups : {
      type   = "log"
      x      = (idx % 2) * 12
      y      = 6 + floor(idx / 2) * 6
      width  = 12
      height = 6

      properties = {
        query  = format("SOURCE '%s' | %s", item.group, item.query)
        region = data.aws_region.current.name
        title  = format("%s Logs", item.key)
        view   = "table"
      }
    }
  ]

  dashboard_widgets = concat(local.dashboard_metric_widgets, local.log_widgets)

  dashboard_body = jsonencode({
    widgets = local.dashboard_widgets
  })
}

resource "aws_cloudwatch_dashboard" "main" {
  count = var.enable_dashboards && length(local.dashboard_widgets) > 0 ? 1 : 0

  dashboard_name = "${local.name_prefix}-cw-dashboard"
  dashboard_body = local.dashboard_body
}

resource "aws_cloudwatch_metric_alarm" "search_latency" {
  count = var.enable_alarms && local.search_service_identifier != null ? 1 : 0

  alarm_name          = "${local.name_prefix}-search-latency-p95"
  alarm_description   = "Alert when the semantic search runtime exceeds the P95 latency threshold."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "QueryLatencyP95"
  namespace           = local.runtime_metrics_namespace
  period              = 60
  statistic           = "Average"
  threshold           = local.resolved_alarm_thresholds.search_latency_p95
  treat_missing_data  = "notBreaching"

  dimensions = {
    ServiceName = local.search_service_identifier
  }

  alarm_actions             = var.notification_topic_arn != "" ? [var.notification_topic_arn] : []
  ok_actions                = var.notification_topic_arn != "" ? [var.notification_topic_arn] : []
  insufficient_data_actions = []

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "search_error_rate" {
  count = var.enable_alarms && local.search_service_identifier != null ? 1 : 0

  alarm_name          = "${local.name_prefix}-search-error-rate"
  alarm_description   = "Alert when the semantic search runtime error rate exceeds the defined threshold."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "QueryErrorRate"
  namespace           = local.runtime_metrics_namespace
  period              = 60
  statistic           = "Average"
  threshold           = local.resolved_alarm_thresholds.search_error_rate
  treat_missing_data  = "notBreaching"

  dimensions = {
    ServiceName = local.search_service_identifier
  }

  alarm_actions             = var.notification_topic_arn != "" ? [var.notification_topic_arn] : []
  ok_actions                = var.notification_topic_arn != "" ? [var.notification_topic_arn] : []
  insufficient_data_actions = []

  tags = local.common_tags
}

output "dashboard_name" {
  description = "CloudWatch dashboard name created by the observability module."
  value       = var.enable_dashboards && length(aws_cloudwatch_dashboard.main) > 0 ? aws_cloudwatch_dashboard.main[0].dashboard_name : null
}

output "alarm_names" {
  description = "List of CloudWatch alarm names managed by this module."
  value = concat(
    var.enable_alarms && length(aws_cloudwatch_metric_alarm.search_latency) > 0 ? [aws_cloudwatch_metric_alarm.search_latency[0].alarm_name] : [],
    var.enable_alarms && length(aws_cloudwatch_metric_alarm.search_error_rate) > 0 ? [aws_cloudwatch_metric_alarm.search_error_rate[0].alarm_name] : []
  )
}

output "alarm_arns" {
  description = "List of CloudWatch alarm ARNs managed by this module."
  value = concat(
    var.enable_alarms && length(aws_cloudwatch_metric_alarm.search_latency) > 0 ? [aws_cloudwatch_metric_alarm.search_latency[0].arn] : [],
    var.enable_alarms && length(aws_cloudwatch_metric_alarm.search_error_rate) > 0 ? [aws_cloudwatch_metric_alarm.search_error_rate[0].arn] : []
  )
}
