# Search Service (Lambda) Module

This module deploys the semantic search runtime as an AWS Lambda function backed by
an HTTP API Gateway endpoint. It packages the FastAPI application built in
`semantic_search.runtime.api` into a serverless footprint with optional VPC
networking, provisioned concurrency, and observability hooks that mirror the
Fargate deployment profile.

---

## Responsibilities

- **Runtime Hosting** – Creates a Lambda function from the shared container image,
  wiring environment variables and secrets to match the embedding/vector-store configuration.
- **API Exposure** – Provisions an HTTP API Gateway with routes for `/v1/search`,
  `/healthz`, and `/readyz`, forwarding requests to the Lambda runtime.
- **Networking** – Optionally attaches the function to private subnets and security
  groups when access to VPC-only resources (e.g., RDS, internal services) is required.
- **Scaling & Latency Controls** – Supports provisioned concurrency, configurable
  memory/timeout settings, and tailored throttling alarms to keep latency predictable.
- **Observability** – Emits logs to CloudWatch (function and API Gateway), publishes
  metrics/alarms, and integrates with AWS X-Ray when enabled.

---

## Module Layout

| Resource                                    | Purpose                                                 |
|---------------------------------------------|---------------------------------------------------------|
| `aws_lambda_function`                       | Runs the semantic search runtime container.             |
| `aws_iam_role` + policies                   | Grants logging, VPC, and secret access permissions.     |
| `aws_apigatewayv2_api` + routes/stage       | Exposes HTTP endpoints for search and health checks.    |
| `aws_cloudwatch_log_group`                  | Captures Lambda and API Gateway logs.                   |
| `aws_cloudwatch_metric_alarm`               | Monitors throttles for proactive alerting.              |
| `aws_lambda_provisioned_concurrency_config` | (Optional) Keeps warm executions for low-latency calls. |

---

## Inputs

| Variable | Description |
| --- | --- |
| `project`, `environment`, `name_prefix`, `tags` | Naming and tagging controls. |
| `container_image` | OCI image URI produced by the shared container pipeline. |
| `lambda_architecture` | CPU architecture (`x86_64` or `arm64`). |
| `timeout_seconds`, `memory_mb` | Lambda runtime sizing parameters. |
| `enable_ephemeral_storage`, `ephemeral_storage_mb` | Custom `/tmp` storage allocation. |
| `enable_provisioned_concurrency`, `provisioned_concurrency_count` | Provisioned concurrency settings. |
| `vector_store_endpoint`, `embedding_endpoint` | Connection metadata injected into the runtime. |
| `ingestion_queue_arn`, `reindex_topic_arn` | Eventing hooks for reindex workflows. |
| `log_level`, `metrics_namespace` | Logging and metrics configuration. |
| `enable_request_tracing`, `enable_query_logging` | Feature flags for tracing and analytics. |
| `max_concurrent_queries`, `default_top_k`, `max_top_k`, `candidate_multiplier` | Runtime tuning knobs. |
| `healthcheck_path`, `readiness_path` | Health endpoints exposed via API Gateway. |
| `environment_variables`, `secret_arn_values` | Additional plain-text env vars and Secrets Manager values. |
| `log_retention_in_days` | CloudWatch log retention policy. |
| `api_gateway_timeout_ms`, `api_gateway_stage` | API Gateway integration behaviour. |
| `xray_tracing_mode` | X-Ray tracing (`PassThrough` or `Active`). |
| `alarm_throttle_threshold` | CloudWatch alarm threshold for throttled invocations. |
| `vpc_id`, `subnet_ids`, `additional_security_group_ids` | Optional VPC configuration for the Lambda runtime. |

### Runtime Environment Variables

The container image loads a consistent set of environment variables so the Lambda runtime can boot without manual wiring:

- `VECTOR_STORE_ENDPOINT`, `EMBEDDING_ENDPOINT` — Connection metadata originating from the selected vector store and embedding provider modules.
- `INGESTION_QUEUE_ARN`, `REINDEX_TOPIC_ARN` — Event channels used to trigger index refresh jobs across services.
- `LOG_LEVEL`, `METRICS_NAMESPACE`, `ENABLE_REQUEST_TRACING`, `ENABLE_QUERY_LOGGING` — Observability toggles that align with the FastAPI runtime defaults.
- `MAX_CONCURRENT_QUERIES`, `DEFAULT_TOP_K`, `MAX_TOP_K`, `CANDIDATE_MULTIPLIER` — Search-specific tuning knobs surfaced as module inputs.
- `HEALTHCHECK_PATH`, `READINESS_PATH` — The health endpoints exposed through API Gateway so upstream monitors stay consistent with the Fargate deployment profile.

The Lambda module mirrors the configuration schema documented in `semantic_search.runtime.api`, enabling the same container artifact to operate behind either Lambda or Fargate with only Terraform variable changes.

---

## Outputs

| Output | Description |
| --- | --- |
| `function_arn`, `function_name` | Identifiers for the Lambda runtime. |
| `api_endpoint` | Public HTTPS endpoint exposed via API Gateway. |
| `log_group_name` | CloudWatch log group for Lambda execution logs. |
| `security_group_id` | Security group applied to Lambda ENIs (when VPC-enabled). |

---

## Usage Workflow

1. **Select Runtime Toggle**  
   In the environment stack (e.g., `infrastructure/environments/dev`), set
   `search_runtime = "lambda"` to activate this module instead of the Fargate variant.

2. **Provide Container Artifact**  
   Build and push the semantic search runtime image via the shared container pipeline
   (`developer/container_pipeline.md`) and pass the resulting URI to `container_image`.

3. **Configure Environment & Secrets**  
   Supply runtime configuration using `environment_variables` (non-sensitive) and
   `secret_arn_values` for credentials stored in AWS Secrets Manager.

4. **Optionally Attach to VPC**  
   Populate `vpc_id` and `subnet_ids` when the Lambda function must communicate with
   private resources such as RDS/pgvector or internal services.

5. **Tune Performance**  
   - Enable provisioned concurrency for latency-sensitive deployments.
   - Adjust memory/timeout to match workload characteristics.
   - Use `alarm_throttle_threshold` to alert when throttles occur.

6. **Deploy**  
   Execute your standard Terraform workflow (`init/plan/apply`). The module
   outputs the API endpoint and function identifiers for downstream integration
   (CLI smoke tests, observability, documentation updates).

---

## Observability & Operations

- **Logging:** Lambda execution logs live in `/aws/lambda/<name-prefix>`, while API
  Gateway access logs stream to `/aws/apigateway/<name-prefix>`.
- **Metrics:** Lambda publishes invocation, duration, and error metrics by default.
  Custom metrics use the namespace defined by `metrics_namespace`.
- **Tracing:** Set `xray_tracing_mode = "Active"` and enable request tracing in the
  runtime to capture end-to-end traces.
- **Alerts:** The provided throttle alarm is a starting point—extend with latency
  and error-rate alarms to satisfy SLA/SLO commitments.

---

## Alignment with Project Phases

- **Phase 4 — Search Runtime & Interfaces:** Implements the Lambda runtime path,
  mirroring Fargate responsibilities while optimising for cold-start and cost control.
- **Phase 5 — Quality & Launch Readiness:** Exercises load testing, relevance
  evaluation, and documentation handoffs using the outputs from this module.

---

## Related References

- `developer/container_pipeline.md` – Building/publishing the runtime container.
- `AGENTS.md` – Phase checkpoints and delivery expectations for the search runtime.
- `developer/project_status.md` – Current progress and outstanding Phase 4 tasks.
- `semantic_search/runtime/api.py` – FastAPI application surfaced by this module.