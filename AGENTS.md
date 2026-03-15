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
> **Recommendation:** If you don't have a known consumer pinned below 1.9, bumping to `>= 1.9.0` is reasonable. It simplifies validation patterns and the old floor is nearly two years behind. If you're unsure about downstream consumers, you could bump to `>= 1.9.0` in `environments/dev/` (which you control) and leave the module constraint at `>= 1.5.0` so the modules stay reusable.

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

### Data Ingestion Connectors
- **CSV** — streams one or more files, concatenates configured text columns, and records metadata fields for downstream filtering.
- **SQL** — executes parameterised SELECT statements via SQLAlchemy, supporting server-side cursors for large result sets.
- **JSON / JSONL** — loads array or newline-delimited exports, applies optional jq-style filters, and converts objects into canonical records.
- **XML** — selects repeating nodes via XPath, extracts child elements or attributes for text/metadata, and handles namespace-aware documents.
- **REST API** — paginates through cursor- or offset-based endpoints with configurable headers, parameters, and retry logic.

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

## Phase Markers
### Phase 0 — Planning & Alignment
- Align on goals, success criteria, and scope boundaries using `docs/PRD-semantic-search.md` as the source of truth.
- Record architectural and modular requirements in `developer/technical_approach.md`, `README.md`, and `AGENTS.md`.
- Establish documentation checkpoints and governance for future phase handoffs.

### Phase 1 — Foundation & Infrastructure
- ✅ Scaffolded Terraform module directories (`core_network`, `data_plane`, `vector_store`, `search_service_*`, `embedding_*`, `observability`, `shared`) with initial responsibilities captured in module READMEs.
- ✅ Defined configuration toggles (`var.search_runtime`, `var.embedding_backend`, `var.ingestion_mode`) with trade-offs and published toggle guidance + tfvars examples in `infrastructure/README.md`.
- ✅ Authored the reusable container build/deploy pipeline (`developer/container_pipeline.md`) supporting both ECS/Fargate and Lambda runtimes.
- ✅ Phase 1 deliverables unlocked Phase 2 ingestion work (pluggable connectors, canonical schema, instrumentation).

### Phase 2 — Data Ingestion Layer
- ✅ Implemented pluggable connectors (CSV, SQL, JSON, API) and orchestrated scheduled batches with optional streaming pathways.
- ✅ Normalized records into a canonical schema persisted to S3 with metadata enrichment.
- ✅ Added ingestion observability (structured logging, metrics, DLQ alerts) and documented configuration toggles feeding Phase 3.
- ✅ Updated developer documentation to reflect ingestion outputs and dependencies for embedding jobs.

### Phase 3 — Embedding & Vector Services
- ✅ Implemented shared `EmbeddingProvider` base interface and provider factory registry (`semantic_search/embeddings/`).
- ✅ Delivered Bedrock, Spot-hosted OSS, and SageMaker embedding adapters — all registered via factory and covered by unit tests.
- ✅ Provisioned NumPy-backed vector store (`NumpyVectorStore`) with L2, cosine, and inner-product metrics, idempotent upsert, metadata persistence, and save/load roundtrip.
- ✅ Fixed `upsert()` to honor its silent-overwrite contract by inlining insert logic directly, bypassing the `add()` warning path.
- ✅ Hardened `NumpyVectorStore.load()` with `VectorStoreError` for missing files, malformed metadata keys, ID/vector count mismatch, and per-row shape validation; `allow_pickle=False` enforced on `np.load`.
- ✅ Added `SageMakerInvocationError` guard for empty `embeddings` list — fails immediately at the provider boundary instead of silently propagating a `[]` into `_coerce_vector`.
- ✅ Wired end-to-end `EmbeddingPipeline` with two-phase S3 backup: files staged to a timestamped prefix; `latest` pointer written only after both uploads succeed.
- ✅ Added `backup_error: Optional[str]` to `PipelineResult` — S3 backup failures caught, logged, and recorded without discarding an otherwise successful run result.
- ✅ Added silent-record-loss detection in `_process_batch` — records omitted from provider output are logged and counted as failures.
- ✅ Full test suite green: 50 tests passing across embeddings, pipeline, and vector store modules.

