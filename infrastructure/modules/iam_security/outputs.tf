output "permission_boundary_arn" {
  description = "ARN of the IAM permission boundary policy. Attach to workload roles via permissions_boundary."
  value       = aws_iam_policy.permission_boundary.arn
}

output "kms_key_arn" {
  description = "ARN of the customer-managed KMS key. Empty string when enable_kms is false."
  value       = var.enable_kms ? aws_kms_key.this[0].arn : ""
}

output "kms_key_id" {
  description = "ID of the customer-managed KMS key. Empty string when enable_kms is false."
  value       = var.enable_kms ? aws_kms_key.this[0].key_id : ""
}

output "cloudtrail_arn" {
  description = "ARN of the CloudTrail trail. Empty string when enable_cloudtrail is false."
  value       = var.enable_cloudtrail ? aws_cloudtrail.this[0].arn : ""
}

output "cloudtrail_bucket_name" {
  description = "Name of the S3 bucket storing CloudTrail logs. Empty string when enable_cloudtrail is false."
  value       = var.enable_cloudtrail ? aws_s3_bucket.cloudtrail[0].id : ""
}

output "deny_guardrail_policy_json" {
  description = "JSON policy document containing deny-based guardrails. Attach as an inline policy to runtime roles."
  value       = local.deny_guardrail_policy
}
