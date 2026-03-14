output "canonical_bucket_name" {
  description = "Name of the S3 bucket storing canonical records."
  value       = aws_s3_bucket.canonical.id
}

output "canonical_bucket_arn" {
  description = "ARN of the canonical records S3 bucket."
  value       = aws_s3_bucket.canonical.arn
}

output "embeddings_bucket_name" {
  description = "Name of the S3 bucket storing embedding artefacts."
  value       = aws_s3_bucket.embeddings.id
}

output "embeddings_bucket_arn" {
  description = "ARN of the embeddings S3 bucket."
  value       = aws_s3_bucket.embeddings.arn
}

output "ingestion_queue_arn" {
  description = "ARN of the SQS ingestion queue."
  value       = aws_sqs_queue.ingestion.arn
}

output "ingestion_queue_url" {
  description = "URL of the SQS ingestion queue."
  value       = aws_sqs_queue.ingestion.url
}

output "dead_letter_queue_arn" {
  description = "ARN of the SQS dead-letter queue receiving unprocessable ingestion messages."
  value       = aws_sqs_queue.ingestion_dlq.arn
}

output "reindex_topic_arn" {
  description = "ARN of the SNS topic used to broadcast reindex notifications."
  value       = aws_sns_topic.reindex.arn
}

output "dedupe_table_name" {
  description = "Name of the DynamoDB deduplication table. Empty string when enable_dedupe_store is false."
  value       = var.enable_dedupe_store ? aws_dynamodb_table.dedupe[0].name : ""
}

output "ingestion_stream_arn" {
  description = "ARN of the Kinesis ingestion stream. Empty string when ingestion_mode is 'batch'."
  value       = var.ingestion_mode == "stream" ? aws_kinesis_stream.ingestion[0].arn : ""
}
