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

## Security Configuration

### HTTPS and TLS

The Fargate ALB supports optional HTTPS with ACM certificates:

- **Development:** HTTP-only mode is acceptable for testing (no certificate required)
- **Production:** HTTPS is strongly recommended; provide an ACM certificate ARN via `search_service_acm_certificate_arn`

When a certificate ARN is provided:
- HTTPS listener is created on port 443 with TLS 1.3 policy (`ELBSecurityPolicy-TLS13-1-2-2021-06`)
- HTTP port 80 redirects to HTTPS with a permanent (301) redirect
- Security group allows both HTTP and HTTPS ingress from configured CIDRs

When no certificate is provided:
- HTTP listener forwards directly to the target group
- No HTTPS listener is created
- Security group allows only HTTP ingress

**To enable HTTPS:**
1. Create or import an ACM certificate in the deployment region
2. Set `search_service_acm_certificate_arn` in terraform.tfvars
3. Apply the Terraform configuration

### Network Access Control

The `search_service_allowed_ingress_cidrs` variable controls which IP ranges can access the ALB:

- **Development:** `0.0.0.0/0` is acceptable for testing but not recommended
- **Staging/Production:** Restrict to known CIDRs:
  - Office/VPN IP ranges
  - CloudFront prefix list (if using CDN)
  - Partner API gateway IPs
  - Internal VPC CIDR (for service-to-service calls)

**Example production configuration:**
```hcl
search_service_allowed_ingress_cidrs = [
  "203.0.113.0/24",    # Office network
  "198.51.100.0/24",   # VPN range
]
search_service_acm_certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/abcd1234-..."
```

### Private Subnets and NAT Gateway

Fargate tasks run in **private subnets** for security hardening and do not receive public IP addresses. Outbound connectivity to AWS services (ECR, Bedrock, S3) and the internet is provided through a **NAT gateway** or **VPC endpoints**.

**Configuration options:**

1. **NAT Gateway (default)** — Simplest option, provides general internet egress for all services
   - Cost: ~$32/month per AZ plus data transfer charges
   - Set `create_nat_gateway = true` in terraform.tfvars
   - Tasks automatically route all egress through the NAT gateway
   
2. **VPC Endpoints** — Lower cost for specific AWS services, no internet egress
   - Cost: ~$7/month per interface endpoint (e.g., ECR, Bedrock)
   - Set `enable_interface_endpoints = true` in terraform.tfvars
   - Requires endpoint configuration for each required service
   - No internet access (outbound HTTPS is blocked except to AWS services)

**Network flow:**
- Internet → ALB (public subnets) → Fargate tasks (private subnets)
- Fargate tasks → NAT gateway (public subnet) → Internet Gateway → AWS services/Internet
- Or: Fargate tasks → VPC endpoints (private subnets) → AWS services directly

**Required settings:**
```hcl
create_nat_gateway              = true   # Or enable_interface_endpoints = true
search_service_assign_public_ip = false  # Tasks use private IPs only
```

**Important limitations:**
- **Single NAT Gateway:** The default configuration provisions one NAT gateway in the first availability zone only. Tasks in other AZs route egress traffic cross-AZ through this single NAT gateway. If that AZ experiences degradation, all private subnet egress fails, despite the multi-AZ ECS deployment. For production environments requiring AZ-level fault isolation, consider enabling VPC interface endpoints instead (`enable_interface_endpoints = true`), which are provisioned per-AZ automatically.
- **Egress precondition:** Terraform enforces that at least one egress mechanism is enabled when tasks are in private subnets. If `create_nat_gateway`, `enable_interface_endpoints`, and `search_service_assign_public_ip` are all `false`, the apply will fail with a precondition error.

When disabling the NAT gateway or VPC endpoints (e.g., for local testing), tasks can be placed in public subnets with `assign_public_ip = true`, but this configuration **is not recommended for production** as it exposes container instances directly to the internet.

### Security Group Egress Restrictions

The `restrict_egress` variable controls outbound traffic from Fargate tasks, Lambda functions, and the ALB security groups.

**When `restrict_egress = false` (default for development):**
- All security groups allow unrestricted egress (`0.0.0.0/0`) on all ports
- Simplifies initial setup and troubleshooting
- **Not recommended for production** — widens blast radius if a workload is compromised

**When `restrict_egress = true` (recommended for production):**
- Fargate task and Lambda security groups: HTTPS egress (port 443) scoped to VPC CIDR only
- ALB security group: All egress scoped to VPC CIDR only (for forwarding to tasks)
- Requires either NAT gateway or VPC endpoints for AWS service access

**Example production configuration:**
```hcl
create_nat_gateway = true   # Provides egress for all AWS services
restrict_egress    = true   # Scopes all security group egress to VPC CIDR
```

**Prerequisites for enabling `restrict_egress = true`:**
- At least one egress path must be provisioned (`create_nat_gateway = true` OR `enable_interface_endpoints = true`)
- VPC CIDR must be set (automatically provided via `var.vpc_cidr`)

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