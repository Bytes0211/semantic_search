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
- **MongoDB** — connects via PyMongo, queries with configurable filter and projection, and streams cursor results as canonical records.

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

### Branch: feature/data-abstraction — Data Abstraction & Preprocessing
- ✅ Implemented 6 pluggable connectors in `semantic_search/ingestion/`: CSV, SQL (SQLAlchemy), JSON/JSONL, XML (XPath), REST API (pagination + retry), and MongoDB (PyMongo cursor) — all emit canonical `Record(record_id, text, metadata, source)`.
- ✅ Added `semantic_search/preprocessing/` package: `TextCleaner` (HTML strip via regex, NFKC Unicode, whitespace collapse, optional lowercase), `TextChunker` (word-boundary char split, configurable `chunk_size`/`overlap`, `chunk("") → []`), and `PreprocessingPipeline` (opt-in cleaner + chunker; chunked records get `{id}#chunk-{n}` IDs; drops empty records with WARNING).
- ✅ Added `data/sample.csv` (20 rows, 5 categories — `id, title, content, category, author`) for local development and test validation.
- ✅ Added `scripts/generate_csv_index.py` and `scripts/generate_pg_index.py` — end-to-end index build scripts using `CsvConnector`/`SqlConnector`, Spot embedding provider (dim=384), and `NumpyVectorStore`.
- ✅ Created `test_spot_csv_server.sh`, renamed `test_bedrock_json_server.sh`, and added `test_bedrock_pg_server.sh` — full validation runner scripts with index generation, server launch, endpoint verification, interactive query loop, and optional `--ui` flag.
- ✅ Authored `developer/functional_process_flow.md` — accurate Mermaid diagram + prose stage notes for the full ingestion → preprocessing → embedding → vector store → query pipeline.
- ✅ Created `github/ISSUES/data-abstraction.md` tracking all branch deliverables and known follow-ups.
- ✅ Applied 9 PR review fixes: lazy `httpx` import with `TYPE_CHECKING` guard, exponential backoff in API connector, explicit auth validation guard, dead SQL branch removal, XML `_sequence` coercion to `List[str]`, `sqlalchemy` dependency dedup in `pyproject.toml`, `chunk("") → []` empty-string guard, Spot embedding dimension 768→384, and `.gitignore` + `git rm --cached` for `*_index/` directories.
- ✅ Added `pymongo>=4.6,<5.0` to production dependencies; removed duplicate `sqlalchemy` from dev dependencies.
- ✅ Test suite: 208 passing (up from 157) — 51 new preprocessing tests across `tests/preprocessing/`, 33 ingestion tests.

### Branch: feature/record_drill_down — Record Detail Drill-Down
- ✅ Added `_detail` metadata convention: at index build time, configurable detail fields are stored under a reserved `_detail` key in vector store metadata, separating display/filter fields from rich drill-down content.
- ✅ Updated `scripts/generate_pg_index.py` — added `detail_fields` to `TABLE_CONFIGS` (candidates: `["summary", "skills"]`, tickets: `["body"]`); new `_split_metadata()` helper; combined `metadata_fields + detail_fields` passed to SQL connector.
- ✅ Updated `scripts/generate_csv_index.py` — added `--detail-fields` CLI argument (comma-separated) with same `_split_metadata()` convention.
- ✅ Extended `SearchResultItem` in `api.py` with `detail: Dict[str, Any]`; `SearchRuntime.search` pops `_detail` from metadata and surfaces it as a separate field. Missing `_detail` → empty dict (backward compatible).
- ✅ Added `detail: Record<string, unknown>` to frontend `SearchResultItem` TypeScript interface.
- ✅ Enhanced `ResultCard.tsx` with inline expand/collapse toggle (chevron icon, `aria-expanded`); detail fields rendered as `<dt>`/`<dd>` blocks below metadata tags; no affordance when `detail` is empty.
- ✅ Added `--show-detail` flag to CLI `_render_response`; detail fields print indented below metadata with `--- detail ---` separator.
- ✅ 6 new tests: 2 runtime tests (`_detail` extraction + backward compat), 4 frontend tests (toggle visibility, expand, collapse).

