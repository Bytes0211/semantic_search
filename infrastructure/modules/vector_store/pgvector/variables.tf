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
  description = "VPC identifier for the RDS/pgvector instance."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for RDS instance placement."
}

variable "security_group_ids" {
  type        = list(string)
  description = "Security group IDs attached to the RDS instance."
  default     = []
}

variable "ingestion_queue_arn" {
  type        = string
  description = "ARN of the SQS ingestion queue."
}
