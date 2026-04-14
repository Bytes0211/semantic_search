terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  default_tags = merge(
    {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
      Stack       = "semantic-search"
    },
    var.additional_tags
  )

}

module "core_network" {
  source = "../../modules/core_network"

  project                   = var.project
  environment               = var.environment
  vpc_cidr                  = var.vpc_cidr
  default_az_count          = var.default_az_count
  create_nat_gateway        = false
  enable_internet_gateway   = true
  enable_flow_logs          = var.enable_flow_logs
  flow_log_destination_type = var.flow_log_destination_type
  flow_log_destination_arn  = var.flow_log_destination_arn
  flow_log_iam_role_arn     = var.flow_log_iam_role_arn

  # VPC Endpoints
  enable_s3_endpoint         = var.enable_s3_endpoint
  enable_interface_endpoints = var.enable_interface_endpoints

  tags = local.default_tags
}

# ---------------------------------------------------------------------------
# IAM Security
# ---------------------------------------------------------------------------

module "iam_security" {
  source = "../../modules/iam_security"

  project     = var.project
  environment = var.environment
  tags        = local.default_tags

  enable_kms         = var.enable_kms
  enable_cloudtrail  = var.enable_cloudtrail
  enable_data_events = var.enable_cloudtrail_data_events

  # Scope the permission boundary to the project's data buckets once they exist.
  s3_bucket_arns = [
    module.data_plane.canonical_bucket_arn,
    module.data_plane.embeddings_bucket_arn,
    var.vector_store == "faiss" ? module.vector_store_faiss[0].index_bucket_arn : "arn:aws:s3:::unused",
  ]
  sqs_queue_arns = [module.data_plane.ingestion_queue_arn]
  sns_topic_arns = [module.data_plane.reindex_topic_arn]
}

module "data_plane" {
  source = "../../modules/data_plane"

  project               = var.project
  environment           = var.environment
  ingestion_mode        = var.ingestion_mode
  enable_step_functions = var.enable_step_functions
  enable_dedupe_store   = var.enable_dedupe_store
  bucket_lifecycle_days = var.bucket_lifecycle_days
  vpc_id                = module.core_network.vpc_id
  private_subnet_ids    = module.core_network.private_subnet_ids
  kms_key_arn           = var.enable_kms ? module.iam_security.kms_key_arn : ""
  tags                  = local.default_tags
}

# ---------------------------------------------------------------------------
# Embedding Provider Modules (count-gated — only one active at a time)
# ---------------------------------------------------------------------------

module "embedding_bedrock" {
  count  = var.embedding_backend == "bedrock" ? 1 : 0
  source = "../../modules/embedding_bedrock"

  project     = var.project
  environment = var.environment
  vpc_id      = module.core_network.vpc_id
  subnet_ids  = module.core_network.private_subnet_ids
  tags        = local.default_tags

  canonical_bucket_name  = module.data_plane.canonical_bucket_name
  embeddings_bucket_name = module.data_plane.embeddings_bucket_name
  reindex_topic_arn      = module.data_plane.reindex_topic_arn

  # TODO: Provide backend-specific configuration (model IDs, IAM policies, etc.).
}

module "embedding_spot" {
  count  = var.embedding_backend == "spot" ? 1 : 0
  source = "../../modules/embedding_spot"

  project     = var.project
  environment = var.environment
  vpc_id      = module.core_network.vpc_id
  subnet_ids  = module.core_network.private_subnet_ids
  tags        = local.default_tags

  canonical_bucket_name  = module.data_plane.canonical_bucket_name
  embeddings_bucket_name = module.data_plane.embeddings_bucket_name
  reindex_topic_arn      = module.data_plane.reindex_topic_arn

  # TODO: Provide backend-specific configuration (instance sizing, autoscaling, etc.).
}

module "embedding_sagemaker" {
  count  = var.embedding_backend == "sagemaker" ? 1 : 0
  source = "../../modules/embedding_sagemaker"

