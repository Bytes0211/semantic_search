terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  name_prefix = "${var.project}-${var.environment}"
  account_id  = data.aws_caller_identity.current.account_id
  region      = data.aws_region.current.id

  common_tags = merge({
    Project     = var.project
    Environment = var.environment
    Module      = "iam-security"
  }, var.tags)

  # Flatten S3 bucket ARNs to include object-level paths.
  s3_resource_arns = flatten([
    for arn in var.s3_bucket_arns : [arn, "${arn}/*"]
  ])

  # KMS admin principals — fall back to the current caller when none are
  # supplied so the key is always manageable.
  effective_kms_admins = length(var.kms_admin_arns) > 0 ? var.kms_admin_arns : [
    "arn:aws:iam::${local.account_id}:root"
  ]
}

# ═════════════════════════════════════════════════════════════════════════════
# 1. PERMISSION BOUNDARY
# ═════════════════════════════════════════════════════════════════════════════
# A managed policy attached as a *permissions boundary* on every task / Lambda
# role. It caps the maximum effective permissions regardless of any inline or
# managed policies attached to the role.

resource "aws_iam_policy" "permission_boundary" {
  name        = "${local.name_prefix}-permission-boundary"
  description = "Permission boundary for ${var.project} ${var.environment} workload roles."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [

      # ── Allow: S3 operations scoped to project buckets ──────────────
      {
        Sid      = "AllowS3ProjectBuckets"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"]
        Resource = length(local.s3_resource_arns) > 0 ? local.s3_resource_arns : ["arn:aws:s3:::${local.name_prefix}-*"]
      },

      # ── Allow: SQS operations scoped to project queues ──────────────
      {
        Sid    = "AllowSQS"
        Effect = "Allow"
        Action = [
          "sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage",
          "sqs:GetQueueAttributes", "sqs:GetQueueUrl"
        ]
        Resource = length(var.sqs_queue_arns) > 0 ? var.sqs_queue_arns : ["arn:aws:sqs:${local.region}:${local.account_id}:${local.name_prefix}-*"]
      },

      # ── Allow: SNS publish scoped to project topics ─────────────────
      {
        Sid      = "AllowSNS"
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = length(var.sns_topic_arns) > 0 ? var.sns_topic_arns : ["arn:aws:sns:${local.region}:${local.account_id}:${local.name_prefix}-*"]
      },

      # ── Allow: Bedrock InvokeModel ──────────────────────────────────
      {
        Sid      = "AllowBedrock"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = var.bedrock_model_arns
      },

      # ── Allow: CloudWatch & X-Ray for observability ─────────────────
      {
        Sid    = "AllowObservability"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream", "logs:PutLogEvents",
          "cloudwatch:PutMetricData",
          "xray:PutTraceSegments", "xray:PutTelemetryRecords"
        ]
        Resource = "*"
      },

      # ── Allow: ECR image pulls ──────────────────────────────────────
      {
        Sid    = "AllowECRPull"
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage",
          "ecr:GetAuthorizationToken", "ecr:BatchCheckLayerAvailability"
        ]
        Resource = "*"
      },

      # ── Allow: KMS encrypt/decrypt (if key exists) ──────────────────
      {
        Sid    = "AllowKMS"
        Effect = "Allow"
        Action = [
          "kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey", "kms:GenerateDataKey*",
          "kms:DescribeKey", "kms:ReEncryptFrom", "kms:ReEncryptTo"
        ]
        Resource = var.enable_kms ? [aws_kms_key.this[0].arn] : ["*"]
      },

      # ── Allow: Secrets Manager read ─────────────────────────────────
      {
        Sid      = "AllowSecretsRead"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = ["arn:aws:secretsmanager:${local.region}:${local.account_id}:secret:${local.name_prefix}-*"]
      },

      # ── Deny: Dangerous / out-of-scope actions ─────────────────────
      {
        Sid    = "DenyDangerous"
        Effect = "Deny"
        Action = [
          "iam:CreateUser", "iam:CreateRole", "iam:DeleteRole",
          "iam:AttachRolePolicy", "iam:DetachRolePolicy",
          "iam:PutRolePolicy", "iam:DeleteRolePolicy",
          "iam:CreatePolicy", "iam:DeletePolicy",
          "iam:PutUserPolicy", "iam:AttachUserPolicy",
          "organizations:*",
          "s3:DeleteBucket", "s3:PutBucketPolicy",
          "ec2:RunInstances", "ec2:TerminateInstances",
          "ec2:CreateVpc", "ec2:DeleteVpc",
          "ec2:CreateSubnet", "ec2:DeleteSubnet"
        ]
        Resource = "*"
      }
    ]
  })

  tags = local.common_tags
}

