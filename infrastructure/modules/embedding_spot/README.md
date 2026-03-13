# Spot-Hosted Embedding Module

This module provisions the infrastructure required to run open-source embedding models on spot compute capacity. It is intentionally lightweight, capturing inputs/outputs and responsibilities so the Terraform implementation can be filled in during Phase 3.

---

## Responsibilities

- Launch containerized embedding workers (e.g., SentenceTransformers) on spot instances or spot-backed Fargate tasks.
- Configure autoscaling policies and interruption handling (checkpointing, graceful shutdown).
- Expose network endpoints or queue subscriptions for batch embedding jobs.
- Manage IAM roles, security groups, and access to S3 checkpoints or model artifacts.
- Publish observability signals (invocation counts, latency, interruption metrics) to the shared monitoring stack.

---

## Expected Inputs

| Variable | Description |
| --- | --- |
| `project` | Project identifier for tagging/naming. |
| `environment` | Deployment environment label (dev/staging/prod). |
| `vpc_id` | VPC where the workers run. |
| `subnet_ids` | Private subnets for worker placement. |
| `container_image` | Embedding model container image URI. |
| `spot_instance_types` | Preferred instance types for spot capacity. |
| `checkpoint_bucket` | S3 bucket for model weights and checkpoints. |
| `scaling_config` | Autoscaling thresholds (min/max tasks, CPU/memory targets). |
| `tags` | Additional resource tags. |

---

## Expected Outputs

| Output | Description |
| --- | --- |
| `endpoint` | Network endpoint or queue ARN used by embedding jobs. |
| `task_role_arn` | IAM role assumed by embedding workers. |
| `execution_role_arn` | IAM role for pulling images/logging. |
| `log_group_name` | CloudWatch log group for worker logs. |
| `metrics_namespace` | Namespace for emitted metrics. |

---

## Phase Alignment

- **Phase 3**: Implement this module alongside the embedding provider adapters, wiring configuration through `var.embedding_backend = "spot"`.
- **Phase 4**: Ensure the search runtime and ingestion pipelines can resolve the spot-hosted endpoint via module outputs.
- **Phase 5**: Validate interruption handling, scaling, and cost efficiency before go-live.

---

## Next Steps

1. Implement Terraform resources: spot-capable compute (ECS/Fargate/ASG), autoscaling, IAM, networking.
2. Integrate checkpoint sync mechanisms (S3 events or startup scripts).
3. Wire outputs into the embedding factory configuration consumed by the runtime.
4. Document operational runbooks (interrupt handling, scaling tuning, cost monitoring).