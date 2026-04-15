# Variables for the search_service_lambda module.

variable "project" {
  description = "Project identifier used for naming and tagging resources."
  type        = string
}

variable "environment" {
  description = "Environment label (e.g., dev, staging, prod)."
  type        = string
}

variable "name_prefix" {
  description = "Optional override for generated resource names. Defaults to <project>-<environment>-lambda-search when empty."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Additional tags to merge into every resource."
  type        = map(string)
  default     = {}
}

variable "container_image" {
  description = "Container image URI (ECR) for the semantic search runtime Lambda."
  type        = string
}

variable "lambda_architecture" {
  description = "CPU architecture for the Lambda function (x86_64 or arm64)."
  type        = string
  default     = "x86_64"
  validation {
    condition     = contains(["x86_64", "arm64"], lower(var.lambda_architecture))
    error_message = "lambda_architecture must be either \"x86_64\" or \"arm64\"."
  }
}

variable "timeout_seconds" {
  description = "Lambda function timeout in seconds."
  type        = number
  default     = 30
}

variable "memory_mb" {
  description = "Amount of memory (in MB) allocated to the Lambda function."
  type        = number
  default     = 1024
}

variable "enable_ephemeral_storage" {
  description = "Enable custom ephemeral storage sizing for the Lambda runtime."
  type        = bool
  default     = false
}

variable "ephemeral_storage_mb" {
  description = "Ephemeral storage size in MB when custom storage is enabled (min 512, max 10240)."
  type        = number
  default     = 1024
}

variable "enable_provisioned_concurrency" {
  description = "Enable provisioned concurrency for predictable latency."
  type        = bool
  default     = false
}

variable "provisioned_concurrency_count" {
  description = "Number of provisioned concurrent executions to maintain when enabled."
  type        = number
  default     = 2
}

variable "vector_store_endpoint" {
  description = "Endpoint URL or connection string for the active vector store."
  type        = string
}

variable "embedding_endpoint" {
  description = "Endpoint URL for the configured embedding provider."
  type        = string
}

variable "ingestion_queue_arn" {
  description = "ARN of the ingestion/reindex queue consumed by the runtime."
  type        = string
}

variable "reindex_topic_arn" {
  description = "ARN of the SNS topic used for cross-service reindex notifications."
  type        = string
}

variable "log_level" {
  description = "Default log level for the runtime (e.g., INFO, DEBUG)."
  type        = string
  default     = "INFO"
}

variable "metrics_namespace" {
  description = "Namespace used by the runtime to emit custom metrics."
  type        = string
  default     = "SemanticSearch/Runtime"
}

variable "enable_request_tracing" {
  description = "Enable request-level tracing headers and propagation."
  type        = bool
  default     = false
}

variable "enable_query_logging" {
  description = "Enable structured logging of search queries for analytics/audit."
  type        = bool
  default     = false
}

variable "max_concurrent_queries" {
  description = "Application-level concurrency guard for the runtime."
  type        = number
  default     = 100
}

variable "default_top_k" {
  description = "Default number of results returned when top_k is not supplied."
  type        = number
  default     = 10
}

variable "max_top_k" {
  description = "Maximum number of results allowed per query."
  type        = number
  default     = 200
}

variable "candidate_multiplier" {
  description = "Candidate pool multiplier applied before metadata filters."
  type        = number
  default     = 3
}

variable "healthcheck_path" {
  description = "HTTP path used for health checks (mirrors /healthz in the runtime)."
  type        = string
  default     = "/healthz"
}

variable "readiness_path" {
  description = "HTTP path used for readiness checks (mirrors /readyz in the runtime)."
  type        = string
  default     = "/readyz"
}

variable "environment_variables" {
  description = "Additional plain-text environment variables injected into the runtime container."
  type        = map(string)
  default     = {}
}

variable "secret_arn_values" {
  description = "Mapping of environment variable names to Secrets Manager ARNs."
  type        = map(string)
  default     = {}
}

variable "log_retention_in_days" {
  description = "CloudWatch log retention period in days for the Lambda and API Gateway logs."
  type        = number
  default     = 14
}

variable "api_gateway_timeout_ms" {
  description = "Timeout (in milliseconds) for the API Gateway integration."
  type        = number
  default     = 29000
}

variable "api_gateway_stage" {
  description = "API Gateway stage name."
  type        = string
  default     = "$default"
}

variable "xray_tracing_mode" {
  description = "X-Ray tracing mode for the Lambda function (PassThrough or Active)."
  type        = string
  default     = "PassThrough"
  validation {
    condition     = contains(["PassThrough", "Active"], var.xray_tracing_mode)
    error_message = "xray_tracing_mode must be either \"PassThrough\" or \"Active\"."
  }
}

variable "alarm_throttle_threshold" {
  description = "Threshold for Lambda throttles that triggers a CloudWatch alarm."
  type        = number
  default     = 1
}

variable "vpc_id" {
  description = "VPC identifier used when the Lambda function runs inside a VPC."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnet IDs assigned to the Lambda function (empty list disables VPC attachment)."
  type        = list(string)
  default     = []
}

variable "additional_security_group_ids" {
  description = "Additional security groups attached to the Lambda ENIs."
  type        = list(string)
  default     = []
}

# ─── IAM Security ────────────────────────────────────────────────────────────

variable "permissions_boundary_arn" {
  type        = string
  description = "ARN of the IAM permissions boundary policy to attach to the Lambda execution role. Leave empty to skip."
  default     = ""
}

variable "deny_guardrail_policy_json" {
  type        = string
  description = "JSON policy document with deny-based guardrails to attach as an inline policy on the Lambda role. Leave empty to skip."
  default     = ""
}

variable "restrict_egress" {
  type        = bool
  description = "When true, restrict Lambda SG to HTTPS-only (443) egress."
  default     = true
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block (currently unused by Lambda module but kept for API consistency)."
  default     = ""
}