# ═════════════════════════════════════════════════════════════════════════════
# 2. KMS CUSTOMER-MANAGED KEY
# ═════════════════════════════════════════════════════════════════════════════

resource "aws_kms_key" "this" {
  count               = var.enable_kms ? 1 : 0
  description         = "CMK for ${var.project} ${var.environment} — S3, SQS, SNS, CloudTrail encryption."
  enable_key_rotation = true
  deletion_window_in_days = var.kms_deletion_window_days

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Root account has full control (required for key manageability).
      {
        Sid       = "RootAccess"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${local.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      # Explicit admin principals.
      {
        Sid       = "KeyAdmins"
        Effect    = "Allow"
        Principal = { AWS = local.effective_kms_admins }
        Action = [
          "kms:Create*", "kms:Describe*", "kms:Enable*", "kms:List*",
          "kms:Put*", "kms:Update*", "kms:Revoke*", "kms:Disable*",
          "kms:Get*", "kms:Delete*", "kms:TagResource", "kms:UntagResource",
          "kms:ScheduleKeyDeletion", "kms:CancelKeyDeletion"
        ]
        Resource = "*"
      },
      # Key users (runtime roles, embedding pipeline roles).
      {
        Sid       = "KeyUsers"
        Effect    = "Allow"
        Principal = { AWS = length(var.kms_user_arns) > 0 ? var.kms_user_arns : ["arn:aws:iam::${local.account_id}:root"] }
        Action = [
          "kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey", "kms:GenerateDataKey*",
          "kms:DescribeKey", "kms:ReEncryptFrom", "kms:ReEncryptTo"
        ]
        Resource = "*"
      },
      # Allow CloudTrail to encrypt log files.
      {
        Sid       = "CloudTrailEncrypt"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = ["kms:GenerateDataKey*", "kms:DescribeKey"]
        Resource  = "*"
        Condition = {
          StringEquals = {
            "aws:SourceArn" = "arn:aws:cloudtrail:${local.region}:${local.account_id}:trail/${local.name_prefix}-trail"
          }
        }
      },
      # Allow S3/SQS/SNS service principals to use the key.
      {
        Sid       = "ServiceEncrypt"
        Effect    = "Allow"
        Principal = { Service = ["s3.amazonaws.com", "sqs.amazonaws.com", "sns.amazonaws.com"] }
        Action    = ["kms:GenerateDataKey*", "kms:Decrypt", "kms:DescribeKey"]
        Resource  = "*"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_kms_alias" "this" {
  count         = var.enable_kms ? 1 : 0
  name          = "alias/${local.name_prefix}-key"
  target_key_id = aws_kms_key.this[0].key_id
}

# ═════════════════════════════════════════════════════════════════════════════
# 3. CLOUDTRAIL
# ═════════════════════════════════════════════════════════════════════════════

# --- S3 bucket for CloudTrail logs ---

resource "aws_s3_bucket" "cloudtrail" {
  count         = var.enable_cloudtrail ? 1 : 0
  bucket        = "${local.name_prefix}-cloudtrail-logs"
  force_destroy = var.environment == "dev" ? true : false
  tags          = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "cloudtrail" {
  count                   = var.enable_cloudtrail ? 1 : 0
  bucket                  = aws_s3_bucket.cloudtrail[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cloudtrail" {
  count  = var.enable_cloudtrail ? 1 : 0
  bucket = aws_s3_bucket.cloudtrail[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.enable_kms ? "aws:kms" : "AES256"
      kms_master_key_id = var.enable_kms ? aws_kms_key.this[0].arn : null
    }
  }
}

resource "aws_s3_bucket_policy" "cloudtrail" {
  count  = var.enable_cloudtrail ? 1 : 0
  bucket = aws_s3_bucket.cloudtrail[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AWSCloudTrailAclCheck"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:GetBucketAcl"
        Resource  = aws_s3_bucket.cloudtrail[0].arn
        Condition = {
          StringEquals = {
            "aws:SourceArn" = "arn:aws:cloudtrail:${local.region}:${local.account_id}:trail/${local.name_prefix}-trail"
          }
        }
      },
      {
        Sid       = "AWSCloudTrailWrite"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.cloudtrail[0].arn}/AWSLogs/${local.account_id}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl" = "bucket-owner-full-control"
            "aws:SourceArn" = "arn:aws:cloudtrail:${local.region}:${local.account_id}:trail/${local.name_prefix}-trail"
          }
        }
      }
    ]
  })
}