  project     = var.project
  environment = var.environment
  vpc_id      = module.core_network.vpc_id
  subnet_ids  = module.core_network.private_subnet_ids
  tags        = local.default_tags

  canonical_bucket_name  = module.data_plane.canonical_bucket_name
  embeddings_bucket_name = module.data_plane.embeddings_bucket_name
  reindex_topic_arn      = module.data_plane.reindex_topic_arn

  # TODO: Provide backend-specific configuration (endpoint configs, scaling policies, etc.).
}

locals {
  embedding_endpoint = (
    var.embedding_backend == "bedrock" ? module.embedding_bedrock[0].endpoint :
    var.embedding_backend == "spot" ? module.embedding_spot[0].endpoint :
    module.embedding_sagemaker[0].endpoint
  )
}

# ---------------------------------------------------------------------------
# Vector Store Modules (count-gated — only one active at a time)
# ---------------------------------------------------------------------------

module "vector_store_faiss" {
  count  = var.vector_store == "faiss" ? 1 : 0
  source = "../../modules/vector_store/faiss"

  project            = var.project
  environment        = var.environment
  vpc_id             = module.core_network.vpc_id
  subnet_ids         = module.core_network.private_subnet_ids
  security_group_ids = [] # TODO: populate with shared SGs once defined.

  ingestion_queue_arn = module.data_plane.ingestion_queue_arn
  tags                = local.default_tags
}

module "vector_store_qdrant" {
  count  = var.vector_store == "qdrant" ? 1 : 0
  source = "../../modules/vector_store/qdrant"

  project            = var.project
  environment        = var.environment
  vpc_id             = module.core_network.vpc_id
  subnet_ids         = module.core_network.private_subnet_ids
  security_group_ids = [] # TODO: populate with shared SGs once defined.

  ingestion_queue_arn = module.data_plane.ingestion_queue_arn
  tags                = local.default_tags
}

module "vector_store_pgvector" {
  count  = var.vector_store == "pgvector" ? 1 : 0
  source = "../../modules/vector_store/pgvector"

  project            = var.project
  environment        = var.environment
  vpc_id             = module.core_network.vpc_id
  subnet_ids         = module.core_network.private_subnet_ids
  security_group_ids = [] # TODO: populate with shared SGs once defined.

  ingestion_queue_arn = module.data_plane.ingestion_queue_arn
  tags                = local.default_tags

  # TODO: Surface pgvector-specific sizing and replication parameters.
}

locals {
  vector_store_endpoint = (
    var.vector_store == "faiss" ? module.vector_store_faiss[0].endpoint :
    var.vector_store == "qdrant" ? module.vector_store_qdrant[0].endpoint :
    module.vector_store_pgvector[0].endpoint
  )
}

# ---------------------------------------------------------------------------
# Search Service Modules (count-gated — only one active at a time)
# ---------------------------------------------------------------------------

module "search_service_fargate" {
  count  = var.search_runtime == "fargate" ? 1 : 0
  source = "../../modules/search_service_fargate"