### Branch: feature/config_enhancements — Configuration Externalization
- ✅ Created `semantic_search/config/` package with 5 modules: `app.py` (`AppConfig`, tier→flags, env var overrides), `models.py` (`MODEL_PRESETS`, `resolve_dimension`), `source.py` (`SourceConfig`, `load_source_configs`), `display.py` (`DisplayConfig`, `ColumnConfig`, `DetailSectionConfig`), `metadata.py` (shared `split_metadata`).
- ✅ Created YAML config files: `config/app.yaml` (default Standard/Spot), 5 source configs under `config/sources/`, 4 example app profiles under `config/examples/`.
- ✅ Consolidated `_split_metadata` — replaced four duplicate copies in generate scripts with `from semantic_search.config.metadata import split_metadata`.
- ✅ Added `--config` and `--app-config` CLI flags to all 4 generate scripts (`generate_csv_index.py`, `generate_pg_index.py`, `generate_json_index.py`, `generate_mongo_index.py`). Precedence: CLI flag > source YAML > script default.
- ✅ Created unified `scripts/generate_index.py` — config-driven multi-source index builder reading `config/app.yaml` + `config/sources/*.yaml`; supports `--source`, `--backend`, `--model`, `--dimension` overrides.
- ✅ Updated `create_app()` in `api.py` to accept `app_config` and `display_configs`; `/v1/config` now returns `tier`, `detail_enabled`, `filters_enabled`, `analytics_enabled`, `search_top_k`, and per-source `display` map.
- ✅ Updated `main.py` to load YAML config at startup (`CONFIG_DIR` env var, defaults to `./config`); full backward compat with env-var-only deployments.
- ✅ Updated frontend: extended `ConfigResponse` in `types/api.ts`, `App.tsx` gates features by config flags, `ResultCard.tsx` uses display config for title/columns/detail labels.
- ✅ Wrote 51 config tests across 5 test files in `tests/config/`.
- ✅ Created `config/README.md` with full YAML schema reference, tier feature matrix, model presets, precedence rules, and examples.
- ✅ Updated `developer/guides/data-and-testing-guide.md` with config-driven workflow, YAML reference, and unified builder documentation.
- ✅ Test suite: 261 passing (up from 210) — 51 new config tests, 0 regressions.

### Phase 7 — Preprocessing Integration & Live Search Activation — Complete
- ✅ Added `PreprocessingConfig` dataclass to `semantic_search/config/app.py` with `enabled`, `clean`, `chunk`, `chunk_size`, `overlap` fields and full env-var override support (`PREPROCESSING_*`).
- ✅ Added `build_preprocessing_pipeline(cfg)` factory function to `semantic_search/config/app.py` — constructs a `PreprocessingPipeline` from config; returns `None` when preprocessing is a no-op (disabled or neither clean nor chunk enabled).
- ✅ Exported `PreprocessingConfig` and `build_preprocessing_pipeline` from `semantic_search/config/__init__.py`.
- ✅ Wired `PreprocessingPipeline` into all five generate scripts (`generate_index.py`, `generate_csv_index.py`, `generate_pg_index.py`, `generate_json_index.py`, `generate_mongo_index.py`) — pipeline applied after connector extraction and before EmbeddingInput construction; `--no-preprocessing` flag bypasses it.
- ✅ Added `preprocessing:` block to `config/app.yaml` (enabled=true, clean=true, chunk=false, chunk_size=512, overlap=64) and updated `config/README.md` with schema reference and env var mapping.
- ✅ Updated `Dockerfile` with a Node 20 multi-stage frontend build: `frontend-builder` stage runs `npm ci && npm run build`; `frontend/dist/` is copied into the runtime image so `ENABLE_UI=true` works without separate build infrastructure.
- ✅ Updated `main.py` to mount the React SPA at `/` (root) when `ENABLE_UI=true`, enabling single-container production mode at `http://<host>/`.
- ✅ Authored `developer/runbooks/index_build.md` — index build commands (all three backends), S3 upload, ECS task activation, `/readyz` polling, validation suite and Locust runs, rollback procedure.
- ✅ Added 7 new `TestLoadAppConfig` tests and `TestBuildPreprocessingPipeline` class (8 tests) to `tests/config/test_app.py`.
- ✅ Created `tests/preprocessing/test_pipeline_wiring.py` — 24 new tests covering CSV extract_inputs wiring, unified builder `extract_from_source` wiring, `--no-preprocessing` CLI parsing, and `PreprocessingConfig`-to-pipeline integration.
- ✅ Test suite: **292 passing** (up from 268) — 24 new wiring tests + 7 config tests, 0 regressions.