# --- CloudWatch log group for CloudTrail (optional) ---

resource "aws_cloudwatch_log_group" "cloudtrail" {
  count             = var.enable_cloudtrail && var.cloudtrail_log_retention_days > 0 ? 1 : 0
  name              = "/aws/cloudtrail/${local.name_prefix}"
  retention_in_days = var.cloudtrail_log_retention_days
  tags              = local.common_tags
}

resource "aws_iam_role" "cloudtrail_cw" {
  count = var.enable_cloudtrail && var.cloudtrail_log_retention_days > 0 ? 1 : 0
  name  = "${local.name_prefix}-cloudtrail-cw-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudtrail.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "cloudtrail_cw" {
  count = var.enable_cloudtrail && var.cloudtrail_log_retention_days > 0 ? 1 : 0
  name  = "${local.name_prefix}-cloudtrail-cw"
  role  = aws_iam_role.cloudtrail_cw[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.cloudtrail[0].arn}:*"
    }]
  })
}

# --- Trail ---

resource "aws_cloudtrail" "this" {
  count = var.enable_cloudtrail ? 1 : 0

  name                       = "${local.name_prefix}-trail"
  s3_bucket_name             = aws_s3_bucket.cloudtrail[0].id
  include_global_service_events = true
  is_multi_region_trail      = false
  enable_log_file_validation = true
  kms_key_id                 = var.enable_kms ? aws_kms_key.this[0].arn : null

  cloud_watch_logs_group_arn = (
    var.cloudtrail_log_retention_days > 0
    ? "${aws_cloudwatch_log_group.cloudtrail[0].arn}:*"
    : null
  )
  cloud_watch_logs_role_arn = (
    var.cloudtrail_log_retention_days > 0
    ? aws_iam_role.cloudtrail_cw[0].arn
    : null
  )

  dynamic "event_selector" {
    for_each = var.enable_data_events ? [1] : []
    content {
      read_write_type           = "All"
      include_management_events = true

      data_resource {
        type   = "AWS::S3::Object"
        values = ["arn:aws:s3"]
      }
      data_resource {
        type   = "AWS::Lambda::Function"
        values = ["arn:aws:lambda"]
      }
    }
  }

  tags = local.common_tags

  depends_on = [
    aws_s3_bucket_policy.cloudtrail
  ]
}

# ═════════════════════════════════════════════════════════════════════════════
# 4. DENY-POLICY DOCUMENT (consumed by runtime modules)
# ═════════════════════════════════════════════════════════════════════════════
# Exported as a JSON string so Fargate / Lambda modules can attach it as an
# inline policy without duplicating the deny list.

locals {
  deny_guardrail_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenyPrivilegeEscalation"
        Effect = "Deny"
        Action = [
          "iam:CreateUser", "iam:CreateRole", "iam:DeleteRole",
          "iam:AttachRolePolicy", "iam:DetachRolePolicy",
          "iam:PutRolePolicy", "iam:DeleteRolePolicy",
          "iam:CreatePolicy", "iam:DeletePolicy",
          "iam:PutUserPolicy", "iam:AttachUserPolicy"
        ]
        Resource = "*"
      },
      {
        Sid    = "DenyBucketDestruction"
        Effect = "Deny"
        Action = ["s3:DeleteBucket", "s3:PutBucketPolicy"]
        Resource = "*"
      },
      {
        Sid    = "DenyInfraManagement"
        Effect = "Deny"
        Action = [
          "ec2:RunInstances", "ec2:TerminateInstances",
          "ec2:CreateVpc", "ec2:DeleteVpc",
          "ec2:CreateSubnet", "ec2:DeleteSubnet"
        ]
        Resource = "*"
      }
    ]
  })
}