### Phase 4 — Search Runtime & Interfaces
- ✅ Built FastAPI-based REST service (`semantic_search/runtime/api.py`) with health/readiness probes and the `/v1/search` endpoint.
- ✅ Delivered CLI tooling (`semantic_search/runtime/cli.py`) for ad-hoc searches using shared runtime orchestration.
- ✅ Added deterministic runtime fixtures and tests (`tests/runtime/`) validating core search logic and API wiring; test suite now 55 passing tests.
- ✅ Expanded package exports and CLI entry point (`semantic_search/__init__.py`, `pyproject.toml`) to support runtime consumption across deployment targets.
- ✅ Scaffolded full Terraform for both ECS/Fargate and Lambda runtimes (`infrastructure/modules/search_service_fargate`, `infrastructure/modules/search_service_lambda`) and wired them into the dev stack with autoscaling and configuration defaults.
- ✅ Fleshed out the observability module (`infrastructure/modules/observability/main.tf`, `variables.tf`, `README.md`) with CloudWatch dashboards (latency, error rate, queue depth, log widgets), alarms with configurable thresholds, and SNS notification wiring — consumes runtime outputs from either deployment mode.
- ✅ Expanded runtime module outputs for both Fargate (`outputs.tf`) and Lambda (`outputs.tf`) to expose ARN suffixes, log group names, autoscaling resource IDs, and API identifiers needed by dashboards, alarms, and runbooks.
- ✅ Completed dev environment wire-up (`infrastructure/environments/dev/main.tf`): full Lambda module configuration, normalised observability inputs for either runtime, and additional stack-level outputs for logs and service identifiers.
- ✅ Created example tfvars for both runtime profiles (`infrastructure/environments/dev/examples/fargate.tfvars.example`, `lambda.tfvars.example`) and documented apply instructions in `infrastructure/README.md`.
- ✅ Authored the runtime deployment runbook (`developer/runbooks/runtime_deploy.md`) covering init/plan/apply, Fargate and Lambda validation checklists, observability wiring steps, runtime switching, rollback procedures, and post-deployment tasks.
- ✅ Implemented the lightweight validation UI (`semantic_search/runtime/ui.py`) — single-page HTML/JS interface served at `/ui` via FastAPI that submits queries to `/v1/search` and renders ranked results with scores and metadata. Enabled via `create_app(enable_ui=True)` or `mount_ui(app)`; disabled by default. Self-contained with no external CDN dependencies.
- ✅ Updated `main.py` as a production-capable uvicorn launcher — reads `VECTOR_STORE_PATH`, `EMBEDDING_BACKEND`, `ENABLE_UI`, `HOST`, `PORT`, and `LOG_LEVEL` from environment; starts without a runtime when no store path is supplied so the container is healthy before an index is loaded.
- ✅ Phase 4 fully complete: test suite at 67 passing tests (12 new UI tests).

### Phase 5 — Quality & Launch Readiness
- ✅ Run `terraform apply` against the dev environment for the chosen runtime; execute the full validation checklist in `developer/runbooks/runtime_deploy.md`.
- ✅ Built and executed the relevance evaluation suite (`semantic_search/evaluation/`) — `EvalQuery`, `EvalResult`, `EvalReport` dataclasses; IR metrics (`hit_rate`, `MRR`, `Precision@K`, `nDCG@K`); `RelevanceEvaluator` wrapping `SearchRuntime`; `semantic-search-eval` CLI with text/JSON output and threshold-based exit codes; 54 new tests; suite at 121 passing tests.
- ✅ Locust load test harness (`tests/load/locustfile.py`) — env-driven query bank, `on_start` health check, `search_task` failure tracking; headless and UI modes documented in `tests/load/README.md`; acceptance criteria: P95 ≤ 1 s, error rate < 1 %.
- ✅ Cost optimisation review documented (`docs/cost_optimisation.md`) — Fargate/Lambda compute sizing, Spot strategy for embedding jobs, S3 lifecycle rules, provisioned concurrency scheduling guidance, alarm threshold calibration.
- ✅ Documentation handoff package (`developer/handoff/`) — `deployment_playbook.md` (13-step client-facing guide) and `terraform_variable_reference.md` (all variables for `core_network`, `search_service_fargate`, `search_service_lambda`, and `observability` modules).

