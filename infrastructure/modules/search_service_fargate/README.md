# Search Service (Fargate) Module

This module provisions the semantic search runtime on AWS Fargate. It builds an
ECS cluster, task definition, security boundaries, and an Application Load
Balancer (ALB) that exposes the FastAPI service implemented in
`semantic_search.runtime.api`. Autoscaling, logging, alarms, and request
configuration are baked in so environments can promote the same container image
across dev/staging/prod without rewriting infrastructure code.

---

## Responsibilities

- **Runtime Hosting** – Creates an ECS/Fargate service that runs the semantic
  search container with health and readiness probes aligned to `/healthz` and
  `/readyz`.
- **Traffic Management** – Deploys an ALB + target group pair, including
  security groups and HTTP listeners, to terminate client traffic and forward to
  the tasks.
- **Configuration Delivery** – Maps vector store, embedding, and pipeline
  metadata into environment variables and secrets for the container at launch
  time.
- **Observability** – Provisions CloudWatch log groups, request 5xx alarms, and
  optional tracing/query logging controls.
- **Autoscaling** – Configures CPU-based target tracking by default, with an
  optional request-per-target policy driven by ALB metrics.

---

## Module Structure

| Resource | Purpose |
| --- | --- |
| `aws_ecs_cluster` | Logical cluster for the runtime tasks. |
| `aws_ecs_task_definition` | Fargate task definition with container image, env vars, health checks. |
| `aws_ecs_service` | Manages task count, load balancer wiring, and deployments. |
| `aws_lb`, `aws_lb_target_group`, `aws_lb_listener` | Public ALB frontend routing HTTP traffic to the service. |
| `aws_security_group` (x2) | Isolates the service tasks and ALB ingress controls. |
| `aws_cloudwatch_log_group` | Central log destination (`/aws/ecs/<name>`). |
| `aws_appautoscaling_*` | CPU (and optional request-count) target tracking. |
| `aws_cloudwatch_metric_alarm` | Triggers on ALB 5xx bursts for operational awareness. |
| `aws_iam_role*` | Task and execution roles granting logging, secret access, and AWS API usage. |

---

## Inputs

| Variable | Type | Description |
| --- | --- | --- |
| `project` | `string` | Project identifier applied to names/tags. |
| `environment` | `string` | Environment label (`dev`, `staging`, `prod`, …). |
| `name_prefix` | `string` | Optional override for generated resource names. |
| `tags` | `map(string)` | Additional tags merged into every resource. |
| `aws_region` | `string` | Region used for ECS/CloudWatch logging references. |
| `vpc_id` | `string` | VPC where the service is deployed. |
| `subnet_ids` | `list(string)` | Private subnets for Fargate ENIs. |
| `public_subnet_ids` | `list(string)` | Public subnets used by the ALB. |
| `additional_security_group_ids` | `list(string)` | Extra security groups attached to the ECS service. |
| `allowed_ingress_cidrs` | `list(string)` | Source CIDRs allowed into the ALB (default `["0.0.0.0/0"]`). |
| `container_image` | `string` | OCI image URI produced by the container pipeline. |
| `cpu_architecture` | `string` | CPU architecture (`X86_64` or `ARM64`). |
| `cpu` | `number` | Task CPU (e.g., `1024`). |
| `memory` | `number` | Task memory in MiB (e.g., `2048`). |
| `container_port` | `number` | Exposed container port (defaults to `8080`). |
| `desired_count` | `number` | Initial task count managed by ECS. |
| `min_capacity` / `max_capacity` | `number` | Autoscaling bounds for task count. |
| `assign_public_ip` | `bool` | Whether tasks receive public IPs (default `false`). |
| `platform_version` | `string` | Fargate platform version (`LATEST` by default). |
| `log_retention_in_days` | `number` | CloudWatch log retention (default `14`). |
| `environment_variables` | `map(string)` | Extra plain-text env vars merged into container configuration. |
| `secret_arn_values` | `map(string)` | Mapping of env var name → Secrets Manager ARN. |
| `vector_store_endpoint` | `string` | Endpoint exported by the active vector store module. |
| `embedding_endpoint` | `string` | Endpoint exported by the selected embedding provider module. |
| `ingestion_queue_arn` | `string` | SQS queue used for on-demand reindex triggers. |
| `reindex_topic_arn` | `string` | SNS topic broadcast for cross-service reindex coordination. |
| `log_level` | `string` | Default application log level (`INFO`, `DEBUG`, etc.). |
| `metrics_namespace` | `string` | Namespace used by the service for custom metrics. |
| `enable_request_tracing` | `bool` | Toggles request-level trace headers/logging. |
| `enable_query_logging` | `bool` | Enables structured query logging for analytics. |
| `max_concurrent_queries` | `number` | Application-level concurrency guard (passed as env var). |
| `default_top_k` | `number` | Default search result count presented to API/CLI clients. |
| `max_top_k` | `number` | Hard limit on results per query. |
| `candidate_multiplier` | `number` | Candidate pool multiplier prior to filter application. |
| `healthcheck_path` | `string` | Container liveness endpoint (default `/healthz`). |
| `readiness_path` | `string` | Container readiness endpoint (default `/readyz`). |
| `healthcheck_interval_seconds` | `number` | ALB health check interval. |
| `healthcheck_timeout_seconds` | `number` | ALB health check timeout. |
| `healthcheck_healthy_threshold` | `number` | Success threshold for ALB health checks. |
| `healthcheck_unhealthy_threshold` | `number` | Failure threshold for ALB health checks. |
| `healthcheck_unhealthy_threshold` | Number of consecutive failures required before a target is unhealthy. |
| `alarm_http_5xx_threshold` | ALB 5xx count that triggers the CloudWatch alarm. |
| `startup_timeout_seconds` | Grace period before declaring startup failure. |
| `shutdown_timeout_seconds` | Grace period for container shutdown hooks. |
| `enable_request_based_scaling` | Toggle for the optional ALB RequestCount autoscaling policy. |
| `autoscaling_cpu_target` | CPU utilization target (percentage). |
| `autoscaling_requests_per_target` | Request count target when request-based scaling is enabled. |
| `scale_in_cooldown_seconds` / `scale_out_cooldown_seconds` | Cooldown periods for autoscaling reactions. |