  project     = var.project
  environment = var.environment
  aws_region  = var.aws_region
  vpc_id      = module.core_network.vpc_id
  # In dev there is no NAT gateway; tasks use public subnets with assign_public_ip=true
  # so they can reach ECR and Bedrock without a NAT.
  subnet_ids                      = module.core_network.public_subnet_ids
  public_subnet_ids               = module.core_network.public_subnet_ids
  additional_security_group_ids   = var.search_service_additional_security_group_ids
  allowed_ingress_cidrs           = var.search_service_allowed_ingress_cidrs
  acm_certificate_arn             = var.search_service_acm_certificate_arn
  vector_store_endpoint           = local.vector_store_endpoint
  embedding_endpoint              = local.embedding_endpoint
  ingestion_queue_arn             = module.data_plane.ingestion_queue_arn
  reindex_topic_arn               = module.data_plane.reindex_topic_arn
  container_image                 = var.search_service_container_image
  cpu                             = var.search_service_cpu
  memory                          = var.search_service_memory
  container_port                  = var.search_service_container_port
  desired_count                   = var.search_service_desired_count
  min_capacity                    = var.search_service_min_capacity
  max_capacity                    = var.search_service_max_capacity
  assign_public_ip                = var.search_service_assign_public_ip
  platform_version                = var.search_service_platform_version
  log_retention_in_days           = var.search_service_log_retention_in_days
  environment_variables           = var.search_service_environment_variables
  secret_arn_values               = var.search_service_secret_arn_values
  log_level                       = var.search_service_log_level
  metrics_namespace               = var.search_service_metrics_namespace
  enable_request_tracing          = var.search_service_enable_request_tracing
  enable_query_logging            = var.search_service_enable_query_logging
  max_concurrent_queries          = var.search_service_max_concurrent_queries
  default_top_k                   = var.search_service_default_top_k
  max_top_k                       = var.search_service_max_top_k
  candidate_multiplier            = var.search_service_candidate_multiplier
  healthcheck_path                = var.search_service_healthcheck_path
  readiness_path                  = var.search_service_readiness_path
  healthcheck_interval_seconds    = var.search_service_healthcheck_interval_seconds
  healthcheck_timeout_seconds     = var.search_service_healthcheck_timeout_seconds
  healthcheck_healthy_threshold   = var.search_service_healthcheck_healthy_threshold
  healthcheck_unhealthy_threshold = var.search_service_healthcheck_unhealthy_threshold
  alarm_http_5xx_threshold        = var.search_service_alarm_http_5xx_threshold
  startup_timeout_seconds         = var.search_service_startup_timeout_seconds
  shutdown_timeout_seconds        = var.search_service_shutdown_timeout_seconds
  enable_request_based_scaling    = var.search_service_enable_request_based_scaling
  autoscaling_cpu_target          = var.search_service_autoscaling_cpu_target
  autoscaling_requests_per_target = var.search_service_autoscaling_requests_per_target
  scale_in_cooldown_seconds       = var.search_service_scale_in_cooldown_seconds
  scale_out_cooldown_seconds      = var.search_service_scale_out_cooldown_seconds

  # IAM Security
  permissions_boundary_arn   = module.iam_security.permission_boundary_arn
  deny_guardrail_policy_json = module.iam_security.deny_guardrail_policy_json
  restrict_egress            = var.restrict_egress
  vpc_cidr                   = var.vpc_cidr

  tags = local.default_tags
}

module "search_service_lambda" {
  count  = var.search_runtime == "lambda" ? 1 : 0
  source = "../../modules/search_service_lambda"

  project                        = var.project
  environment                    = var.environment
  vpc_id                         = module.core_network.vpc_id
  subnet_ids                     = module.core_network.private_subnet_ids
  vector_store_endpoint          = local.vector_store_endpoint
  embedding_endpoint             = local.embedding_endpoint
  ingestion_queue_arn            = module.data_plane.ingestion_queue_arn
  reindex_topic_arn              = module.data_plane.reindex_topic_arn
  tags                           = local.default_tags
  container_image                = var.lambda_container_image
  lambda_architecture            = var.lambda_architecture
  timeout_seconds                = var.lambda_timeout_seconds
  memory_mb                      = var.lambda_memory_mb
  enable_ephemeral_storage       = var.lambda_enable_ephemeral_storage
  ephemeral_storage_mb           = var.lambda_ephemeral_storage_mb
  enable_provisioned_concurrency = var.lambda_enable_provisioned_concurrency
  provisioned_concurrency_count  = var.lambda_provisioned_concurrency_count
  log_level                      = var.lambda_log_level
  metrics_namespace              = var.lambda_metrics_namespace
  enable_request_tracing         = var.lambda_enable_request_tracing
  enable_query_logging           = var.lambda_enable_query_logging
  max_concurrent_queries         = var.lambda_max_concurrent_queries
  default_top_k                  = var.lambda_default_top_k
  max_top_k                      = var.lambda_max_top_k
  candidate_multiplier           = var.lambda_candidate_multiplier
  healthcheck_path               = var.lambda_healthcheck_path
  readiness_path                 = var.lambda_readiness_path
  environment_variables          = var.lambda_environment_variables
  secret_arn_values              = var.lambda_secret_arn_values
  log_retention_in_days          = var.lambda_log_retention_in_days
  api_gateway_timeout_ms         = var.lambda_api_gateway_timeout_ms
  api_gateway_stage              = var.lambda_api_gateway_stage
  xray_tracing_mode              = var.lambda_xray_tracing_mode
  alarm_throttle_threshold       = var.lambda_alarm_throttle_threshold
  additional_security_group_ids  = var.lambda_additional_security_group_ids

