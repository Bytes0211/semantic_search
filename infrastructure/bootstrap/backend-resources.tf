# Bootstrap resources for Terraform remote state
#
# This creates the S3 bucket and DynamoDB table needed for remote state management.
# Run this ONCE before initializing the main dev environment:
#
#   cd infrastructure/bootstrap
#   terraform init
#   terraform apply
#
# After these resources exist, you can initialize the dev environment with remote state.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region for backend resources"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name (used in resource naming)"
  type        = string
  default     = "semantic-search"
}

variable "environment" {
  description = "Environment name (used in resource naming)"
  type        = string
  default     = "dev"
}

# S3 bucket for Terraform state
resource "aws_s3_bucket" "terraform_state" {
  bucket = "${var.project}-${var.environment}-terraform-state"

  tags = {
    Name        = "${var.project}-${var.environment}-terraform-state"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
    Purpose     = "terraform-state"
  }
}

# Enable versioning for state history and recovery
resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Enable server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block public access
resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# DynamoDB table for state locking
resource "aws_dynamodb_table" "terraform_locks" {
  name         = "${var.project}-${var.environment}-terraform-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Name        = "${var.project}-${var.environment}-terraform-locks"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
    Purpose     = "terraform-state-locking"
  }
}

# Outputs for verification
output "state_bucket_name" {
  description = "S3 bucket name for Terraform state"
  value       = aws_s3_bucket.terraform_state.id
}

output "state_bucket_arn" {
  description = "ARN of the S3 state bucket"
  value       = aws_s3_bucket.terraform_state.arn
}

output "dynamodb_table_name" {
  description = "DynamoDB table name for state locking"
  value       = aws_dynamodb_table.terraform_locks.id
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB locks table"
  value       = aws_dynamodb_table.terraform_locks.arn
}
