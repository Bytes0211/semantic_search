terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

data "aws_region" "current" {}

locals {
  name_prefix = "${var.project}-${var.environment}-bedrock"
  common_tags = merge(
    {
      Project     = var.project
      Environment = var.environment
      Module      = "embedding-bedrock"
    },
    var.tags
  )

  # Bedrock runtime endpoint for the current region.
  bedrock_endpoint = "https://bedrock-runtime.${data.aws_region.current.id}.amazonaws.com"
}

# ─── IAM: Bedrock InvokeModel policy ────────────────────────────────────────
# Attach this policy to the ECS task role or Lambda execution role that runs
# the embedding provider.

resource "aws_iam_policy" "bedrock_invoke" {
  name        = "${local.name_prefix}-invoke"
  description = "Grants bedrock:InvokeModel for the configured embedding model."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "BedrockInvokeModel"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:${data.aws_region.current.id}::foundation-model/${var.embedding_model_id}"
        ]
      }
    ]
  })

  tags = local.common_tags
}

# ─── IAM: S3 access for the embedding worker ────────────────────────────────
# Read canonical records; write embedding artefacts.

resource "aws_iam_policy" "s3_access" {
  name        = "${local.name_prefix}-s3"
  description = "Grants the embedding worker read access to canonical records and write access to the embeddings bucket."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadCanonical"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          "arn:aws:s3:::${var.canonical_bucket_name}",
          "arn:aws:s3:::${var.canonical_bucket_name}/*"
        ]
      },
      {
        Sid      = "WriteEmbeddings"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
        Resource = [
          "arn:aws:s3:::${var.embeddings_bucket_name}",
          "arn:aws:s3:::${var.embeddings_bucket_name}/*"
        ]
      }
    ]
  })

  tags = local.common_tags
}
