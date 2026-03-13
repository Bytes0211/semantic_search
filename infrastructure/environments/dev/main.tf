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
  tags                      = local.default_tags
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
  tags                  = local.default_tags

  # TODO: Wire additional module-specific inputs (e.g., KMS keys, DLQ policies) as contracts are finalized.
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

  project               = var.project
  environment           = var.environment
  vpc_id                = module.core_network.vpc_id
  subnet_ids            = module.core_network.private_subnet_ids
  public_subnet_ids     = module.core_network.public_subnet_ids
  vector_store_endpoint = local.vector_store_endpoint
  embedding_endpoint    = local.embedding_endpoint
  ingestion_queue_arn   = module.data_plane.ingestion_queue_arn
  reindex_topic_arn     = module.data_plane.reindex_topic_arn
  tags                  = local.default_tags

  # TODO: Link to container image repository and runtime configuration once available.
}

module "search_service_lambda" {
  count  = var.search_runtime == "lambda" ? 1 : 0
  source = "../../modules/search_service_lambda"

  project               = var.project
  environment           = var.environment
  vpc_id                = module.core_network.vpc_id
  subnet_ids            = module.core_network.private_subnet_ids
  public_subnet_ids     = module.core_network.public_subnet_ids
  vector_store_endpoint = local.vector_store_endpoint
  embedding_endpoint    = local.embedding_endpoint
  ingestion_queue_arn   = module.data_plane.ingestion_queue_arn
  reindex_topic_arn     = module.data_plane.reindex_topic_arn
  tags                  = local.default_tags

  # TODO: Link to container image repository and runtime configuration once available.
}

locals {
  search_service_endpoint = (
    var.search_runtime == "fargate" ? module.search_service_fargate[0].endpoint :
    module.search_service_lambda[0].endpoint
  )

  search_service_name = (
    var.search_runtime == "fargate" ? module.search_service_fargate[0].service_name :
    module.search_service_lambda[0].service_name
  )
}

module "observability" {
  source = "../../modules/observability"

  project     = var.project
  environment = var.environment
  vpc_id      = module.core_network.vpc_id
  tags        = local.default_tags
  metrics_sources = {
    ingestion_queue = module.data_plane.ingestion_queue_arn
    search_service  = local.search_service_name
  }

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

output "embedding_backend" {
  description = "Embedding provider configured for this environment."
  value       = var.embedding_backend
}

output "vector_store_engine" {
  description = "Vector store engine configured for this environment."
  value       = var.vector_store
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
  description = "Whether to enable VPC flow logs."
  default     = true
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
