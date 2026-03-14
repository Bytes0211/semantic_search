terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

locals {
  name_prefix = "${var.project}-${var.environment}"
  common_tags = merge(
    {
      Project     = var.project
      Environment = var.environment
      Module      = "data-plane"
    },
    var.tags
  )
}

# ─── S3: Canonical records bucket ────────────────────────────────────────────

resource "aws_s3_bucket" "canonical" {
  bucket        = "${local.name_prefix}-canonical-records"
  force_destroy = var.force_destroy_buckets
  tags          = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "canonical" {
  bucket                  = aws_s3_bucket.canonical.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "canonical" {
  bucket = aws_s3_bucket.canonical.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "canonical" {
  count  = var.bucket_lifecycle_days > 0 ? 1 : 0
  bucket = aws_s3_bucket.canonical.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    filter {
      prefix = ""
    }

    transition {
      days          = var.bucket_lifecycle_days
      storage_class = "STANDARD_IA"
    }
  }
}

# ─── S3: Embeddings bucket ───────────────────────────────────────────────────

resource "aws_s3_bucket" "embeddings" {
  bucket        = "${local.name_prefix}-embeddings"
  force_destroy = var.force_destroy_buckets
  tags          = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "embeddings" {
  bucket                  = aws_s3_bucket.embeddings.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "embeddings" {
  bucket = aws_s3_bucket.embeddings.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "embeddings" {
  bucket = aws_s3_bucket.embeddings.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "embeddings" {
  count  = var.bucket_lifecycle_days > 0 ? 1 : 0
  bucket = aws_s3_bucket.embeddings.id

  rule {
    id     = "expire-staging-artefacts"
    status = "Enabled"

    filter {
      prefix = "staging/"
    }

    transition {
      days          = var.bucket_lifecycle_days
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = var.bucket_lifecycle_days * 3
    }
  }

  rule {
    id     = "expire-old-versions"
    status = "Enabled"

    filter {
      prefix = ""
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# ─── SQS: Ingestion queue + DLQ ─────────────────────────────────────────────

resource "aws_sqs_queue" "ingestion_dlq" {
  name                      = "${local.name_prefix}-ingestion-dlq"
  message_retention_seconds = 1209600 # 14 days
  tags                      = local.common_tags
}

resource "aws_sqs_queue" "ingestion" {
  name                       = "${local.name_prefix}-ingestion"
  visibility_timeout_seconds = 300
  message_retention_seconds  = 86400 # 1 day

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ingestion_dlq.arn
    maxReceiveCount     = 3
  })

  tags = local.common_tags
}

# ─── SNS: Reindex notification topic ────────────────────────────────────────

resource "aws_sns_topic" "reindex" {
  name = "${local.name_prefix}-reindex"
  tags = local.common_tags
}

# ─── DynamoDB: Deduplication store (optional) ───────────────────────────────

resource "aws_dynamodb_table" "dedupe" {
  count        = var.enable_dedupe_store ? 1 : 0
  name         = "${local.name_prefix}-dedupe"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "record_id"

  attribute {
    name = "record_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = local.common_tags
}

# ─── Kinesis: Streaming ingestion (optional) ────────────────────────────────

resource "aws_kinesis_stream" "ingestion" {
  count            = var.ingestion_mode == "stream" ? 1 : 0
  name             = "${local.name_prefix}-ingestion-stream"
  shard_count      = var.kinesis_shard_count
  retention_period = 24

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  tags = local.common_tags
}
