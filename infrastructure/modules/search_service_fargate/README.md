# Search Service (Fargate) Module

This module provisions the semantic search runtime on AWS Fargate. It delivers a warm, autoscaled service designed to meet the sub-second latency goal defined in the product requirements while keeping deployment highly configurable via Terraform toggles.

---

## Responsibilities

- **Containerized API Service**: Runs the semantic search application in AWS Fargate tasks behind an Application Load Balancer (ALB).
- **Autoscaling & Health Checks**: Configures target tracking on CPU/memory or request count, plus health checks for graceful failover.
- **Networking & Security**: Attaches tasks to private subnets and security groups supplied by the core network module; supports egress through NAT or VPC endpoints.
- **Configuration Injection**: Pulls environment variables, Secrets Manager references, and feature toggles provided by higher-level stacks.
- **Observability Hooks**: Exposes CloudWatch log groups, metrics, and optional X-Ray tracing for centralized monitoring.

---

## Inputs (Recommended)

| Variable | Type | Description |
| --- | --- | --- |
| `project` | `string` | Project identifier used for naming and tagging (e.g., `semantic-search`). |
| `environment` | `string` | Environment label (`dev`, `staging`, `prod`). |
| `vpc_id` | `string` | VPC hosting the service. |
| `subnet_ids` | `list(string)` | Private subnets for the Fargate tasks. |
| `public_subnet_ids` | `list(string)` | Public subnets for the ALB (if applicable). |
| `security_group_ids` | `list(string)` | Security groups attached to tasks. |
| `container_image` | `string` | Image URI produced by the shared container pipeline (`developer/container_pipeline.md`). |
| `cpu` | `number` | Task CPU units (e.g., 1024). |
| `memory` | `number` | Task memory in MB (e.g., 2048). |
| `desired_count` | `number` | Initial task count (defaults to 2 for HA). |
| `max_count` | `number` | Maximum tasks allowed by autoscaling. |
| `vector_store_endpoint` | `string` | Connection endpoint for the active vector store module. |
| `embedding_endpoint` | `string` | Endpoint for embedding provider (Bedrock, Spot, SageMaker). |
| `ingestion_queue_arn` | `string` | SQS ARN for reindex or refresh events. |
| `reindex_topic_arn` | `string` | SNS topic ARN for cross-service notifications. |
| `environment_variables` | `map(string)` | Additional non-sensitive environment variables. |
| `secret_arns` | `list(string)` | Secrets Manager ARNs injected as environment variables. |
| `tags` | `map(string)` | Additional resource tags. |

---

## Outputs (Recommended)

| Output | Description |
| --- | --- |
| `service_name` | ECS service identifier for downstream references. |
| `cluster_id` | ECS cluster hosting the service. |
| `load_balancer_dns` | ALB DNS name for the semantic search API. |
| `task_role_arn` | IAM role assumed by tasks. |
| `execution_role_arn` | IAM role used by ECS to pull images and publish logs. |
| `log_group_name` | CloudWatch log group capturing application output. |

---

## Deployment Workflow

1. **Compose with Core Modules**  
   This module expects networking primitives from `modules/core_network` and data artifacts from `modules/data_plane`, `modules/vector_store`, and the selected `modules/embedding_*`.

2. **Provide Container Artifact**  
   Supply the image built via the shared container pipeline. The image must expose the API server entrypoint compatible with both ECS and Lambda runtimes (see `developer/container_pipeline.md`).

3. **Configure Autoscaling**  
   Default configuration uses target tracking on average CPU utilization (e.g., 60%). Override to request-count-based scaling when the ALB metrics are more predictive.

4. **Integrate Observability**  
   - Forward logs to CloudWatch with JSON structure.  
   - Optionally enable X-Ray or third-party solutions via sidecars or FireLens.  
   - Export key metrics (latency, 5xx rate) to the `observability` module.

5. **Expose Endpoints**  
   Application Load Balancer listeners (HTTP/HTTPS) are provisioned here or in a shared module; ensure certificates and routing rules match the environment’s networking guidelines.

---

## Alignment with Project Phases

- **Phase 0 — Planning & Alignment**  
  Document latency expectations, throughput targets, and compliance needs that justify Fargate over Lambda for certain deployments.

- **Phase 1 — Foundation & Infrastructure**  
  Scaffold this module, define variables/outputs, and document trade-offs relative to the Lambda module (`var.search_runtime`). Confirm compatibility with the shared container pipeline.

- **Phase 3 — Embedding & Vector Services**  
  Verify secure connectivity to selected embedding providers and vector stores via IAM roles and security groups.

- **Phase 4 — Search Runtime & Interfaces**  
  Deploy the API, connect client interfaces, and validate health checks, autoscaling, and monitoring alarms.

- **Phase 5 — Quality & Launch Readiness**  
  Run load/performance tests, failover simulations, and cost benchmarking (task hours, ALB usage) before go-live.

---

## Trade-offs vs. Lambda Runtime

| Aspect | Fargate Module | Lambda Module |
| --- | --- | --- |
| Latency | Predictable (warm tasks) | Potential cold starts unless provisioned concurrency |
| Cost | Higher floor (always-on tasks) | Pay-per-invoke, lower idle cost |
| Long-lived connections | Supported | Limited by Lambda timeouts |
| Operational control | Greater (autoscaling policies, task sizing) | Simpler (no server management) |
| Deployment artifact | Same container image | Same container image |

Use Terraform variable `var.search_runtime` to toggle between this module and `modules/search_service_lambda`, keeping the rest of the infrastructure unchanged.

---

## Future Enhancements

- Blue/green deployments via CodeDeploy or weighted target groups.
- gRPC/websocket support for real-time features.
- Service Mesh integration (e.g., AWS App Mesh) for advanced routing and observability.
- Custom scaling metrics (queue depth, p99 latency) to drive autoscaling policies.

---

## References

- Product requirements: `docs/PRD-semantic-search.md`  
- Technical approach: `developer/technical_approach.md`  
- Container pipeline: `developer/container_pipeline.md`  
- Project status tracking: `developer/project_status.md`  
- Agent guidelines: `AGENTS.md`
