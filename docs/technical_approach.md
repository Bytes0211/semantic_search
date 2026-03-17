# Technical Approach: Semantic Search Platform

## 1. Context
This document translates the goals and scope defined in `docs/PRD-semantic-search.md` into an implementable, modular architecture that balances production-grade reliability with cost efficiency across client deployments.

## 2. Alignment with Goals & Success Criteria
- **Natural-language semantic search** is delivered through an embedding-driven retrieval pipeline with vector similarity ranking, directly supporting the relevance targets (90%+).
- **Sub-second latency** is addressed by keeping the hot search path on warm compute (ECS/Fargate preferred) while offering Lambda for cost-sensitive scenarios, both backed by scalable vector storage.
- **Extensible data ingestion** is enabled by modular connectors for CSV, SQL, JSON, and APIs, with Terraform-managed configuration for quick onboarding of new sources.
- **Minimal infrastructure overhead** is achieved by composing infra modules that can be selectively enabled (UI optional, Lambda vs Fargate, different embedding providers).
- **Clear documentation & handoff** is built into the delivery plan with runbooks, Terraform module READMEs, and configuration templates per client tier.

## 3. High-Level Architecture
1. **Data Ingestion Layer** – pluggable extractors normalize source data and emit canonical records to S3.
2. **Preprocessing & Feature Engineering** – text cleaning, field selection, and chunking managed by a Python pipeline.
3. **Embedding Provider Interface** – configurable adapters (Bedrock, Spot-hosted open source, SageMaker) produce vector embeddings.
4. **Vector Store Tier** – FAISS (ECS), Qdrant, or pgvector host embeddings and metadata for semantic queries.
5. **Search Service Runtime** – containerized Python API exposing semantic search operations; deployable to ECS/Fargate or Lambda.
6. **Client Interfaces** – REST API, CLI, and optional lightweight UI for validation.
7. **Observability & Ops** – centralized logging, metrics, alarms, and dashboards managed via Terraform.

## 4. Modular Deployment Strategy
The system is packaged as reusable Terraform modules that can be composed per client engagement:
- `modules/core_network`: VPC, subnets, security groups.
- `modules/data_plane`: S3 buckets, ingestion queues, batch orchestration.
- `modules/vector_store`: parameterized to provision FAISS on ECS tasks, managed Qdrant, or pgvector on RDS.
- `modules/search_service_fargate` / `modules/search_service_lambda`: mutually exclusive modules selected by `var.search_runtime`.
- `modules/embedding_bedrock`, `modules/embedding_spot`, `modules/embedding_sagemaker`: embedding backend selection via `var.embedding_backend`.
- `modules/observability`: shared CloudWatch dashboards, alarms, and log retention policies.

### Runtime Toggle: Fargate vs. Lambda
- **Configuration**: `var.search_runtime = "fargate" | "lambda"`.
- **Outputs**: Unified API endpoint, IAM role ARNs, autoscaling policies, and deployment artifacts for the chosen runtime.
- **Container Strategy**: Single Docker image for the search application; reused across both runtimes (Lambda container images vs ECS task definitions). See `developer/container_pipeline.md` for build and deployment workflow details and `infrastructure/README.md` for runtime/embedding toggle configuration examples.
- **Shared Infra**: Vector store, networking, and monitoring modules remain unchanged, ensuring consistent behavior regardless of runtime choice.
- **Trade-offs**:
  - Fargate → higher baseline cost, predictable latency, long-lived connections.
  - Lambda → lower idle cost, potential cold-start latency; mitigate with provisioned concurrency when required.

## 5. Embedding Provider Abstraction
### Provider Interface
- Define `EmbeddingProvider.generate(records: List[Record]) -> List[Vector]` within the application.
- Implementations register via configuration (env vars, config file, or Terraform outputs consumed by the runtime).

### Deployable Options
1. **AWS Bedrock**
   - Managed embeddings (Titan, Claude).
   - High reliability, compliance alignment.
   - Terraform provisions IAM policies, allowed model IDs, and regional endpoints.
2. **Open-Source Model on Spot Capacity**
   - Containerized model server (e.g., SentenceTransformers) running on spot EC2 or Fargate Compute Savings Plans.
   - Lifecycle hooks checkpoint model weights to S3 for rapid recovery.
   - Autoscaling group policies and preemption alarms are provisioned via Terraform.
3. **SageMaker Endpoint with Autoscaling**
   - Managed hosting for custom models.
   - Terraform defines endpoint configs, scaling policies, and CloudWatch metrics for invocation throttling.

