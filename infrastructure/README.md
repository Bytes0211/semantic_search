# Semantic Search Platform — Infrastructure Overview

This directory contains the infrastructure-as-code foundation for the semantic search platform. The goal is to provide a modular, configurable Terraform layout that lets each engagement select the runtime, embedding provider, and ingestion mode that best matches its performance and cost targets.

---

## Directory Layout

```
infrastructure/
├── README.md                      # This overview
├── bootstrap/                     # One-time backend resources (S3 + DynamoDB)
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

## Remote State Backend

All environments use **S3 + DynamoDB** for remote state storage and locking to enable team collaboration and prevent state corruption.

### Bootstrap Process (One-Time Setup)

Before initializing any environment for the first time, create the backend resources:

```bash
cd infrastructure/bootstrap
terraform init
terraform apply
```

This creates:
- **S3 bucket** (`semantic-search-dev-terraform-state`) — stores Terraform state with versioning and encryption
- **DynamoDB table** (`semantic-search-dev-terraform-locks`) — provides state locking to prevent concurrent modifications

The bootstrap configuration is intentionally minimal and uses local state. After the backend resources exist, all other environments use remote state.

### Initializing an Environment

Once the bootstrap resources are created:

```bash
cd infrastructure/environments/dev
terraform init  # Configures the S3 backend from backend.tf
terraform plan
terraform apply
```

The `backend.tf` file in each environment references the appropriate S3 bucket and DynamoDB table. The state file is stored at `s3://<bucket>/<environment>/terraform.tfstate`.

### State Migration (Existing Deployments)

If you have existing local state files:

1. Ensure the bootstrap resources exist (run `terraform apply` in `infrastructure/bootstrap`)
2. Run `terraform init -migrate-state` in the environment directory
3. Terraform will prompt to copy the local state to S3
4. After successful migration, the local `terraform.tfstate` files can be removed (they're already gitignored)

### Multi-Environment State Isolation

Each environment (dev, prod, client-specific) uses:
- The **same S3 bucket** for centralized management
- A **unique state file path** (e.g., `dev/terraform.tfstate`, `prod/terraform.tfstate`)
- Environment-specific DynamoDB tables to prevent lock contention

For production environments, consider using separate AWS accounts or dedicated state buckets for additional isolation.

---

## Workflow

1. **Bootstrap Backend Resources (First Time Only):** Create the S3 bucket and DynamoDB table by applying the `infrastructure/bootstrap` configuration.
2. **Core Network First:** Compose the `core_network` module to establish the baseline VPC, subnets, and security boundaries.
3. **Data Plane & Shared Resources:** Layer in storage, queues, and shared IAM roles with the `data_plane` and `shared` modules.
4. **Embedding Provider:** Instantiate exactly one embedding module based on `var.embedding_backend`.
5. **Vector Store:** Provision the appropriate vector database module (FAISS/Qdrant/pgvector) to house embeddings.
6. **Search Runtime:** Toggle between `search_service_fargate` or `search_service_lambda` using `var.search_runtime`. Both expect the same container artifact.
7. **Observability:** Append monitoring defaults with the `observability` module to ensure metrics, logs, and alarms are consistent.
8. **Environment Composition:** The `environments/` directory contains Terraform stacks (e.g., `dev`, `prod`, `client-X`) that wire these modules together with environment-specific variables.

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