# IAM Security Module

Centralises IAM security controls for the semantic search platform.

## Resources Provisioned

| Resource | Purpose |
|----------|---------|
| **Permission Boundary** | Managed IAM policy that caps the maximum effective permissions for any workload role (ECS task, Lambda). Scoped to project S3 buckets, SQS, SNS, Bedrock, CloudWatch, ECR, Secrets Manager, and KMS. Includes explicit deny statements for privilege escalation, bucket destruction, and infrastructure management. |
| **KMS Key** | Customer-managed key with automatic rotation. Key policy grants access to root, named admins, runtime roles, CloudTrail, and AWS service principals (S3, SQS, SNS). Gated by `enable_kms`. |
| **CloudTrail** | Management-event trail writing to a dedicated encrypted S3 bucket with log-file validation. Optional CloudWatch Logs delivery and data-event logging. Gated by `enable_cloudtrail`. |
| **Deny Guardrail Policy** | Exported JSON document for runtime modules to attach as an inline deny policy preventing privilege escalation, bucket destruction, and EC2 infrastructure operations. |

## Usage

```hcl
module "iam_security" {
  source = "../../modules/iam_security"

  project     = "semantic-search"
  environment = "dev"

  s3_bucket_arns = [
    module.data_plane.canonical_bucket_arn,
    module.data_plane.embeddings_bucket_arn,
    module.vector_store_faiss[0].index_bucket_arn,
  ]
  sqs_queue_arns = [module.data_plane.ingestion_queue_arn]
  sns_topic_arns = [module.data_plane.reindex_topic_arn]

  enable_kms        = true
  enable_cloudtrail = true
}
```

## Outputs

- `permission_boundary_arn` — attach to runtime IAM roles via `permissions_boundary`.
- `kms_key_arn` / `kms_key_id` — pass to data_plane and other modules for encryption.
- `cloudtrail_arn` / `cloudtrail_bucket_name` — for audit and compliance references.
- `deny_guardrail_policy_json` — JSON document for inline deny policies on runtime roles.
