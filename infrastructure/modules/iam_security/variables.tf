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

# ─── Permission Boundary ─────────────────────────────────────────────────────

variable "s3_bucket_arns" {
  type        = list(string)
  description = "List of S3 bucket ARNs the permission boundary should grant access to."
  default     = []
}

variable "sqs_queue_arns" {
  type        = list(string)
  description = "List of SQS queue ARNs the permission boundary should grant access to."
  default     = []
}

variable "sns_topic_arns" {
  type        = list(string)
  description = "List of SNS topic ARNs the permission boundary should grant access to."
  default     = []
}

variable "bedrock_model_arns" {
  type        = list(string)
  description = "List of Bedrock foundation model ARNs the boundary should allow InvokeModel on."
  default     = ["arn:aws:bedrock:*::foundation-model/*"]
}

# ─── KMS ─────────────────────────────────────────────────────────────────────

variable "enable_kms" {
  type        = bool
  description = "Provision a customer-managed KMS key for encryption of S3, SQS, SNS, and CloudTrail."
  default     = true
}

variable "kms_admin_arns" {
  type        = list(string)
  description = "IAM principal ARNs granted KMS key administration (key policy). Typically the Terraform executor or CI role."
  default     = []
}

variable "kms_user_arns" {
  type        = list(string)
  description = "IAM principal ARNs granted encrypt/decrypt usage of the KMS key."
  default     = []
}

variable "kms_deletion_window_days" {
  type        = number
  description = "Waiting period (in days) before a deleted KMS key is permanently removed."
  default     = 14

  validation {
    condition     = var.kms_deletion_window_days >= 7 && var.kms_deletion_window_days <= 30
    error_message = "kms_deletion_window_days must be between 7 and 30."
  }
}

# ─── CloudTrail ──────────────────────────────────────────────────────────────

variable "enable_cloudtrail" {
  type        = bool
  description = "Provision a CloudTrail trail logging management events."
  default     = true
}

variable "enable_data_events" {
  type        = bool
  description = "Enable CloudTrail data-event logging for S3 and Lambda (higher cost)."
  default     = false
}

variable "cloudtrail_log_retention_days" {
  type        = number
  description = "Retention in days for the CloudTrail CloudWatch log group. Set to 0 to skip CW log group creation."
  default     = 90
}
