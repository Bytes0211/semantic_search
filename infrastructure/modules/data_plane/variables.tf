variable "project" {
  type        = string
  description = "Project identifier used for naming and tagging resources."
}

variable "environment" {
  type        = string
  description = "Deployment environment label (e.g., dev, staging, prod)."
}

variable "tags" {
  type        = map(string)
  description = "Additional tags merged into every resource managed by this module."
  default     = {}
}

variable "vpc_id" {
  type        = string
  description = "VPC identifier for resources that require VPC placement."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs available to VPC-placed resources."
}

variable "ingestion_mode" {
  type        = string
  description = "Ingestion strategy: 'batch' (default) or 'stream' (provisions Kinesis)."
  default     = "batch"

  validation {
    condition     = contains(["batch", "stream"], var.ingestion_mode)
    error_message = "ingestion_mode must be either \"batch\" or \"stream\"."
  }
}

variable "enable_step_functions" {
  type        = bool
  description = "Toggle to provision Step Functions orchestration hooks."
  default     = false
}

variable "enable_dedupe_store" {
  type        = bool
  description = "Toggle to provision the DynamoDB deduplication table."
  default     = true
}

variable "bucket_lifecycle_days" {
  type        = number
  description = "Days before S3 objects transition to Infrequent Access storage. Set to 0 to disable lifecycle rules."
  default     = 30

  validation {
    condition     = var.bucket_lifecycle_days >= 0
    error_message = "bucket_lifecycle_days must be a non-negative integer."
  }
}

variable "force_destroy_buckets" {
  type        = bool
  description = "Allow Terraform to destroy non-empty S3 buckets. Use true only for dev/ephemeral environments."
  default     = false
}

variable "kinesis_shard_count" {
  type        = number
  description = "Number of Kinesis shards provisioned when ingestion_mode is 'stream'."
  default     = 1

  validation {
    condition     = var.kinesis_shard_count >= 1
    error_message = "kinesis_shard_count must be at least 1."
  }
}
