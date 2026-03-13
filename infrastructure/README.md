# Semantic Search Platform — Infrastructure Overview

This directory contains the infrastructure-as-code foundation for the semantic search platform. The goal is to provide a modular, configurable Terraform layout that lets each engagement select the runtime, embedding provider, and ingestion mode that best matches its performance and cost targets.

---

## Directory Layout

```
infrastructure/
├── README.md                      # This overview
├── modules/                       # Reusable building blocks
│   ├── core_network/              # VPC, subnets, security groups
│   ├── data_plane/                # S3 buckets, queues, batch orchestration
│   ├── vector_store/              # FAISS (ECS), Qdrant, or pgvector
│   ├── search_service_fargate/    # ECS/Fargate deployment of the search API
│   ├── search_service_lambda/     # Lambda deployment of the search API
│   ├── embedding_bedrock/         # Bedrock access policies and configuration
│   ├── embedding_spot/            # Spot-backed open-source embedding stack
│   ├── embedding_sagemaker/       # SageMaker endpoint provisioning
│   ├── observability/             # CloudWatch dashboards, log retention, alarms
│   └── shared/                    # Cross-cutting resources and helpers
└── environments/                  # Stacks composed from modules (e.g. dev, prod, client-specific)
```

---

## Key Configuration Variables

The Terraform modules expose a small set of variables to keep deployments configurable without editing code:

- `var.search_runtime` — switch between `"fargate"` and `"lambda"` for the semantic search service.
- `var.embedding_backend` — select `"bedrock"`, `"spot"`, or `"sagemaker"` for embedding generation.
- `var.ingestion_mode` — `"batch"` (default) or `"stream"` for ingestion workflows.

**Runtime toggle (`var.search_runtime`)** — Select `"fargate"` when predictable low-latency workloads or long-lived connections are expected; select `"lambda"` to minimize idle cost for bursty or low-volume environments. Both runtimes consume the shared container image produced by the build pipeline and expose identical environment variables, so switching only requires updating the Terraform variable.

**Embedding toggle (`var.embedding_backend`)** — Choose `"bedrock"` for fully managed embeddings, `"spot"` for cost-optimized self-managed models, or `"sagemaker"` for managed endpoints with autoscaling. Each option maps to a dedicated Terraform submodule that emits consistent outputs (e.g., `endpoint`, `secret_arn`, `metrics_namespace`) consumed by ingestion jobs and the runtime.

**Ingestion toggle (`var.ingestion_mode`)** — The default `"batch"` mode provisions EventBridge schedules and SQS queues; switching to `"stream"` layers in streaming resources (e.g., Kinesis, Lambda consumers) for near-real-time updates while keeping downstream modules untouched.

Additional settings—instance sizes, autoscaling thresholds, retention periods—are surfaced through module-specific variables, keeping the top-level configuration focused on high-impact choices.

---

## Workflow

1. **Core Network First:** Compose the `core_network` module to establish the baseline VPC, subnets, and security boundaries.
2. **Data Plane & Shared Resources:** Layer in storage, queues, and shared IAM roles with the `data_plane` and `shared` modules.
3. **Embedding Provider:** Instantiate exactly one embedding module based on `var.embedding_backend`.
4. **Vector Store:** Provision the appropriate vector database module (FAISS/Qdrant/pgvector) to house embeddings.
5. **Search Runtime:** Toggle between `search_service_fargate` or `search_service_lambda` using `var.search_runtime`. Both expect the same container artifact.
6. **Observability:** Append monitoring defaults with the `observability` module to ensure metrics, logs, and alarms are consistent.
7. **Environment Composition:** The `environments/` directory contains Terraform stacks (e.g., `dev`, `prod`, `client-X`) that wire these modules together with environment-specific variables.

---

## Design Principles

- **Modularity:** Each capability is encapsulated in a dedicated module to encourage reuse and simplify onboarding of new clients or environments.
- **Configurable Deployment:** Clients can mix runtime and embedding choices without forking code, aligning with the technical approach documented in `developer/technical_approach.md`.
- **Cost Awareness:** Defaults favor batch ingestion, spot capacity for non-latency-critical workloads, and lifecycle policies for storage; all can be tuned via variables.
- **Observability by Default:** Metrics, logs, and alarms are included in every stack to support production readiness.
- **Documented Trade-offs:** Runtime and embedding module READMEs (to be authored) will outline latency, cost, and operational considerations that inform the Terraform toggles.

## Configuration Examples

The sample Terraform variable files below demonstrate how to flip deployment modes without touching module source code.

- **Cost-optimized baseline:** Lambda runtime + Bedrock embeddings + batch ingestion.
- **Low-latency production:** Fargate runtime + Spot-hosted embeddings + streaming ingestion.

```/dev/null/lambda_baseline.tfvars#L1-6
project           = "semantic-search"
environment       = "dev"
search_runtime    = "lambda"
embedding_backend = "bedrock"
ingestion_mode    = "batch"
vector_store      = "pgvector"
```

```/dev/null/fargate_streaming.tfvars#L1-7
project                = "semantic-search"
environment            = "prod"
search_runtime         = "fargate"
embedding_backend      = "spot"
ingestion_mode         = "stream"
vector_store           = "faiss"
enable_step_functions  = true
```

Adjust additional variables (for example, CPU/memory, lifecycle policies, or autoscaling thresholds) within the same files to fine-tune capacity and cost per environment.

---

## Next Steps

- Populate each module directory with Terraform code and module-level READMEs.
- Create baseline environment configurations (e.g., `environments/dev/main.tf`) demonstrating how to assemble modules.
- Integrate the infrastructure code into the CI/CD process once the module templates are finalized.