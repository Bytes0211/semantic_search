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
  description = "VPC identifier for the Qdrant deployment."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for Qdrant instance placement."
}

variable "security_group_ids" {
  type        = list(string)
  description = "Security group IDs attached to the Qdrant deployment."
  default     = []
}

variable "ingestion_queue_arn" {
  type        = string
  description = "ARN of the SQS ingestion queue."
}