  # IAM Security
  permissions_boundary_arn   = module.iam_security.permission_boundary_arn
  deny_guardrail_policy_json = module.iam_security.deny_guardrail_policy_json
  restrict_egress            = var.restrict_egress
  vpc_cidr                   = var.vpc_cidr
}

locals {
  search_service_endpoint = (
    var.search_runtime == "fargate"
    ? module.search_service_fargate[0].endpoint
    : module.search_service_lambda[0].endpoint
  )

  search_service_name = (
    var.search_runtime == "fargate"
    ? module.search_service_fargate[0].service_name
    : module.search_service_lambda[0].function_name
  )

  search_service_metrics_source = local.search_service_name

  runtime_log_group_name = (
    var.search_runtime == "fargate"
    ? module.search_service_fargate[0].log_group_name
    : module.search_service_lambda[0].log_group_name
  )

  api_log_group_name = (
    var.search_runtime == "lambda"
    ? module.search_service_lambda[0].api_log_group_name
    : null
  )
}

# ---------------------------------------------------------------------------
# IAM Policy Attachments — bind dangling policies to runtime roles
# ---------------------------------------------------------------------------

# Fargate: Bedrock invoke policy → task role
resource "aws_iam_role_policy_attachment" "fargate_bedrock_invoke" {
  count      = var.search_runtime == "fargate" && var.embedding_backend == "bedrock" ? 1 : 0
  role       = module.search_service_fargate[0].task_role_arn
  policy_arn = module.embedding_bedrock[0].bedrock_invoke_policy_arn
}

# Fargate: Embedding S3 access policy → task role
resource "aws_iam_role_policy_attachment" "fargate_embedding_s3" {
  count      = var.search_runtime == "fargate" && var.embedding_backend == "bedrock" ? 1 : 0
  role       = module.search_service_fargate[0].task_role_arn
  policy_arn = module.embedding_bedrock[0].s3_access_policy_arn
}

# Fargate: FAISS index read policy → task role
resource "aws_iam_role_policy_attachment" "fargate_faiss_read" {
  count      = var.search_runtime == "fargate" && var.vector_store == "faiss" ? 1 : 0
  role       = module.search_service_fargate[0].task_role_arn
  policy_arn = module.vector_store_faiss[0].index_read_policy_arn
}

# Lambda: Bedrock invoke policy → Lambda role
resource "aws_iam_role_policy_attachment" "lambda_bedrock_invoke" {
  count      = var.search_runtime == "lambda" && var.embedding_backend == "bedrock" ? 1 : 0
  role       = module.search_service_lambda[0].role_name
  policy_arn = module.embedding_bedrock[0].bedrock_invoke_policy_arn
}

# Lambda: Embedding S3 access policy → Lambda role
resource "aws_iam_role_policy_attachment" "lambda_embedding_s3" {
  count      = var.search_runtime == "lambda" && var.embedding_backend == "bedrock" ? 1 : 0
  role       = module.search_service_lambda[0].role_name
  policy_arn = module.embedding_bedrock[0].s3_access_policy_arn
}

# Lambda: FAISS index read policy → Lambda role
resource "aws_iam_role_policy_attachment" "lambda_faiss_read" {
  count      = var.search_runtime == "lambda" && var.vector_store == "faiss" ? 1 : 0
  role       = module.search_service_lambda[0].role_name
  policy_arn = module.vector_store_faiss[0].index_read_policy_arn
}