### Selection Mechanics
- Terraform variable `var.embedding_backend` controls which provider module is instantiated.
- Application uses configuration bundle (e.g., JSON delivered via SSM Parameter Store or Secrets Manager) to initialize the matching adapter at runtime.
- New providers can be added by implementing a new adapter and Terraform module without impacting existing flows.

## 6. Data Pipeline & Indexing
- **Ingestion**: Python-based orchestration (possibly Dagster or Airflow-lite scripts) reads from CSV, SQL, JSON, and API sources.
- **Normalization**: Light schema mapping, text field concatenation, and metadata tagging.
- **Batch Processing**: Delivered in Phase 2 with pluggable connectors and canonical normalization; Terraform toggle `var.ingestion_mode = "batch" | "stream"` still governs optional streaming infrastructure (e.g., Kinesis) for clients demanding near-real-time updates.
- **Embedding Jobs**: Batch workers read normalized records, invoke the configured embedding provider, and write vectors + metadata to S3 and the vector store.
- **Index Refresh**: Idempotent upserts ensure minimal downtime; blue/green index swaps available for large rebuilds.

## 7. Semantic Search Service
- **API Contract**: REST endpoints for keyword + semantic query, filters, pagination, and relevance scores; CLI mirrors API via shared client library.
- **Ranking**: Cosine similarity primary ranking with optional re-ranking (e.g., cross-encoder) activated per client.
- **Caching**: Optional Redis/ElastiCache module for frequent queries.
- **Security**: IAM-authenticated API Gateway or ALB with mTLS/VPC access restrictions per client requirements.

## 8. Observability & Quality Assurance
- **Logging**: Centralized structured logs (JSON) shipped to CloudWatch and optionally to OpenSearch or Datadog.
- **Metrics**:
  - Query latency, throughput, cache hit rate, embedding job durations.
  - Model performance metrics captured during evaluation runs (relevance score, MRR).
- **Alerts**: Terraform defines SLO thresholds (latency > 1s, error rate > 2%).
- **Testing**:
  - Automated QA suite with synthetic queries (90% relevance goal).
  - Load tests (e.g., Locust) targeting sub-second SLA.
  - Infrastructure validation via Terraform tests (e.g., terratest).

## 9. Cost Management Strategies
- **Right-Sizing Compute**: Terraform variables parameterize CPU/memory for ECS tasks, Lambda provisioned concurrency, and autoscaling thresholds.
- **Spot vs On-Demand**: Support spot capacity for non-critical workloads (embedding generation) while keeping latency-critical services on on-demand or provisioned capacity.
- **Storage Lifecycle Policies**: S3 lifecycle rules move older raw data and embeddings to infrequent access or Glacier tiers.
- **Batch-Oriented Ingestion**: Default to scheduled batch pipelines to avoid always-on compute; enable streaming only when absolutely needed.
- **Benchmarking**: Terraform workspaces per client allow cost comparisons of different embedding/vector store configurations before committing.

## 10. Security & Compliance Considerations
- **Data Residency**: Region selection via Terraform ensures data stays within client-approved boundaries.
- **Access Control**: Principle of least privilege IAM roles; secrets managed in Secrets Manager with rotation policies.
- **Network Isolation**: Private subnets for data and search tiers; optional VPC endpoints for Bedrock/SageMaker.
- **Auditability**: CloudTrail logging of API usage; embedding and search logs stored with retention policies to meet compliance needs.

## 11. Delivery & Handoff Plan
1. **Scaffold Terraform Modules** – implement core + optional modules, publish reference architectures.
2. **Build Application Skeleton** – Completed in Phase 2 with provider interfaces, canonical ingestion pipelines, and baseline search surfaces.
3. **Integrate Embedding Providers** – In progress for Phase 3: implement adapters, add integration tests, and document setup steps.
4. **Implement Deployment Profiles** – default to Fargate runtime with Lambda alternative; provide deployment recipes.
5. **Performance Validation** – run relevance evaluation suite and latency benchmarks for both runtimes.
6. **Documentation & Training** – deliver runbooks, customization guides, and Terraform variable reference for client teams.

## 12. Future Enhancements
- Add hybrid search (keyword + vector) for fallback scenarios.
- Introduce multi-tenant isolation module for clients who require shared infrastructure with strict data boundaries.
- Support automated schema inference for new data sources to further reduce onboarding friction.
- Incorporate human feedback loops to continuously improve relevance metrics.

## 13. Summary
This approach provides a modular, infrastructure-as-code-managed semantic search platform that meets the PRD’s goals for accuracy, latency, extensibility, and operational clarity. By parameterizing critical choices—search runtime, embedding provider, ingestion mode—the system can be tuned for each client’s performance and cost profile without forking the codebase.