### Branch: feature/iam-security — IAM Security Hardening
- ✅ Created `infrastructure/modules/iam_security/` module: permission boundary policy (scoped to project S3/SQS/SNS/Bedrock/CW/ECR/KMS/Secrets Manager with deny statements for privilege escalation, bucket destruction, and infra management), KMS customer-managed key with auto-rotation and service principal grants, CloudTrail trail with S3 bucket policy + optional CW Logs delivery + optional data events, and exported deny-guardrail policy JSON.
- ✅ Added VPC endpoints to `core_network`: S3 gateway endpoint, interface endpoints for SQS/SNS/Bedrock Runtime/CloudWatch Logs/ECR API/ECR DKR (all gated by toggle variables), shared VPCE security group allowing HTTPS from VPC CIDR only.
- ✅ Wired permission boundaries into `search_service_fargate` (task role) and `search_service_lambda` (execution role) via `var.permissions_boundary_arn`.
- ✅ Attached deny-guardrail inline policies to both Fargate task role and Lambda execution role via `var.deny_guardrail_policy_json`.
- ✅ Replaced blanket `0.0.0.0/0` all-port egress on service and Lambda security groups with dynamic rules: unrestricted (default) or HTTPS-only to VPC CIDR when `var.restrict_egress = true`.
- ✅ Added KMS encryption to `data_plane`: S3 canonical and embeddings buckets switch from SSE-S3 to SSE-KMS, SQS ingestion + DLQ queues and SNS reindex topic encrypted when `kms_key_arn` is provided.
- ✅ Attached previously dangling IAM policies in dev environment: `bedrock_invoke_policy_arn` → task role, `s3_access_policy_arn` → task role, `index_read_policy_arn` → task role (Fargate and Lambda variants, count-gated).
- ✅ Added `role_name` and `role_arn` outputs to `search_service_lambda` for correct policy attachment targeting.
- ✅ Dev environment fully wired: `iam_security` module instantiated with project bucket/queue/topic ARNs, `kms_key_arn` passed to `data_plane`, VPC endpoint toggles passed to `core_network`, security vars passed to runtime modules.
- ✅ `terraform validate` passes.
- ✅ Created `github/ISSUES/iam-security-hardening.md` tracking all deliverables and follow-ups.

**Remaining (infrastructure, deferred):**
- Build and upload FAISS index to S3 → confirm `/readyz → 200` (requires live AWS credentials).
- Run `semantic-search-eval` and Locust against the live ALB endpoint with a real index.
- Add pgvector and Qdrant vector store adapters (currently only `NumpyVectorStore` is implemented).
- Extend `_detail` support to remaining connectors (XML, API, MongoDB) as needed.
- `terraform apply` the IAM security changes in the dev environment.
- Enable `restrict_egress` + `enable_interface_endpoints` for prod environments.
- Attach `index_write_policy_arn` to a dedicated embedding pipeline role.
- Add IAM Access Analyzer and Secrets Manager rotation schedules.

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
