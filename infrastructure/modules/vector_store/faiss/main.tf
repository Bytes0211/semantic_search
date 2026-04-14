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
  name_prefix  = "${var.project}-${var.environment}-faiss"
  store_prefix = "vector_store/current"
  common_tags = merge(
    {
      Project     = var.project
      Environment = var.environment
      Module      = "vector-store-faiss"
    },
    var.tags
  )
}

# ─── S3: FAISS index bucket ──────────────────────────────────────────────────
# The NumpyVectorStore is loaded from and serialised to this bucket.
# The search runtime reads VECTOR_STORE_PATH = the S3 URI output below.

resource "aws_s3_bucket" "index" {
  bucket        = "${local.name_prefix}-index"
  force_destroy = var.force_destroy_bucket
  tags          = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "index" {
  bucket                  = aws_s3_bucket.index.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "index" {
  bucket = aws_s3_bucket.index.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "index" {
  bucket = aws_s3_bucket.index.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "index" {
  bucket = aws_s3_bucket.index.id

  rule {
    id     = "expire-old-index-versions"
    status = "Enabled"

    filter {
      prefix = ""
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# ─── IAM: Read policy (search runtime) ──────────────────────────────────────

resource "aws_iam_policy" "index_read" {
  name        = "${local.name_prefix}-index-read"
  description = "Grants the search runtime read access to the FAISS vector index in S3."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadFaissIndex"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.index.arn,
          "${aws_s3_bucket.index.arn}/*"
        ]
      }
    ]
  })

  tags = local.common_tags
}

# ─── IAM: Write policy (embedding pipeline) ─────────────────────────────────

resource "aws_iam_policy" "index_write" {
  name        = "${local.name_prefix}-index-write"
  description = "Grants the embedding pipeline write access to publish a new FAISS index to S3."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "WriteFaissIndex"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:DeleteObject"]
        Resource = ["${aws_s3_bucket.index.arn}/*"]
      }
    ]
  })

  tags = local.common_tags
}
