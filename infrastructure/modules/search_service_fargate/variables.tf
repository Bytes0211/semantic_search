terraform {
  required_version = ">= 1.5.0"
}

variable "project" {
  description = "Project identifier used for resource naming conventions and tagging."
  type        = string
}

variable "environment" {
  description = "Deployment environment label (e.g., dev, staging, prod)."
  type        = string
}

variable "aws_region" {
  description = "AWS region the service is deployed to (used for log configuration)."
  type        = string
}

variable "name_prefix" {
  description = "Optional override for generated resource names. Defaults to <project>-<environment>-search when empty."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Additional tags to merge into every provisioned resource."
  type        = map(string)
  default     = {}
}

variable "vpc_id" {
  description = "VPC identifier where the ECS tasks and load balancer will be deployed."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnet identifiers for the ECS tasks."
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "Public subnet identifiers used by the Application Load Balancer."
  type        = list(string)
}

variable "additional_security_group_ids" {
  description = "Additional security groups to attach to the ECS service tasks."
  type        = list(string)
  default     = []
}

variable "allowed_ingress_cidrs" {
  description = "CIDR ranges permitted to access the ALB listener."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "acm_certificate_arn" {
  description = "ARN of the ACM certificate for HTTPS listener. Leave empty to skip HTTPS and use HTTP only (not recommended for production)."
  type        = string
  default     = ""
}

variable "container_image" {
  description = "Fully qualified container image URI for the semantic search runtime."
  type        = string
}

variable "cpu_architecture" {
  description = "CPU architecture for the Fargate task (X86_64 or ARM64)."
  type        = string
  default     = "X86_64"
  validation {
    condition     = contains(["X86_64", "ARM64"], var.cpu_architecture)
    error_message = "cpu_architecture must be either \"X86_64\" or \"ARM64\"."
  }
}

variable "cpu" {
  description = "CPU units allocated to the Fargate task (e.g., 1024)."
  type        = number
  default     = 1024
}

variable "memory" {
  description = "Memory (in MiB) allocated to the Fargate task (e.g., 2048)."
  type        = number
  default     = 2048
}

variable "container_port" {
  description = "Container port exposed by the FastAPI runtime."
  type        = number
  default     = 8080
}

variable "desired_count" {
  description = "Initial desired task count managed by ECS."
  type        = number
  default     = 2
}

variable "min_capacity" {
  description = "Minimum task count configured for autoscaling."
  type        = number
  default     = 2
}

variable "max_capacity" {
  description = "Maximum task count configured for autoscaling."
  type        = number
  default     = 6
}

variable "assign_public_ip" {
  description = "Whether Fargate tasks should be assigned public IP addresses."
  type        = bool
  default     = false
}

variable "platform_version" {
  description = "Fargate platform version to run (e.g., 1.4.0 or LATEST)."
  type        = string
  default     = "LATEST"
}

variable "log_retention_in_days" {
  description = "Retention period (in days) for CloudWatch Logs."
  type        = number
  default     = 14
}

variable "environment_variables" {
  description = "Additional plain-text environment variables injected into the container."
  type        = map(string)
  default     = {}
}

variable "secret_arn_values" {
  description = "Mapping of environment variable names to Secrets Manager ARNs."
  type        = map(string)
  default     = {}
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
  description = "ARN of the queue used to submit on-demand reindex jobs."
  type        = string
}

variable "reindex_topic_arn" {
  description = "ARN of the SNS topic used for cross-service reindex notifications."
  type        = string
}

variable "log_level" {
  description = "Default application log level (e.g., INFO, DEBUG)."
  type        = string
  default     = "INFO"
}

variable "metrics_namespace" {
  description = "Namespace used by the runtime to publish custom metrics."
  type        = string
  default     = "SemanticSearch/Runtime"
}

variable "enable_request_tracing" {
  description = "Enable request-level tracing within the runtime."
  type        = bool
  default     = false
}

variable "enable_query_logging" {
  description = "Enable structured logging of search queries for analytics."
  type        = bool
  default     = false
}

variable "max_concurrent_queries" {
  description = "Upper bound on concurrent requests processed by the runtime."
  type        = number
  default     = 100
}

variable "default_top_k" {
  description = "Default number of results returned when top_k is not specified."
  type        = number
  default     = 10
}

variable "max_top_k" {
  description = "Maximum number of results allowed per request."
  type        = number
  default     = 200
}

variable "candidate_multiplier" {
  description = "Multiplier applied to top_k to determine the candidate pool before filtering."
  type        = number
  default     = 3
}

variable "healthcheck_path" {
  description = "HTTP path used by the ALB to check task health."
  type        = string
  default     = "/healthz"
}

variable "readiness_path" {
  description = "HTTP path used by the runtime to signal readiness."
  type        = string
  default     = "/readyz"
}

variable "healthcheck_interval_seconds" {
  description = "Interval between load balancer health checks."
  type        = number
  default     = 30
}

variable "healthcheck_timeout_seconds" {
  description = "Timeout for load balancer health check responses."
  type        = number
  default     = 5
}

variable "healthcheck_healthy_threshold" {
  description = "Number of consecutive successes required before considering a target healthy."
  type        = number
  default     = 3
}

variable "healthcheck_unhealthy_threshold" {
  description = "Number of consecutive failures required before considering a target unhealthy."
  type        = number
  default     = 3
}

variable "alarm_http_5xx_threshold" {
  description = "Threshold for ALB target 5xx count that triggers an alarm."
  type        = number
  default     = 5
}

variable "startup_timeout_seconds" {
  description = "Grace period before the runtime is considered unhealthy during startup."
  type        = number
  default     = 60
}

variable "shutdown_timeout_seconds" {
  description = "Grace period granted to the runtime during shutdown hooks."
  type        = number
  default     = 30
}

variable "enable_request_based_scaling" {
  description = "Enable ALB RequestCountPerTarget autoscaling policy."
  type        = bool
  default     = false
}

variable "autoscaling_cpu_target" {
  description = "Target CPU utilization percentage for autoscaling."
  type        = number
  default     = 60
}

variable "autoscaling_requests_per_target" {
  description = "Desired number of requests per target when request-based autoscaling is enabled."
  type        = number
  default     = 50
}

variable "scale_in_cooldown_seconds" {
  description = "Cooldown period after a scale-in event."
  type        = number
  default     = 120
}

variable "scale_out_cooldown_seconds" {
  description = "Cooldown period after a scale-out event."
  type        = number
  default     = 60
}

# ─── IAM Security ────────────────────────────────────────────────────────────

variable "permissions_boundary_arn" {
  type        = string
  description = "ARN of the IAM permissions boundary policy to attach to the task role. Leave empty to skip."
  default     = ""
}

variable "deny_guardrail_policy_json" {
  type        = string
  description = "JSON policy document with deny-based guardrails to attach as an inline policy on the task role. Leave empty to skip."
  default     = ""
}

variable "restrict_egress" {
  type        = bool
  description = "When true, replace the all-traffic egress rule on the service SG with HTTPS-only (443) to the VPC CIDR."
  default     = true
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block used for scoped egress rules when restrict_egress is true."
  default     = ""

  validation {
    condition     = !var.restrict_egress || var.vpc_cidr != ""
    error_message = "vpc_cidr must be a non-empty CIDR block when restrict_egress is true."
  }
}
