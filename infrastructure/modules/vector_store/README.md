# Vector Store Modules

The vector store layer provides modular Terraform components for hosting semantic embeddings with multiple backends. Each submodule under this directory implements a consistent contract so environments can toggle between FAISS (self-managed), Qdrant, or pgvector without rewriting infrastructure code.

---

## Directory Layout

- `faiss/` — ECS/Fargate task definitions and storage wiring for FAISS-based ANN search.
- `qdrant/` — Managed or self-hosted Qdrant deployment, including configuration endpoints.
- `pgvector/` — Amazon RDS / Aurora PostgreSQL with the `pgvector` extension enabled.

Additional providers can be added by creating a new subdirectory that adheres to the shared interface.

---

## Shared Responsibilities

All vector store modules are expected to:

1. Accept networking inputs (VPC ID, subnet IDs, security groups) exported by `modules/core_network`.
2. Consume ingestion signals (queues, topics) exported by `modules/data_plane`.
3. Expose connection metadata (endpoint URLs, ports, secrets references) for the search runtime.
4. Emit observability hooks that the `modules/observability` stack can subscribe to.
5. Surface configuration variables for sizing, replication, backups, and cost tuning.

---

## Common Inputs (Recommended)

| Variable | Description |
| --- | --- |
| `project` | Project identifier for tagging. |
| `environment` | Environment label (dev, staging, prod). |
| `vpc_id` | Network where the service should run. |
| `subnet_ids` | Private subnet list for workloads. |
| `security_group_ids` | Security groups to attach to compute resources. |
| `ingestion_queue_arn` | SQS queue or equivalent for index refresh events. |
| `tags` | Additional tags merged into every resource. |

Each backend may add further inputs (e.g., instance size, storage capacity, managed service flags).

---

## Common Outputs (Recommended)

| Output | Description |
| --- | --- |
| `endpoint` | Primary connection endpoint/URL for the vector store. |
| `port` | Network port, when relevant. |
| `admin_role_arn` | IAM role or secret reference for administrative access. |
| `metrics_namespace` | Namespace used for observability integrations. |
| `index_refresh_queue_arn` | Re-exported queue for downstream modules, if applicable. |

Ensure outputs are kept stable so `environments/*` stacks can switch backends seamlessly.

---

## Alignment with Delivery Phases

- **Phase 0 — Planning & Alignment:** Document SLAs, data volume expectations, and compliance requirements per client.
- **Phase 1 — Foundation & Infrastructure:** Scaffold Terraform templates, variable definitions, and module READMEs (this file).
- **Phase 2 — Data Ingestion Layer:** Validate connectivity between ingestion pipelines and vector store write APIs.
- **Phase 3 — Embedding & Vector Services:** Implement provisioning logic and indexing automation pipelines.
- **Phase 4 — Search Runtime & Interfaces:** Expose connection details to runtime modules; ensure health checks and scaling policies are in place.
- **Phase 5 — Quality & Launch Readiness:** Run performance benchmarks, failover drills, and document operational runbooks.

---

## Next Steps

1. Populate each backend submodule with Terraform configurations and backend-specific READMEs.
2. Define example compositions demonstrating how to switch vector stores via variables in `environments/*`.
3. Add automated checks (e.g., `terraform validate`, unit tests via Terratest) to ensure interface compatibility.
4. Update `developer/project_status.md` as backend implementations progress through their respective phases.