module "observability" {
  source = "../../modules/observability"

  project     = var.project
  environment = var.environment
  tags        = local.default_tags
  metrics_sources = {
    ingestion_queue = module.data_plane.ingestion_queue_arn
    search_service  = local.search_service_metrics_source
  }
  log_group_names = merge(
    { runtime = local.runtime_log_group_name },
    local.api_log_group_name != null ? { api = local.api_log_group_name } : {}
  )

  # TODO: Extend with dashboards/alarms specific to embedding and vector store modules.
}

output "vpc_id" {
  description = "VPC identifier for the dev environment."
  value       = module.core_network.vpc_id
}

output "private_subnet_ids" {
  description = "List of private subnet IDs available to workloads."
  value       = module.core_network.private_subnet_ids
}

output "search_service_endpoint" {
  description = "Primary endpoint for the semantic search API."
  value       = local.search_service_endpoint
}

output "search_service_name" {
  description = "Identifier of the active search runtime (ECS service name or Lambda function name)."
  value       = local.search_service_name
}

output "search_service_runtime_log_group_name" {
  description = "CloudWatch Log Group capturing search runtime logs."
  value       = local.runtime_log_group_name
}

output "search_service_api_log_group_name" {
  description = "CloudWatch Log Group capturing API Gateway access logs when the Lambda runtime is selected."
  value       = local.api_log_group_name
}

output "embedding_backend" {
  description = "Embedding provider configured for this environment."
  value       = var.embedding_backend
}

output "vector_store_engine" {
  description = "Vector store engine configured for this environment."
  value       = var.vector_store
}

output "permission_boundary_arn" {
  description = "ARN of the IAM permission boundary attached to workload roles."
  value       = module.iam_security.permission_boundary_arn
}

output "kms_key_arn" {
  description = "ARN of the customer-managed KMS key (empty when KMS is disabled)."
  value       = module.iam_security.kms_key_arn
}

output "cloudtrail_arn" {
  description = "ARN of the CloudTrail trail (empty when CloudTrail is disabled)."
  value       = module.iam_security.cloudtrail_arn
}

variable "project" {
  type        = string
  description = "Project identifier used for naming and tagging (e.g., semantic-search)."
}

variable "environment" {
  type        = string
  description = "Deployment environment label."
  default     = "dev"
}

variable "aws_region" {
  type        = string
  description = "AWS region to deploy resources into."
  default     = "us-east-1"
}

variable "additional_tags" {
  type        = map(string)
  description = "Extra tags to merge into the default tag set."
  default     = {}
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block allocated to the VPC."
  default     = "10.42.0.0/16"
}

variable "default_az_count" {
  type        = number
  description = "Number of availability zones to span when explicit AZs are not provided."
  default     = 2
}

variable "enable_flow_logs" {
  type        = bool
  description = "Whether to enable VPC flow logs. Requires flow_log_destination_arn (and flow_log_iam_role_arn for CloudWatch Logs) when true."
  default     = false
}

variable "flow_log_destination_type" {
  type        = string
  description = "Destination type for VPC flow logs (cloud-watch-logs or s3)."
  default     = "cloud-watch-logs"
}

variable "flow_log_destination_arn" {
  type        = string
  description = "ARN for the log destination receiving flow logs. Required when enable_flow_logs is true."
  default     = ""
}

variable "flow_log_iam_role_arn" {
  type        = string
  description = "IAM role ARN used when delivering flow logs to CloudWatch."
  default     = ""
}

variable "ingestion_mode" {
  type        = string
  description = "Ingestion strategy for the environment: batch or stream."
  default     = "batch"

  validation {
    condition     = contains(["batch", "stream"], var.ingestion_mode)
    error_message = "ingestion_mode must be either \"batch\" or \"stream\"."
  }
}

variable "enable_step_functions" {
  type        = bool
  description = "Toggle provisioning of Step Functions orchestration."
  default     = false
}

