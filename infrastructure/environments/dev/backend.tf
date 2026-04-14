# Remote state backend configuration
# 
# This file configures S3 for state storage and DynamoDB for state locking.
# The backend resources (S3 bucket and DynamoDB table) must be created
# before running `terraform init`. See infrastructure/README.md for bootstrap steps.

terraform {
  backend "s3" {
    # S3 bucket for state storage
    # Format: <project>-<environment>-terraform-state
    bucket = "semantic-search-dev-terraform-state"

    # State file path within the bucket
    key = "dev/terraform.tfstate"

    # AWS region (must match your resources)
    region = "us-east-1"

    # DynamoDB table for state locking
    # Format: <project>-<environment>-terraform-locks
    dynamodb_table = "semantic-search-dev-terraform-locks"

    # Enable encryption at rest
    encrypt = true

    # Prevent accidental deletion of state files
    # Note: This is a best practice but requires the bucket to have versioning enabled
    # versioning is configured during bootstrap
  }
}
