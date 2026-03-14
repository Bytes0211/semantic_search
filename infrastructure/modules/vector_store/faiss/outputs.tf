output "endpoint" {
  description = "S3 URI pointing to the active FAISS vector index. Injected into the search runtime as VECTOR_STORE_PATH."
  value       = "s3://${aws_s3_bucket.index.id}/${local.store_prefix}"
}

output "index_bucket_name" {
  description = "Name of the S3 bucket holding the FAISS index files."
  value       = aws_s3_bucket.index.id
}

output "index_bucket_arn" {
  description = "ARN of the S3 bucket holding the FAISS index files."
  value       = aws_s3_bucket.index.arn
}

output "index_read_policy_arn" {
  description = "IAM policy ARN granting read access to the FAISS index. Attach to the search runtime task role."
  value       = aws_iam_policy.index_read.arn
}

output "index_write_policy_arn" {
  description = "IAM policy ARN granting write access to the FAISS index. Attach to the embedding pipeline role."
  value       = aws_iam_policy.index_write.arn
}