variable "enable_dedupe_store" {
  type        = bool
  description = "Toggle provisioning of the DynamoDB deduplication table."
  default     = true
}

variable "bucket_lifecycle_days" {
  type        = number
  description = "Number of days before S3 objects transition to infrequent access."
  default     = 30
}

variable "search_service_additional_security_group_ids" {
  type        = list(string)
  description = "Additional security groups attached to the search service tasks."
  default     = []
}

variable "search_service_allowed_ingress_cidrs" {
  type        = list(string)
  description = "CIDR blocks permitted to access the search service load balancer."
  default     = ["0.0.0.0/0"]
}

variable "search_service_acm_certificate_arn" {
  type        = string
  description = "ARN of the ACM certificate for HTTPS listener on the search service ALB. Leave empty to skip HTTPS."
  default     = ""
}

variable "search_service_container_image" {
  type        = string
  description = "Container image URI for the semantic search runtime."
  default     = ""
}

variable "search_service_cpu" {
  type        = number
  description = "CPU units allocated to each Fargate task."
  default     = 1024
}

variable "search_service_memory" {
  type        = number
  description = "Memory (in MiB) allocated to each Fargate task."
  default     = 2048
}

variable "search_service_container_port" {
  type        = number
  description = "Container port exposed by the semantic search runtime."
  default     = 8080
}

variable "search_service_desired_count" {
  type        = number
  description = "Initial desired count for the search service tasks."
  default     = 2
}

variable "search_service_min_capacity" {
  type        = number
  description = "Minimum task count allowed by autoscaling."
  default     = 2
}

variable "search_service_max_capacity" {
  type        = number
  description = "Maximum task count allowed by autoscaling."
  default     = 6
}

variable "search_service_assign_public_ip" {
  type        = bool
  description = "Assign a public IP to the Fargate tasks."
  default     = false
}

variable "search_service_platform_version" {
  type        = string
  description = "Fargate platform version for the search service."
  default     = "LATEST"
}

variable "search_service_log_retention_in_days" {
  type        = number
  description = "CloudWatch Logs retention period for the search service."
  default     = 14
}

variable "search_service_environment_variables" {
  type        = map(string)
  description = "Additional plain-text environment variables for the search runtime."
  default     = {}
}

variable "search_service_secret_arn_values" {
  type        = map(string)
  description = "Mapping of environment variable names to Secrets Manager ARNs."
  default     = {}
}

variable "search_service_log_level" {
  type        = string
  description = "Default log level for the search runtime."
  default     = "INFO"
}

variable "search_service_metrics_namespace" {
  type        = string
  description = "Metrics namespace emitted by the search runtime."
  default     = "SemanticSearch/Runtime"
}

variable "search_service_enable_request_tracing" {
  type        = bool
  description = "Enable request-level tracing headers in the runtime."
  default     = false
}

variable "search_service_enable_query_logging" {
  type        = bool
  description = "Enable structured query logging in the runtime."
  default     = false
}

variable "search_service_max_concurrent_queries" {
  type        = number
  description = "Maximum concurrent queries processed by the runtime."
  default     = 100
}

variable "search_service_default_top_k" {
  type        = number
  description = "Default number of results returned per query."
  default     = 10
}

variable "search_service_max_top_k" {
  type        = number
  description = "Maximum number of results allowed per query."
  default     = 200
}

variable "search_service_candidate_multiplier" {
  type        = number
  description = "Candidate multiplier applied before post-query filtering."
  default     = 3
}

variable "search_service_healthcheck_path" {
  type        = string
  description = "Healthcheck endpoint path exposed by the runtime."
  default     = "/healthz"
}

variable "search_service_readiness_path" {
  type        = string
  description = "Readiness endpoint path exposed by the runtime."
  default     = "/readyz"
}

variable "search_service_healthcheck_interval_seconds" {
  type        = number
  description = "Interval between load balancer health checks."
  default     = 30
}

variable "search_service_healthcheck_timeout_seconds" {
  type        = number
  description = "Timeout for load balancer health checks."
  default     = 5
}

