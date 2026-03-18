# Semantic Search for Internal Databases

![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)
![Version](https://img.shields.io/badge/version-0.1.0-blue)
![Tests](https://img.shields.io/badge/tests-292_passing-brightgreen?logo=pytest&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-Bedrock%20%7C%20ECS%20%7C%20Lambda-FF9900?logo=amazonaws&logoColor=white)
![IAM](https://img.shields.io/badge/IAM-Least%20Privilege-orange?logo=amazonaws&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-IaC-7B42BC?logo=terraform&logoColor=white)
![Observability](https://img.shields.io/badge/Observability-CloudWatch-FF4F8B?logo=amazonaws&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-container-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-TBD-lightgrey)

A semantic search system that uses LLM-powered embeddings and vector search to enable natural-language queries across internal structured and semi-structured data sources. Replaces rigid keyword search with meaning-aware retrieval.

**Key references:**
- [Product Requirements](docs/PRD-semantic-search.md)
- [Technical Approach](docs/technical_approach.md)

## Problem

Organizations store valuable information across databases, CRMs, spreadsheets, and legacy systems but rely on keyword-only search that fails to surface relevant insights. This leads to poor search accuracy, slow manual review, and missed connections across data sources.

Keyword search typically retrieves **<40%** of relevant documents in enterprise datasets.

## Comparison Table: Keyword Search vs. Semantic Search

| Aspect | Keyword Search (Fails) | Semantic Search (Succeeds) |
|-------|-------------------------|-----------------------------|
| **User Query** | “How do I get reimbursed for conference travel?” | Same query |
| **Matching Method** | Literal word matching | Meaning, intent, and conceptual similarity |
| **What It Looks For** | Exact tokens: *reimbursed*, *conference*, *travel* | Concepts: *expense claims*, *business trip*, *reimbursement workflow* |
| **Returned Results** | - “Travel Restrictions and Approval Workflow”<br>- “Corporate Card Usage Guidelines”<br>- “Conference Attendance Policy” | - “Expense Claim Submission Process”<br>- “Travel & Expense Policy”<br>- “Guide: Uploading Receipts to Finance Portal” |
| **Why It Fails/Succeeds** | Misses relevant docs because the policy uses different wording (e.g., *expense claim* instead of *reimbursement*) | Understands that *reimbursement* ≈ *expense claim* and *conference travel* ≈ *business trip* |
| **Impact on User** | Slow, frustrating, incomplete answers | Fast, accurate retrieval of the correct workflow |
| **Enterprise Pain Point Exposed** | Policies, CRM notes, and spreadsheets use inconsistent terminology | Embeddings unify meaning across heterogeneous data sources |

## Goals

- Natural-language semantic search with 90%+ relevance on test queries
- Sub-second query latency
- Extensible data ingestion with minimal configuration per new source
- Production-ready, modular codebase with clear documentation

## Key Features

- **Ingestion & Preprocessing**
  - **YAML-driven configuration** — tier (Basic/Standard/Premium), embedding backend/model, per-source display layout, and server settings in `config/app.yaml` and `config/sources/*.yaml`; no Python edits required to customise a deployment
  - **Pluggable data ingestion connectors** — CSV, SQL, JSON, XML, REST API, and MongoDB adapters normalise records into a shared schema for the embedding pipeline (see `developer/pluggable_data_sources.md`)
  - **Text preprocessing pipeline** — `TextCleaner` (HTML strip, Unicode normalisation, whitespace collapse), `TextChunker` (word-boundary splits with configurable size/overlap), and `PreprocessingPipeline` wiring them together with optional opt-in per stage
  - **Unified index builder** — `scripts/generate_index.py` reads YAML configs and builds a combined multi-source index in one command
- **Embeddings & Vector Stores**
  - **Pluggable embedding providers** — AWS Bedrock, Spot-hosted open-source models, and SageMaker; model + dimension auto-resolved from presets. SageMaker pairs with HuggingFace containers to serve **domain-specific fine-tuned embedding models** — organisations in legal, medical, or financial verticals can deploy a model trained on their own corpus (case law, clinical notes, SEC filings) and route the platform to that endpoint via `endpoint_name` configuration, with no changes to ingestion, vector storage, or search logic
  - **Multiple vector stores** — FAISS, Qdrant, or pgvector
- **Runtime & Deployment**
  - **Natural-language search** across CSV, SQL, JSON, and API data sources
  - **Flexible deployment** — ECS/Fargate or Lambda, toggled via Terraform configuration
  - **FastAPI runtime & CLI tooling** — container-ready REST service with a shared command-line client for validation and smoke tests
  - **Validation UI** — self-contained single-page web interface served at `/ui` for issuing queries during local development and deployment validation
  - **React Web UI** — React 18 + TypeScript SPA (`frontend/`) with search bar, result cards, dynamic filter panel, pagination, and an optional Premium-tier analytics sidebar; served via S3 + CloudFront or a `StaticFiles` mount on the same container
- **Security & Observability**
  - **Security hardening** — IAM least-privilege permission boundaries, KMS customer-managed keys with auto-rotation for S3/SQS/SNS encryption, CloudTrail audit logging, VPC interface endpoints (Bedrock, ECR, CloudWatch Logs, SQS, SNS) to keep traffic off the public internet, and configurable HTTPS-only egress restrictions on all service security groups
  - **Observability tooling** — Terraform-provisioned CloudWatch dashboards, metrics, alarms, and SNS notifications for end-to-end runtime monitoring

## Performance Characteristics

The runtime targets P95 ≤ 1 s end-to-end, with CloudWatch alarms firing at 900 ms to catch regressions before they impact users. The current `NumpyVectorStore` uses an O(n) brute-force similarity scan, which remains suitable for moderate-scale indexes and should transition to FAISS, pgvector, or Qdrant as volumes grow. The bundled Locust harness validates all three SLOs (latency, error rate, throughput) in both interactive and CI-driven modes to ensure performance stays within bounds.

## Security Model Summary

All traffic stays inside the project VPC—services sit on private subnets behind ALB/API Gateway front doors, and S3, Bedrock, SQS, and SNS are accessed through VPC interface endpoints so no control-plane calls leave AWS networking. Embeddings and index artefacts are stored in KMS-encrypted buckets and queues with per-service IAM roles, and the embedding pipeline writes through permission-scoped policies that prevent direct bucket access. IAM permission boundaries plus deny guardrails wrap every runtime role, blocking lateral movement or privilege escalation even if a container is compromised.

## Architecture Overview

1. **Data Ingestion Layer** — Pluggable extractors normalize source data (CSV, SQL, JSON, API) and emit canonical records to S3.
2. **Preprocessing** — Python pipeline for text cleaning, field selection, and chunking, fully driven by YAML configuration (see the `preprocessing` block in `config/app.yaml` with env-var overrides).
3. **Embedding Provider Interface** — Configurable adapters for AWS Bedrock, Spot-hosted models, or SageMaker endpoints; selected via `var.embedding_backend`.
4. **Vector Store** — FAISS (on ECS), Qdrant, or pgvector; selected via Terraform module parameters.
5. **Search Service Runtime** — Containerized FastAPI deployable to ECS/Fargate or Lambda, toggled by `var.search_runtime`.
6. **Client Interfaces** — REST API, CLI, and optional web UI.
7. **Observability** — CloudWatch logging, metrics, alarms, and dashboards.

```
Data Sources → Ingestion → Preprocessing → Embedding → Vector Store → Search API → Results
(CSV/SQL/JSON/API)                        (Bedrock/     (FAISS/Qdrant/  (REST/CLI/UI)
                                           Spot/         pgvector)
                                           SageMaker)
```

See `docs/PRD-semantic-search.md` for the product requirements.

## Phase Progress

- **Phase 0 — Planning & Alignment:** Complete. Goals, scope, and architectural direction are captured in the PRD, technical approach, and agent guidelines.
- **Phase 1 — Foundation & Infrastructure:** Complete. Terraform scaffolding, runtime/embedding toggles, and container pipeline documentation are in place, enabling Phase 2 ingestion work.
- **Phase 2 — Data Ingestion Layer:** Complete. Pluggable connectors, canonical schema normalisation, and ingestion observability are in place to supply embedding pipelines.
- **Phase 3 — Embedding & Vector Services:** Complete. Bedrock, Spot, and SageMaker adapters implemented; NumPy vector store with cosine/L2/inner-product metrics, persistence, and idempotent upserts delivered; end-to-end embedding pipeline with two-phase S3 backup and resilient error handling wired; 50 tests passing.
- **Phase 4 — Search Runtime & Interfaces:** Complete. FastAPI REST API, CLI, and lightweight validation UI (`/ui`) delivered; full Terraform modules for Fargate and Lambda runtimes, observability module (dashboards/alarms/log widgets), example tfvars, and deployment runbook in place; 67 tests passing. Environment `terraform apply` and smoke-test validation pending.
- **Phase 5 — Quality & Launch Readiness:** Complete. Relevance evaluation suite (`semantic-search-eval` CLI, 5 IR metrics, 54 new tests); Locust load test harness with acceptance criteria; cost optimisation guide; client deployment playbook and Terraform variable reference; 121 tests passing.
- **Deployment — AWS Fargate (dev):** Complete. 53 resources provisioned via `terraform apply`; container image (~85 MB) built and pushed to ECR via CodeBuild; `GET /healthz → 200`; git tag `runtime-v0.1.0` created. `/readyz → 503` until a FAISS index is uploaded to S3.
- **Phase 6 — Web UI:** Complete. React 18 + TypeScript SPA in `frontend/` with SearchBar, ResultCard, FilterPanel, Pagination, AnalyticsPanel, and hooks (useSearch, useConfig, useAnalytics, useDebounce). Tier-gated analytics panel via `GET /v1/config`. 15 component tests (Vitest + RTL). Production build in `frontend/dist/`.
- **feature/data-abstraction — Data Abstraction & Preprocessing:** Complete. Six pluggable connectors (`ingestion/` package: CSV, SQL, JSON/JSONL, XML, REST API, MongoDB), text preprocessing pipeline (`preprocessing/` package: TextCleaner, TextChunker, PreprocessingPipeline), sample dataset (`data/sample.csv`), index generation scripts (`scripts/generate_csv_index.py`, `scripts/generate_pg_index.py`), three validation runner scripts (`test_spot_csv_server.sh`, `test_bedrock_json_server.sh`, `test_bedrock_pg_server.sh`), functional process flow doc, and 9 PR review fixes applied. Test suite: 208 passing.
- **feature/config_enhancements — Configuration Externalization:** Complete. YAML-driven configuration system (`semantic_search/config/` package) with `config/app.yaml` for tier/embedding/server settings and `config/sources/*.yaml` for per-source connector + display configuration. Three-tier feature matrix (Basic/Standard/Premium), model presets with auto-dimension resolution, unified `scripts/generate_index.py`, `--config`/`--app-config` flags on all generate scripts, extended `/v1/config` endpoint, config-driven frontend rendering, and full backward compatibility. Test suite: 261 passing (51 new config tests).
- **Phase 7 — Preprocessing Integration & Live Search Activation:** Complete. `PreprocessingConfig` dataclass and `build_preprocessing_pipeline()` factory added to `semantic_search/config/app.py` with full `PREPROCESSING_*` env-var override support; `PreprocessingPipeline` wired into all five generate scripts (applied after connector extraction, before embedding); `--no-preprocessing` flag on every script. `Dockerfile` upgraded to a 3-stage multi-stage build (Node 20 frontend builder + Python builder + slim runtime) so `ENABLE_UI=true` serves the React SPA at `/` in a single container. Index build runbook added (`docs/runbooks/index_build.md`). Test suite: 292 passing (24 new wiring tests + 7 config tests).

## Live Environment (dev)

| Resource | Value |
|---|---|
| ALB endpoint | `http://<alb-dns-name>.us-east-1.elb.amazonaws.com` |
| ECR image | `<aws-account-id>.dkr.ecr.<region>.amazonaws.com/semantic-search:main` |
| ECS cluster | `<project>-dev-search-cluster` |
| FAISS index bucket | `s3://<project>-dev-faiss-index/vector_store/current/` |

> `/readyz` returns 503 until a FAISS index is uploaded to the bucket above and `VECTOR_STORE_PATH` is set in the task definition.

## Uploading a FAISS Index to S3

The runtime loads its vector index from a local directory path (`VECTOR_STORE_PATH`). For ECS/Fargate deployments the index must first be uploaded to S3, then that S3 path must be referenced when the container starts.

The index consists of exactly two files produced by `NumpyVectorStore.save()`:
- `vectors.npy` — float32 matrix of all record vectors
- `metadata.json` — record IDs, metadata, dimension, and metric

### Step 1 — Build the index locally

```bash
# Config-driven (all sources in config/sources/)
uv run python scripts/generate_index.py --output ./my_index

# Or for a single CSV source
uv run python scripts/generate_csv_index.py --output ./my_index
```

### Step 2 — Upload to S3

```bash
BUCKET=<project>-dev-faiss-index
PREFIX=vector_store/current

aws s3 cp ./my_index/vectors.npy  s3://$BUCKET/$PREFIX/vectors.npy
aws s3 cp ./my_index/metadata.json s3://$BUCKET/$PREFIX/metadata.json
```

Verify the upload:

```bash
aws s3 ls s3://$BUCKET/$PREFIX/
# Should show vectors.npy and metadata.json
```

### Step 3 — Point the runtime at the index

The runtime expects a **local** path. For ECS/Fargate, add an entrypoint script or an init container that syncs from S3 before the server starts:

```bash
# In your container entrypoint / task startup script
aws s3 sync s3://$BUCKET/$PREFIX /opt/index
export VECTOR_STORE_PATH=/opt/index
uv run python main.py
```

Alternatively, set `VECTOR_STORE_PATH` to the S3 URI directly only if your deployment wraps `main.py` with an S3-download step (see `docs/runbooks/runtime_deploy.md`).

### Step 4 — Confirm readiness

```bash
curl http://<alb-dns-name>.us-east-1.elb.amazonaws.com/readyz
# {"status": "ready"}  ← 200 once the index is loaded
```

> **Automatic S3 backup:** If you pass `s3_bucket` and `s3_prefix` to `EmbeddingPipeline`, the pipeline uploads the index automatically after each build using a two-phase staged upload (timestamped prefix + `latest` pointer). See `semantic_search/pipeline/embedding_pipeline.py` for details.

## Tech Stack

- **Python** 3.12+
- **AWS Bedrock** / SentenceTransformers / SageMaker (embeddings)
- **FAISS** / **Qdrant** / **pgvector** (vector storage)
- **Terraform** (modular infrastructure-as-code)
- **AWS** ECS/Fargate, Lambda, S3, CloudWatch
- **LangChain** (optional orchestration)

## Prerequisites

- Python >= 3.12.12
- AWS account with appropriate access
- Terraform (for infrastructure provisioning)

## Getting Started

```bash
# Clone the repository
git clone <repo-url>
cd semantic-search

# Install dependencies
uv sync

# Run tests
uv run pytest

# Build a config-driven index from all sources in config/sources/
uv run python scripts/generate_index.py

# Start the server (reads config/app.yaml automatically)
VECTOR_STORE_PATH=./vector_index uv run python main.py

# Start without a vector store (/readyz returns 503 until an index is loaded)
uv run python main.py

# Start the React web UI dev server (proxies /v1/* to localhost:8000)
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

## Project Structure

```
.
├── main.py                  # Application entry point
├── pyproject.toml           # Project metadata and dependencies
├── frontend/                # React 18 + TypeScript web UI
│   ├── src/
│   │   ├── components/      # SearchBar, ResultCard, FilterPanel, Pagination, AnalyticsPanel
│   │   ├── hooks/           # useSearch, useConfig, useAnalytics, useDebounce
│   │   ├── types/           # TypeScript types mirroring FastAPI Pydantic models
│   │   └── App.tsx
│   ├── dist/                # Production build output
│   ├── vite.config.ts       # /v1 proxy to FastAPI, Tailwind v4 plugin
│   └── package.json
├── config/
│   ├── app.yaml             # Tier, embedding backend/model, server settings
│   ├── sources/             # Per-source YAML configs (connector + display)
│   └── examples/            # Example app profiles (basic, premium, bedrock, sagemaker)
├── data/
│   └── sample.csv           # 20-row sample dataset for local development
├── semantic_search/
│   ├── config/              # Configuration dataclasses, YAML loaders, model presets
│   ├── embeddings/          # Provider interface, Bedrock/Spot/SageMaker adapters, factory
│   ├── evaluation/          # Relevance evaluation suite (EvalQuery, metrics, CLI)
│   ├── ingestion/           # Pluggable connectors (CSV, SQL, JSON, XML, API, MongoDB) + factory
│   ├── pipeline/            # EmbeddingPipeline (provider → vector store → S3)
│   ├── preprocessing/       # TextCleaner, TextChunker, PreprocessingPipeline
│   ├── runtime/             # FastAPI search service, CLI tooling
│   └── vectorstores/        # NumpyVectorStore (L2, cosine, inner-product)
├── scripts/
│   ├── generate_index.py          # Unified config-driven multi-source index builder
│   ├── generate_csv_index.py      # Build NumpyVectorStore from CSV via Spot embeddings
│   ├── generate_pg_index.py       # Build NumpyVectorStore from PostgreSQL via Spot embeddings
│   ├── generate_json_index.py     # Build NumpyVectorStore from JSON/JSONL via Spot embeddings
│   └── generate_mongo_index.py    # Build NumpyVectorStore from MongoDB via Spot embeddings
├── tests/
│   ├── config/              # Configuration loader and model preset tests
│   ├── embeddings/          # Unit tests for all embedding providers
│   ├── evaluation/          # Relevance evaluation tests
│   ├── ingestion/           # Connector tests (CSV, SQL, JSON, XML, API, MongoDB)
│   ├── load/                # Locust load test harness
│   ├── pipeline/            # Embedding pipeline tests
│   ├── preprocessing/       # TextCleaner, TextChunker, PreprocessingPipeline tests
│   ├── runtime/             # Search API and CLI tests
│   └── vectorstores/        # Vector store tests
├── test_bedrock_json_server.sh  # Validation runner: Bedrock + JSON index
├── test_bedrock_pg_server.sh    # Validation runner: Bedrock + PostgreSQL index
└── test_spot_csv_server.sh      # Validation runner: Spot + CSV index
├── docs/
│   ├── cost_optimisation.md # Cost sizing and tuning guidance
│   └── process_flows/       # End-to-end process diagrams (01–06)
├── developer/
│   ├── technical_approach.md
│   ├── project_status.md
│   ├── container_pipeline.md
│   ├── developer-journal.md
│   ├── functional_process_flow.md  # Mermaid diagram of full ingestion→search pipeline
│   ├── guides/              # Tier deployment, data & testing guides
│   ├── handoff/             # Deployment playbook & Terraform variable reference
│   └── runbooks/            # Operational runbooks (runtime deployment, rollback)
├── infrastructure/          # Terraform modules and dev environment
├── github/                  # ISSUES and PRs tracking docs
├── AGENTS.md                # Agent coding guidelines and project context
└── README.md
```

## Key Configuration

Application configuration is managed through YAML files in `config/`:

- `config/app.yaml` — tier (`basic`/`standard`/`premium`), embedding backend/model, server settings
- `config/sources/*.yaml` — per-source connector type, field mapping, and UI display layout
- Env vars override YAML values (precedence: env var > YAML > built-in default)
- See `config/README.md` for the full schema reference

Infrastructure is managed through Terraform variables:

- `var.search_runtime` — `"fargate"` or `"lambda"`
- `var.embedding_backend` — selects embedding provider (Bedrock, Spot, SageMaker)
- `var.ingestion_mode` — `"batch"` (default) or `"stream"`

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

## Documentation

- [Product Requirements](docs/PRD-semantic-search.md)
- [Technical Approach](developer/technical_approach.md)
- [Project Status](developer/project_status.md)
- [Process Flow & Configuration Toggles](developer/process-flow.md)
- [Container Build & Deployment](developer/container_pipeline.md)
- [Runtime Deployment Runbook](developer/runbooks/runtime_deploy.md)
- [Index Build Runbook](developer/runbooks/index_build.md)
- [Data Deployment & Testing Guide](developer/guides/data_and_testing_guide.md)
- [Configuration Reference](config/README.md)
- [Cost Optimisation Guide](docs/cost_optimisation.md)
- [Deployment Playbook](developer/handoff/deployment_playbook.md)
- [Terraform Variable Reference](developer/handoff/terraform_variable_reference.md)
- [Web UI (frontend/)](frontend/README.md)
- [Agent Guidelines](AGENTS.md)

## License

TBD