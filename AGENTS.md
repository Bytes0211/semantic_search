# AGENTS.md — Semantic Search Platform

## Project Overview
This project delivers a **semantic search system** for internal databases that uses LLM-powered embeddings, vector search, and lightweight retrieval pipelines. It enables natural-language queries across structured and semi-structured data sources (CSV, SQL, JSON, API), replacing rigid keyword search with meaning-aware retrieval.

**Key references:**
- PRD: `docs/PRD-semantic-search.md`
- Technical Approach: `developer/technical_approach.md`

## Problem Context
Clients struggle with poor search accuracy from keyword-only matching, difficulty locating records across messy or inconsistent data, slow manual review, lack of contextual search (e.g., "find candidates with turnaround experience"), and no unified search across multiple internal sources.

## User Stories
- **Recruiter:** Search for "operators with M&A experience" and get relevant candidates even if the exact phrase isn't in their profile.
- **Support agent:** Find similar past tickets to speed up resolution.
- **Manager:** Search internal documents by concept, not keywords.
- **Analyst:** Retrieve related records across multiple tables.

## Goals
- Natural-language semantic search with 90%+ relevance on test queries
- Sub-second query latency
- Extensible data ingestion with minimal configuration per new source
- Production-ready, modular codebase with clear documentation

## Architecture
The system is composed of seven layers:

1. **Data Ingestion Layer** — Pluggable extractors normalize source data (CSV, SQL, JSON, API) and emit canonical records to S3.
2. **Preprocessing** — Python pipeline for text cleaning, field selection, and chunking.
3. **Embedding Provider Interface** — Configurable adapters for AWS Bedrock, Spot-hosted open-source models, or SageMaker endpoints. Selected via `var.embedding_backend`.
4. **Vector Store** — FAISS (on ECS), Qdrant, or pgvector. Selected via Terraform module parameters.
5. **Search Service Runtime** — Containerized Python API deployable to ECS/Fargate or Lambda, toggled by `var.search_runtime`.
6. **Client Interfaces** — REST API, CLI, and optional lightweight UI.
7. **Observability** — CloudWatch logging, metrics, alarms, and dashboards via Terraform.

## Tech Stack
- **Language:** Python
- **Embeddings:** AWS Bedrock (Titan/Claude), SentenceTransformers (Spot), SageMaker
- **Vector DB:** FAISS / Qdrant / pgvector
- **Infrastructure:** Terraform (modular), AWS (ECS/Fargate, Lambda, S3, CloudWatch)
- **Orchestration:** LangChain (optional), Dagster/Airflow-lite (ingestion)
- **Caching:** Redis / ElastiCache (optional, for frequent queries)

## Infrastructure Modules (Terraform)
- `modules/core_network` — VPC, subnets, security groups
- `modules/data_plane` — S3 buckets, ingestion queues, batch orchestration
- `modules/vector_store` — Parameterized for FAISS, Qdrant, or pgvector
- `modules/search_service_fargate` / `modules/search_service_lambda` — Mutually exclusive, selected by `var.search_runtime`
- `modules/embedding_bedrock` / `modules/embedding_spot` / `modules/embedding_sagemaker` — Selected by `var.embedding_backend`
- `modules/observability` — CloudWatch dashboards, alarms, log retention

## Key Configuration Variables
- `var.search_runtime` — `"fargate"` or `"lambda"` (runtime toggle)
- `var.embedding_backend` — Selects embedding provider module
- `var.ingestion_mode` — `"batch"` (default) or `"stream"` (provisions Kinesis)

## Container Strategy
A single Docker image is used for the search application, reused across both runtimes (Lambda container images vs ECS task definitions). The vector store, networking, and monitoring modules remain unchanged regardless of runtime choice.

- **Fargate** → higher baseline cost, predictable latency, long-lived connections.
- **Lambda** → lower idle cost, potential cold-start latency; mitigate with provisioned concurrency.

## Coding Conventions
- Python with Google-style docstrings on all classes and functions
- Modular, pluggable design — new data sources and embedding providers should be addable without modifying existing code
- Embedding providers implement `EmbeddingProvider.generate(records: List[Record]) -> List[Vector]`
- Implementations register via configuration (env vars, config file, or Terraform outputs consumed by the runtime)
- Configuration delivered via environment variables, config files, or SSM Parameter Store