variable "search_service_healthcheck_healthy_threshold" {
  type        = number
  description = "Number of consecutive successes required for a target to be considered healthy."
  default     = 3
}

variable "search_service_healthcheck_unhealthy_threshold" {
  type        = number
  description = "Number of consecutive failures required for a target to be considered unhealthy."
  default     = 3
}

variable "search_service_alarm_http_5xx_threshold" {
  type        = number
  description = "Threshold of HTTP 5xx responses that triggers the CloudWatch alarm."
  default     = 5
}

variable "search_service_startup_timeout_seconds" {
  type        = number
  description = "Grace period before declaring the runtime unhealthy on startup."
  default     = 60
}

variable "search_service_shutdown_timeout_seconds" {
  type        = number
  description = "Grace period granted to the runtime during shutdown."
  default     = 30
}

variable "search_service_enable_request_based_scaling" {
  type        = bool
  description = "Enable ALB request-count-based autoscaling policy."
  default     = false
}

variable "search_service_autoscaling_cpu_target" {
  type        = number
  description = "Target CPU utilization percentage for autoscaling."
  default     = 60
}

variable "search_service_autoscaling_requests_per_target" {
  type        = number
  description = "Target number of requests per target when request-based scaling is enabled."
  default     = 50
}

variable "search_service_scale_in_cooldown_seconds" {
  type        = number
  description = "Cooldown period after a scale-in event."
  default     = 120
}

variable "search_service_scale_out_cooldown_seconds" {
  type        = number
  description = "Cooldown period after a scale-out event."
  default     = 60
}

variable "lambda_container_image" {
  type        = string
  description = "Container image URI for the Lambda search runtime."
  default     = ""
}

variable "lambda_architecture" {
  type        = string
  description = "CPU architecture for the Lambda function (x86_64 or arm64)."
  default     = "x86_64"

  validation {
    condition     = contains(["x86_64", "arm64"], lower(var.lambda_architecture))
    error_message = "lambda_architecture must be either \"x86_64\" or \"arm64\"."
  }
}

variable "lambda_timeout_seconds" {
  type        = number
  description = "Lambda function timeout in seconds."
  default     = 30
}

variable "lambda_memory_mb" {
  type        = number
  description = "Amount of memory (in MB) allocated to the Lambda function."
  default     = 1024
}

variable "lambda_enable_ephemeral_storage" {
  type        = bool
  description = "Enable custom ephemeral storage sizing for the Lambda runtime."
  default     = false
}

variable "lambda_ephemeral_storage_mb" {
  type        = number
  description = "Ephemeral storage size in MB when custom storage is enabled."
  default     = 1024
}

variable "lambda_enable_provisioned_concurrency" {
  type        = bool
  description = "Enable provisioned concurrency for predictable latency."
  default     = false
}

variable "lambda_provisioned_concurrency_count" {
  type        = number
  description = "Number of provisioned concurrent executions to maintain when enabled."
  default     = 2
}

variable "lambda_log_level" {
  type        = string
  description = "Default log level for the Lambda runtime."
  default     = "INFO"
}

variable "lambda_metrics_namespace" {
  type        = string
  description = "Metrics namespace emitted by the Lambda runtime."
  default     = "SemanticSearch/Runtime"
}

variable "lambda_enable_request_tracing" {
  type        = bool
  description = "Enable request-level tracing headers in the Lambda runtime."
  default     = false
}

variable "lambda_enable_query_logging" {
  type        = bool
  description = "Enable structured query logging in the Lambda runtime."
  default     = false
}

variable "lambda_max_concurrent_queries" {
  type        = number
  description = "Maximum concurrent queries processed by the Lambda runtime."
  default     = 100
}

variable "lambda_default_top_k" {
  type        = number
  description = "Default number of results returned per query."
  default     = 10
}

variable "lambda_max_top_k" {
  type        = number
  description = "Maximum number of results allowed per query."
  default     = 200
}

