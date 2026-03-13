# Cost Optimisation Guide

Practical guidance for keeping the semantic search deployment cost-efficient
at each tier of the stack.

---

## 1. Compute Sizing

### Fargate (search runtime)

The search runtime is CPU-bound only during embedding generation; otherwise it
is largely memory-bound (in-process FAISS index).

**Recommended starting points:**

| Traffic tier | CPU | Memory | Expected cost (us-east-1, 2025) |
|---|---|---|---|
| Development / low traffic | 0.5 vCPU | 1 024 MiB | ~$15 / month (1 task) |
| Moderate (< 50 RPS) | 1 vCPU | 2 048 MiB | ~$55 / month (2 tasks) |
| High (50–200 RPS) | 2 vCPU | 4 096 MiB | ~$130 / month (2 tasks) |

Enable autoscaling (`enable_request_based_scaling = true`) and tune
`autoscaling_cpu_target` (default 60 %) so that tasks scale out before
hitting memory pressure.

Set `min_capacity = 0` only for non-production environments; keep it ≥ 2 in
production to avoid cold-start latency spikes during scale-from-zero.

### Lambda (search runtime)

Cold starts dominate cost and latency for Lambda deployments.

- Use **provisioned concurrency** (`enable_provisioned_concurrency = true`,
  `provisioned_concurrency_count = 2`) for production to eliminate cold-start
  tail latency.  Provisioned concurrency is priced separately; evaluate
  break-even against Fargate at your request rate.
- Set `memory_mb` to **1 024 MiB** minimum.  The NumPy vector index loads
  entirely into memory; under-provisioning causes OOM and cold-start
  amplification.
- Use **ARM64** (`lambda_architecture = "arm64"`) for a ~20 % cost reduction
  at equivalent performance.

---

## 2. Spot Strategy for Embedding Jobs

The embedding pipeline (ingestion + index build) is the most compute-intensive
workload and is well-suited for AWS Spot.

**Recommended pattern:**

- Submit ingestion jobs as **ECS Fargate Spot** tasks.  Configure
  `capacity_provider_strategy` with `weight = 1` for `FARGATE_SPOT` and a
  `base = 1` fallback to `FARGATE` to handle Spot interruptions gracefully.
- Set `spot_instance_draining = true` on the ECS capacity provider so that
  in-flight embedding batches are checkpointed before the task is reclaimed.
- Design the ingestion worker to be **idempotent**: use the S3 backup path
  (the `two-phase backup` in `EmbeddingPipeline`) so a partially completed
  batch can resume without re-embedding already-processed records.
- Expected savings: **60–80 %** compared to on-demand Fargate for batch
  workloads.

For SageMaker embedding endpoints:
- Use **asynchronous inference** (`sagemaker_async_inference`) for
  bulk ingestion instead of real-time endpoints.  Async endpoints scale to
  zero when idle, eliminating the minimum hourly charge of real-time endpoints.

---

## 3. S3 Lifecycle Rules

The vector store backup and intermediate embedding artefacts accumulate in S3.
Apply lifecycle rules to control storage costs.

**Recommended rules (configure via `aws_s3_bucket_lifecycle_configuration`):**

| Prefix | Action | After |
|---|---|---|
| `embeddings/staging/` | Transition to S3 Intelligent-Tiering | 30 days |
| `embeddings/staging/` | Expire | 90 days |
| `vector_store/snapshots/` | Transition to S3 Glacier Instant Retrieval | 60 days |
| `vector_store/snapshots/` | Expire | 365 days |
| `logs/` | Expire | 30 days |

For the active vector store artefact (`vector_store/current/`) do **not** add
an expiry rule; data loss here requires a full re-ingestion.

Enable **S3 Intelligent-Tiering** on buckets with unpredictable access
patterns to automatically move objects between Frequent and Infrequent Access
tiers without retrieval charges.

---

## 4. Provisioned Concurrency Guidance

Use provisioned concurrency on the Lambda deployment when:

1. P99 latency requirements are strict (< 500 ms) and cold starts exceed
   that budget.
2. Traffic is bursty but predictable (e.g. business-hours spikes).

**Schedule-based scaling** (Application Auto Scaling scheduled actions) is
more cost-efficient than always-on provisioned concurrency:

```hcl
# Example: scale up at 08:00 UTC, down at 20:00 UTC weekdays
resource "aws_appautoscaling_scheduled_action" "warm_up" {
  name               = "warm-up-business-hours"
  resource_id        = "function:${aws_lambda_function.search.function_name}:${aws_lambda_alias.live.name}"
  scalable_dimension = "lambda:function:ProvisionedConcurrency"
  service_namespace  = "lambda"
  schedule           = "cron(0 8 ? * MON-FRI *)"
  scalable_target_action {
    min_capacity = 2
    max_capacity = 5
  }
}
```

For Fargate, disable `desired_count` in off-hours using scheduled ECS scaling
to `min_capacity = 0` (dev/staging only).

---

## 5. Alarm Threshold Calibration

Poorly calibrated alarms produce alert fatigue and inflate on-call costs.
Calibrate thresholds against real baseline data before going to production.

**General approach:**

1. Run a 24-hour load test at expected peak traffic.
2. Record P50, P95, and P99 latency; record error rate.
3. Set alarm thresholds at **2× observed P95 latency** and **5× observed
   error rate** to allow headroom without drowning in noise.

**Module defaults (adjust via `alarm_thresholds` variable):**

| Alarm | Default threshold | Calibration note |
|---|---|---|
| `search_latency_p95` | _not set_ | Set to 2× your measured P95 at peak load |
| `search_error_rate` | _not set_ | Set to 5× normal error rate, minimum 0.5 % |
| `lambda_throttles` | 1 (per minute) | Raise to 5–10 for high-burst workloads |
| `ecs_unhealthy_host_count` | _not set_ | Set to 1 for ≥ 2 desired tasks |

Use `notification_topic_arn` to route alarms to an SNS topic that fans out
to PagerDuty, Slack, or email.

---

## 6. Additional Quick Wins

- **CloudWatch Log retention**: set `log_retention_in_days` to 7–14 for
  development and 30 for production.  Logs are often the largest unexplained
  cost item.
- **Data transfer**: deploy the search runtime in the same region as the
  primary data consumers.  Cross-region data transfer costs accumulate quickly
  at high query rates.
- **ECR image scanning**: enable `scan_on_push` but avoid running image scans
  on every CI push to a non-production repository.  Scans are charged per
  image layer.
- **Cost Allocation Tags**: use the `tags` variable (`project`,
  `environment`) consistently across all modules so AWS Cost Explorer can
  show per-environment spend.
