output "endpoint" {
  description = "Bedrock runtime endpoint URL for the current region. Injected into the search runtime as EMBEDDING_ENDPOINT."
  value       = local.bedrock_endpoint
}

output "bedrock_invoke_policy_arn" {
  description = "ARN of the IAM policy granting bedrock:InvokeModel. Attach to the ECS task role or Lambda execution role."
  value       = aws_iam_policy.bedrock_invoke.arn
}

output "s3_access_policy_arn" {
  description = "ARN of the IAM policy granting read access to canonical records and write access to the embeddings bucket."
  value       = aws_iam_policy.s3_access.arn
}
