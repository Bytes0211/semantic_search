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
  description = "VPC identifier (reserved for future VPC-scoped access policies)."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subnet IDs (reserved for future VPC-scoped deployments)."
}

variable "security_group_ids" {
  type        = list(string)
  description = "Security group IDs (reserved for future VPC endpoint attachment)."
  default     = []
}

variable "ingestion_queue_arn" {
  type        = string
  description = "ARN of the SQS ingestion queue (used to scope IAM access if needed)."
}

variable "force_destroy_bucket" {
  type        = bool
  description = "Allow Terraform to destroy the index bucket even when non-empty. Use true only in dev/ephemeral environments."
  default     = false
}