### Deployment — AWS Fargate (dev) — Complete
- ✅ Created `Dockerfile`, `.dockerignore`, and `buildspec.yml`; container image built and pushed to ECR via AWS CodeBuild project `semantic-search-image-build` (~85 MB, base `public.ecr.aws/docker/library/python:3.12-slim`).
- ✅ Implemented missing Terraform module stubs (`data_plane`, `embedding_bedrock`, `vector_store/faiss`) and corrected validation bugs across `core_network`, `observability`, `search_service_fargate`, `search_service_lambda`, and `embedding_bedrock` modules.
- ✅ Created `infrastructure/environments/dev/terraform.tfvars`; `terraform apply` completed — **53 resources created** (VPC, ECS Fargate cluster/service, ALB, S3 buckets, CloudWatch dashboards/alarms, IAM roles).
- ✅ Health check confirmed: `GET /healthz → 200 {"status":"ok"}`; `/readyz → 503` expected (no index loaded yet).
- ✅ Git tag `runtime-v0.1.0` created.

**Live endpoints (dev):**
- ALB: `http://<alb-dns-name>.us-east-1.elb.amazonaws.com`
- ECR image: `<aws-account-id>.dkr.ecr.<region>.amazonaws.com/semantic-search:main`
- ECS cluster / service: `<project>-dev-search-cluster` / `<project>-dev-search-service`
- FAISS index bucket: `s3://<project>-dev-faiss-index/vector_store/current/`

### Phase 6 — Web UI — Complete
- ✅ Scaffolded `frontend/` with Vite + React 18 + TypeScript + Tailwind CSS v4 + TanStack Query.
- ✅ Built all UI components: `SearchBar`, `ResultCard` (with score badge and metadata tags), `FilterPanel` (dynamic field discovery from result metadata), `Pagination` (client-side over full result set), `AnalyticsPanel` (Premium-tier session analytics sidebar), `ScoreBadge`.
- ✅ Implemented hooks: `useSearch` (TanStack Query wrapper over `POST /v1/search`), `useConfig` (fetches `GET /v1/config` once at startup for tier gating), `useAnalytics` (client-side session history, average latency, top-term frequency), `useDebounce` (350 ms input debounce).
- ✅ Wired `App.tsx` — URL-synced query state (`?q=`), debounced search, client-side pagination, dynamic filter field discovery from result metadata, tier-gated analytics panel.
- ✅ Added `GET /v1/config` endpoint to `api.py` returning `{"analytics_enabled": <bool>}`; wired `ANALYTICS_ENABLED` and `CORS_ORIGINS` env vars in `main.py`.
- ✅ Deprecated `semantic_search/runtime/ui.py` (HTML validation UI superseded by React SPA; `mount_ui` retained for emergency fallback).
- ✅ Vite dev server proxies `/v1/*` to FastAPI at `localhost:8000`; production build outputs to `frontend/dist/` for S3 + CloudFront or `StaticFiles` mount.
- ✅ 15 component tests (Vitest + React Testing Library) covering `SearchBar`, `ResultCard`, and `AnalyticsPanel`.
- ✅ Authored `frontend/README.md` — local dev setup, environment variables, tier behaviour table, production deployment instructions.

**Stack delivered:** React 18 + TypeScript · Vite · Tailwind CSS v4 · TanStack Query v5

**Deployment options:**
1. FastAPI serves built `dist/` via `StaticFiles` mount — single container, no extra infra
2. `dist/` deployed to S3 + CloudFront — CDN delivery, decoupled from API lifecycle

### Next Steps
- Build a FAISS index and upload to `s3://semantic-search-dev-faiss-index/vector_store/current/` to enable `/readyz → 200` and activate `/v1/search`.
- Update the ECS task definition to set `VECTOR_STORE_PATH` pointing at the S3 prefix after index upload.
- Run the relevance evaluation suite (`semantic-search-eval`) and Locust load tests against the live ALB endpoint once an index is loaded.
- Update `Dockerfile` to include a frontend build step (or separate build artifact) for single-container production mode.

## Delivery Phases
1. **Scaffold Terraform Modules** — implement core + optional modules, publish reference architectures
2. **Build Application Skeleton** — establish provider interfaces, ingestion pipeline, and search API baseline
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