### Runtime Environment Variables

The container receives a consistent set of environment variables so the FastAPI runtime can bootstrap itself without additional wiring:

- `VECTOR_STORE_ENDPOINT`, `EMBEDDING_ENDPOINT` — Connection metadata exported by the selected vector store and embedding modules.
- `INGESTION_QUEUE_ARN`, `REINDEX_TOPIC_ARN` — Eventing hooks used for on-demand index refresh workflows.
- `LOG_LEVEL`, `METRICS_NAMESPACE`, `ENABLE_REQUEST_TRACING`, `ENABLE_QUERY_LOGGING` — Observability controls aligned with project defaults.
- `MAX_CONCURRENT_QUERIES`, `DEFAULT_TOP_K`, `MAX_TOP_K`, `CANDIDATE_MULTIPLIER` — Search runtime behaviour knobs surfaced as module variables.
- `HEALTHCHECK_PATH`, `READINESS_PATH`, `STARTUP_TIMEOUT_SECONDS`, `SHUTDOWN_TIMEOUT_SECONDS` — Liveness configuration shared with the load balancer and autoscaler.

These variables mirror the configuration schema exposed by `semantic_search.runtime.api`, ensuring the same container can run behind either Fargate or Lambda without code changes.

---

## Outputs

| Output | Description |
| --- | --- |
| `cluster_id` | ECS cluster identifier. |
| `service_name` | ECS service name (used by observability and downstream modules). |
| `task_role_arn` | IAM role assumed by runtime tasks. |
| `execution_role_arn` | IAM role used by ECS to pull images and emit logs. |
| `load_balancer_dns` | Public DNS name of the ALB fronting the service. |
| `target_group_arn` | ARN of the target group associated with the service. |
| `log_group_name` | CloudWatch Log Group capturing application logs. |

---

## Usage

1. **Select Runtime Toggle**  
   In `infrastructure/environments/<env>/main.tf`, set `var.search_runtime = "fargate"`.
   The environment stack will include this module with derived inputs from the core
   network, embedding provider, and vector store selections.

2. **Provide Container Image**  
   Supply the image URI exported by the shared container pipeline (see
   `developer/container_pipeline.md`). This image must expose the FastAPI server
   on the configured port.

3. **Wire Environment & Secrets**  
   Use `environment_variables` for non-sensitive configuration and
   `secret_arn_values` for API keys or credentials stored in Secrets Manager.

4. **Deploy**  
   Run your usual Terraform workflow (`terraform init/plan/apply`). The module
   creates all necessary ECS, IAM, and ALB resources under a consistent naming
   scheme: `<project>-<environment>-search-*`.

5. **Monitor & Scale**  
   - CloudWatch logs stream to `/aws/ecs/<name-prefix>`.
   - An alarm on ALB target 5xx count is pre-configured for basic alerting.
   - CPU target tracking autoscaling is active by default; set
     `enable_request_based_scaling = true` to also scale on ALB request rates.

---

## Security & Networking

- Tasks run in private subnets and only accept traffic from the ALB security
  group.
- Outbound access is unrestricted by default (`0.0.0.0/0` egress). Scope this
  further if the runtime can rely on VPC endpoints.
- Execution roles grant minimal permissions (logging + optional secrets access).
  Extend the task role with additional policies if the runtime must contact
  other AWS services (e.g., S3 backups, vector store APIs).

---

## Observability

- Logs: CloudWatch log group named `/aws/ecs/<project>-<env>-search`.
- Metrics/Alarms: ALB request and HTTP 5xx metrics plus autoscaling targets are
  available out of the box. Enhance the `metrics_namespace` and structured
  logging to integrate with the global `observability` module dashboards.
- Tracing: Enable application-level tracing by setting
  `enable_request_tracing = true` and ensuring the container emits trace headers.

---

## Operational Tips

- **Blue/Green Releases** – Adopt ECS deployment circuit breakers or weighted
  target groups for zero-downtime rollouts.
- **Scaling Boundaries** – Set `min_capacity` >= 2 in production to maintain
  availability during updates. Ensure `max_capacity` aligns with vector store
  throughput and embedding latency budgets.
- **Request Logging** – Keep `enable_query_logging` disabled by default in
  production unless audit requirements mandate query capture.

---

## Related Documentation

- `developer/container_pipeline.md` – Building and publishing the runtime image.
- `AGENTS.md` – Phase checklist and toggles for search runtime delivery.
- `developer/project_status.md` – Phase tracking and outstanding Phase 4 tasks.
- `semantic_search/runtime/api.py` – Application server entry point exposed by
  this module.