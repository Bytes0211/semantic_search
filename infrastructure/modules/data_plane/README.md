# Data Plane Module

The data plane module provisions the storage, messaging, and orchestration resources that power ingestion, embedding, and retrieval workflows for the semantic search platform. It is designed to stay modular so you can activate only the components a client engagement needs while keeping Terraform state clean and reusable.

---

## Responsibilities

- **Object Storage (S3):** canonical record store, embedding backups, intermediate artifacts.
- **Queueing & Pub/Sub:** Amazon SQS/SNS topics for ingestion pipelines, reindex triggers, optional fan-out to downstream systems.
- **Batch Orchestration:** EventBridge schedules or Step Functions hooks that coordinate ingestion and embedding jobs.
- **Metadata Stores:** DynamoDB tables (or equivalent) for pipeline checkpoints, deduplication, and job status.
- **IAM & Secrets Glue:** roles, policies, and secret references shared by data movers, embedding workers, and search services.

---

## How It Fits

1. `core_network` creates the VPC, subnets, and route tables.
2. This module runs next, wiring storage and queues into the network and exporting ARNs/URLs to higher layers.
3. `embedding_*` and `vector_store` modules subscribe to outputs from here (e.g., bucket names, queue ARNs) to hydrate their jobs.
4. `search_service_*` modules use the same queues/topics for reindex signals and read data-plane outputs (e.g., canonical S3 prefixes).

---

## Deployment Modes

| Scenario | Components Enabled | Notes |
| --- | --- | --- |
| **Batch Ingestion (default)** | S3 buckets, ingestion queues, EventBridge schedules | Keeps cost low; aligns with `var.ingestion_mode = "batch"` |
| **Streaming Ingestion** | Adds Kinesis/Data Streams, Lambda consumers | Enabled when `var.ingestion_mode = "stream"` |
| **Reindex-Only** | Shared buckets + control plane topics | Useful for read-only sandboxes or mirroring into staging |
| **Full Production** | All of the above plus DLQs, alarms, and dedupe tables | Recommended for environments subject to SLAs |

---

## Key Terraform Inputs

| Variable | Description | Default |
| --- | --- | --- |
| `project` | Project slug used for naming/tagging | n/a |
| `environment` | Deployment environment (`dev`, `prod`, etc.) | n/a |
| `ingestion_mode` | `"batch"` or `"stream"` | `"batch"` |
| `enable_step_functions` | Toggle to provision orchestration hooks | `false` |
| `enable_dedupe_store` | Creates DynamoDB table for deduplication | `true` |
| `bucket_lifecycle_days` | Days before moving data to infrequent-access storage | `30` |

> Refer to the module’s `variables.tf` (to be committed) for the complete list.

---

## Outputs Consumed Downstream

- `canonical_bucket_name`
- `embeddings_bucket_name`
- `ingestion_queue_arn` / `dead_letter_queue_arn`
- `reindex_topic_arn`
- `dedupe_table_name`
- `ingestion_schedule_arn` (when EventBridge enabled)

These outputs are consumed by embedding jobs, vector store provisioning, and runtime services as described in `developer/technical_approach.md`.

---

## Phase Checklist

### Phase 0 — Planning & Alignment
- Document data retention requirements and cost ceilings per client.
- Identify ingestion sources (CSV/SQL/JSON/API) and throughput expectations.

### Phase 1 — Foundation & Infrastructure
- Scaffold Terraform files (`main.tf`, `variables.tf`, `outputs.tf`, locals/helpers).
- Define tags, naming conventions, and lifecycle policies consistent with `core_network`.

### Phase 2 — Data Ingestion Layer
- Implement batch connectors leveraging the queues/schedules created here.
- Capture logging and metrics requirements (S3 access, queue depth, DLQ alarms).

### Phase 3 — Embedding & Vector Services
- Ensure embedding workers can read/write the buckets and publish to topics.
- Configure IAM roles/policies via this module’s outputs.

### Phase 4 — Search Runtime & Interfaces
- Wire reindex signals from runtime to `reindex_topic_arn`.
- Grant API servers read access to canonical/embedding buckets for troubleshooting.

### Phase 5 — Quality & Launch Readiness
- Validate lifecycle transitions, DLQ draining process, and backfill procedures.
- Produce runbooks referencing bucket layouts and queue/topic semantics.

---

## Implementation Notes

- **Tagging:** Apply tags aligned with `project`, `environment`, and `Module = data-plane` for cost attribution.
- **Security:** Buckets default to private with S3 Block Public Access and encryption enabled. Queue/topic policies should enforce VPC or IAM principal restrictions.
- **Observability:** Export CloudWatch metrics for queue depth, failed events, and scheduled run status. The `observability` module consumes these metrics for dashboards/detectors.
- **Extensibility:** Additional connectors (e.g., Glue jobs, Lake Formation permissions) should integrate through this module to avoid scattering data primitives across stacks.

---

## Next Steps

1. Commit Terraform code for the module, including optional resources toggled by inputs.
2. Author `examples/` showing how to instantiate the module for batch vs. streaming modes.
3. Update environment stacks (`infrastructure/environments/*`) to demonstrate composition with `core_network` and `observability`.
4. Align documentation with `developer/project_status.md` as Phase 1 tasks complete.

For architectural context and design rationale, consult `docs/PRD-semantic-search.md`, `developer/technical_approach.md`, and `AGENTS.md`.