variable "lambda_candidate_multiplier" {
  type        = number
  description = "Candidate multiplier applied before post-query filtering."
  default     = 3
}

variable "lambda_healthcheck_path" {
  type        = string
  description = "Healthcheck endpoint path exposed by the Lambda runtime."
  default     = "/healthz"
}

variable "lambda_readiness_path" {
  type        = string
  description = "Readiness endpoint path exposed by the Lambda runtime."
  default     = "/readyz"
}

variable "lambda_environment_variables" {
  type        = map(string)
  description = "Additional plain-text environment variables for the Lambda runtime."
  default     = {}
}

variable "lambda_secret_arn_values" {
  type        = map(string)
  description = "Mapping of environment variable names to Secrets Manager ARNs for the Lambda runtime."
  default     = {}
}

variable "lambda_log_retention_in_days" {
  type        = number
  description = "CloudWatch Logs retention period for the Lambda runtime."
  default     = 14
}

variable "lambda_api_gateway_timeout_ms" {
  type        = number
  description = "Timeout (in milliseconds) for the API Gateway integration."
  default     = 29000
}

variable "lambda_api_gateway_stage" {
  type        = string
  description = "API Gateway stage name for the Lambda runtime."
  default     = "$default"
}

variable "lambda_xray_tracing_mode" {
  type        = string
  description = "X-Ray tracing mode for the Lambda function (PassThrough or Active)."
  default     = "PassThrough"

  validation {
    condition     = contains(["PassThrough", "Active"], var.lambda_xray_tracing_mode)
    error_message = "lambda_xray_tracing_mode must be either \"PassThrough\" or \"Active\"."
  }
}

variable "lambda_alarm_throttle_threshold" {
  type        = number
  description = "Threshold for Lambda throttles that triggers a CloudWatch alarm."
  default     = 1
}

variable "lambda_additional_security_group_ids" {
  type        = list(string)
  description = "Additional security groups attached to the Lambda ENIs."
  default     = []
}

variable "search_runtime" {
  type        = string
  description = "Runtime for the search service (fargate or lambda)."
  default     = "fargate"

  validation {
    condition     = contains(["fargate", "lambda"], var.search_runtime)
    error_message = "search_runtime must be either \"fargate\" or \"lambda\"."
  }
}

variable "embedding_backend" {
  type        = string
  description = "Embedding provider backend (bedrock, spot, sagemaker)."
  default     = "bedrock"

  validation {
    condition     = contains(["bedrock", "spot", "sagemaker"], var.embedding_backend)
    error_message = "embedding_backend must be one of \"bedrock\", \"spot\", or \"sagemaker\"."
  }
}

variable "vector_store" {
  type        = string
  description = "Vector store engine to provision (faiss, qdrant, pgvector)."
  default     = "faiss"

  validation {
    condition     = contains(["faiss", "qdrant", "pgvector"], var.vector_store)
    error_message = "vector_store must be one of \"faiss\", \"qdrant\", or \"pgvector\"."
  }
}

# ─── IAM Security ────────────────────────────────────────────────────────────

variable "enable_kms" {
  type        = bool
  description = "Provision a customer-managed KMS key for data-at-rest encryption."
  default     = true
}

variable "enable_cloudtrail" {
  type        = bool
  description = "Provision a CloudTrail trail for API audit logging."
  default     = true
}

variable "enable_cloudtrail_data_events" {
  type        = bool
  description = "Enable CloudTrail data-event logging for S3 and Lambda (higher cost)."
  default     = false
}

variable "enable_s3_endpoint" {
  type        = bool
  description = "Provision an S3 gateway VPC endpoint."
  default     = false
}

variable "enable_interface_endpoints" {
  type        = bool
  description = "Provision interface VPC endpoints for SQS, SNS, Bedrock, CW Logs, and ECR."
  default     = false
}

variable "restrict_egress" {
  type        = bool
  description = "Tighten security group egress to HTTPS-only to VPC CIDR (requires VPC endpoints for full connectivity)."
  default     = false
}
