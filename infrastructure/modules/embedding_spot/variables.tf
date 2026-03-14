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
  description = "VPC identifier where embedding workers run."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for embedding worker placement."
}

variable "canonical_bucket_name" {
  type        = string
  description = "Name of the S3 bucket containing canonical source records."
}

variable "embeddings_bucket_name" {
  type        = string
  description = "Name of the S3 bucket where embedding artefacts are written."
}

variable "reindex_topic_arn" {
  type        = string
  description = "ARN of the SNS reindex notification topic."
}