## Data Flow
1. Ingest from source → 2. Preprocess & normalize → 3. Generate embeddings → 4. Store in vector DB → 5. Query → 6. Retrieve & rank (cosine similarity) → 7. Return results

### Indexing Details
- Default scheduled batch processing; streaming (Kinesis) available via `var.ingestion_mode`
- Idempotent upserts ensure minimal downtime during re-indexing
- Blue/green index swaps available for large rebuilds
- Embedding jobs write vectors + metadata to both S3 and the vector store

## Functional Requirements
- Ingest structured/semi-structured data from CSV, SQL, JSON, API
- Generate embeddings for text fields
- Store embeddings in a vector index
- Expose semantic search interface (REST API and CLI via shared client library)
- Rank results by cosine similarity with optional cross-encoder re-ranking (per client)
- Support filters (date, category, tags) and pagination
- Provide logs for search queries and performance

## Security Constraints
- No external data sharing; all processing local or in client's AWS
- IAM least-privilege roles; secrets in Secrets Manager with rotation
- IAM-authenticated API Gateway or ALB with mTLS/VPC access restrictions
- Private subnets for data and search tiers; optional VPC endpoints for Bedrock/SageMaker
- Region selection via Terraform for data residency compliance
- CloudTrail audit logging of API usage; logs stored with retention policies

## Non-Functional Requirements
- **Performance:** Sub-second search latency; SLO alerts at >1s latency or >2% error rate
- **Scalability:** Support up to millions of records
- **Reliability:** Graceful fallback if embedding model fails
- **Maintainability:** Modular codebase with clear configuration
- **Observability:** Structured JSON logs to CloudWatch (optional OpenSearch/Datadog); metrics for query latency, throughput, cache hit rate, embedding job durations, and model performance (relevance score, MRR)
- **Testing:** Automated QA suite with synthetic queries (90% relevance target), load tests (Locust) targeting sub-second SLA, Terraform validation (terratest)

## Cost Management
- Right-size compute via Terraform variables for CPU/memory, provisioned concurrency, and autoscaling thresholds
- Use spot capacity for non-critical workloads (embedding generation); on-demand for latency-critical services
- S3 lifecycle rules move older data/embeddings to Infrequent Access or Glacier
- Default to batch pipelines to avoid always-on compute; enable streaming only when needed
- Terraform workspaces per client enable cost comparisons across configurations

## Risks & Assumptions
**Risks:**
- Poor data quality may reduce search accuracy
- Very large datasets may require optimized indexing
- Client may need help selecting fields to embed

**Assumptions:**
- Client provides clean access to data sources
- Client has or can provision AWS access
- Data volume fits within selected vector DB limits

## Acceptance Criteria
- Search returns relevant results for provided test queries
- Pipeline runs end-to-end without errors
- Documentation enables client to re-index new data
- Deployment validated in client environment

## Delivery Phases
1. **Scaffold Terraform Modules** — implement core + optional modules, publish reference architectures
2. **Build Application Skeleton** — establish provider interfaces, ingestion pipeline, search API baseline
3. **Integrate Embedding Providers** — implement adapters, add integration tests, document setup steps
4. **Implement Deployment Profiles** — default Fargate runtime with Lambda alternative; provide deployment recipes
5. **Performance Validation** — relevance evaluation suite and latency benchmarks for both runtimes
6. **Documentation & Training** — runbooks, customization guides, Terraform variable reference for client teams

## Future Enhancements
- Hybrid search (keyword + vector) for fallback scenarios
- Multi-tenant isolation module for shared infrastructure with strict data boundaries
- Automated schema inference for new data sources
- Human feedback loops to continuously improve relevance metrics

## Scope Boundaries
**In scope:** Data ingestion, embedding generation, vector storage, semantic search API/CLI, documentation, optional UI and AWS deployment.

**Out of scope:** Full enterprise search platform, multi-tenant architecture, deep data cleaning.

> **Note:** Near-real-time streaming ingestion is available as an optional configuration (`var.ingestion_mode = "stream"`), but the default and recommended mode is scheduled batch processing.
