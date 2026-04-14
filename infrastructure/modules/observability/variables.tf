variable "project" {
  description = "Project identifier used to tag and name observability resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment label (e.g., dev, staging, prod)."
  type        = string
}

variable "name_prefix" {
  description = "Optional override for generated observability resource names."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Additional tags to apply to observability resources."
  type        = map(string)
  default     = {}
}

variable "metrics_sources" {
  description = <<-EOT
    Identifiers used to wire dashboards and alarms. Each attribute is optional:
      - ingestion_queue: SQS queue name or ARN for ingestion metrics
      - search_service: ECS service name or Lambda function name for runtime metrics
      - vector_store: Identifier for the active vector store deployment
      - embedding_job: Identifier for the embedding job orchestration
  EOT
  type = object({
    ingestion_queue = optional(string)
    search_service  = optional(string)
    vector_store    = optional(string)
    embedding_job   = optional(string)
  })
  default = {}
}

variable "enable_dashboards" {
  description = "Toggle creation of CloudWatch dashboards."
  type        = bool
  default     = true
}

variable "enable_alarms" {
  description = "Toggle creation of CloudWatch alarms."
  type        = bool
  default     = true
}

variable "dashboard_timeframe_hours" {
  description = "Default time range (in hours) displayed on dashboards."
  type        = number
  default     = 24
}

variable "alarm_thresholds" {
  description = <<-EOT
    Overrides for alarm thresholds. Attributes are optional:
      - search_latency_p95: Maximum acceptable P95 latency in milliseconds
      - search_error_rate: Maximum acceptable error rate percentage
      - lambda_throttles: Threshold for Lambda throttle count (per minute)
      - ecs_unhealthy_host_count: Threshold for unhealthy ECS targets
  EOT
  type = object({
    search_latency_p95       = optional(number)
    search_error_rate        = optional(number)
    lambda_throttles         = optional(number)
    ecs_unhealthy_host_count = optional(number)
  })
  default = {}
}

variable "notification_topic_arn" {
  description = "SNS topic ARN to receive alarm notifications. Leave empty to disable notifications."
  type        = string
  default     = ""
}

variable "log_group_names" {
  description = "Mapping of component identifiers to CloudWatch Log Group names for linking log insights widgets."
  type        = map(string)
  default     = {}
}

variable "widget_queries" {
  description = "Custom CloudWatch Logs Insights queries keyed by widget identifier."
  type        = map(string)
  default     = {}
}
