# Semantic Search Runtime Deployment Runbook

## Purpose

Provide a repeatable procedure for deploying, validating, and rolling back the semantic search runtime in the dev environment for both ECS/Fargate and Lambda execution modes. This runbook covers:

- Preparing deployment artifacts and Terraform variables
- Running `terraform plan` / `terraform apply`
- Smoke-testing API endpoints and autoscaling hooks
- Switching between runtime modes
- Instrumenting observability
- Executing rollback procedures

---

## Preconditions

1. **Access & Tooling**
   - AWS CLI authenticated against the target account with privileges for ECS, Lambda, API Gateway, CloudWatch, IAM, S3, SQS, SNS, and Secrets Manager.
   - Terraform `>= 1.5.0` installed locally or available in CI.
   - `uv` virtual environment ready for running smoke tests and CLI validation.

2. **Artifact Availability**
   - Container image for the runtime published to ECR (e.g., `123456789012.dkr.ecr.us-east-1.amazonaws.com/semantic-search:main`).
   - Runtime configuration secret stored in AWS Secrets Manager containing API credentials, vector store connection strings, etc.

3. **Variable Files**
   - Populate `infrastructure/environments/dev/examples/fargate.tfvars.example` and `lambda.tfvars.example` with real account identifiers, CIDR blocks, and secret ARNs.
   - Copy the relevant example to `terraform.tfvars` (or supply via `-var-file`) before applying:
     ```sh
     cp infrastructure/environments/dev/examples/fargate.tfvars.example infrastructure/environments/dev/terraform.tfvars
     ```

4. **State Safety**
   - Confirm no concurrent Terraform operations are running (check state lock if using remote backends).
   - Backup `terraform.tfstate` if operating locally.

---

## Step 1 — Initialize Terraform

From `infrastructure/environments/dev`:

```sh
terraform init
terraform fmt -check
terraform validate
```

---

## Step 2 — Deploy Fargate Runtime

1. **Set Runtime Mode**
   - Ensure `search_runtime = "fargate"` in the active tfvars.

2. **Plan**
   ```sh
   terraform plan -out=tfplan.fargate
   ```

3. **Apply**
   ```sh
   terraform apply tfplan.fargate
   ```

4. **Outputs to Capture**
   - `search_service_endpoint`
   - `search_service_name` (ECS service)
   - `search_service_runtime_log_group_name`
   - `load_balancer_dns`, `load_balancer_arn_suffix`, `target_group_arn_suffix`

---

## Step 3 — Fargate Validation Checklist

| Check | Command / Observation | Expected Result |
|-------|-----------------------|-----------------|
| Health endpoint | `curl http://<load_balancer_dns>/healthz` | HTTP 200 JSON payload |
| Readiness endpoint | `curl http://<load_balancer_dns>/readyz` | HTTP 200 |
| Search API smoke test | `uv run python -m semantic_search.runtime.cli --query "semantic search hello"` | JSON response with hits |
| ECS service status | AWS Console or `aws ecs describe-services` | Desired count matches running count; no failover deployments |
| CloudWatch logs | Inspect `/aws/ecs/*` log group | Structured JSON logs without errors |
| Autoscaling target | `aws application-autoscaling describe-scalable-targets` | `MinCapacity`, `MaxCapacity` match tfvars |
| ALB target health | `aws elbv2 describe-target-health` | Targets healthy |

---

## Step 4 — Observability Wiring

1. Confirm `module.search_service_fargate` outputs feed `module.observability`.
2. Verify CloudWatch Dashboard (`<project>-<environment>-observability-cw-dashboard`) renders:
   - Runtime P95 latency
   - Query error rate
   - SQS queue depth
   - Runtime log widgets
3. Confirm alarms (`*-search-latency-p95`, `*-search-error-rate`) exist and are in `OK` state.
4. If SNS notifications are configured, send a test alarm via `set-alarm-state`.

---

## Step 5 — Switch to Lambda Runtime (Optional Toggle)

1. **Update tfvars**
   - Set `search_runtime = "lambda"` and populate Lambda-specific variables (`lambda_container_image`, `lambda_enable_provisioned_concurrency`, etc.).
   - Adjust Fargate-only variables if desired (they will be ignored when `count = 0`).

2. **Plan & Apply**
   ```sh
   terraform plan -out=tfplan.lambda
   terraform apply tfplan.lambda
   ```

3. **Outputs to Capture**
   - `search_service_endpoint` (API Gateway URL)
   - `search_service_name` (Lambda function name)
   - `search_service_runtime_log_group_name`
   - `search_service_api_log_group_name`
   - `function_alias_arn` (if provisioned concurrency enabled)

---

## Step 6 — Lambda Validation Checklist

| Check | Command / Observation | Expected Result |
|-------|-----------------------|-----------------|
| Health endpoint | `curl https://<api_gateway>/healthz` | HTTP 200 |
| Readiness endpoint | `curl https://<api_gateway>/readyz` | HTTP 200 |
| Search API smoke test | `uv run python -m semantic_search.runtime.cli --endpoint https://<api_gateway>/v1/search --query "semantic search hello"` | JSON response with hits |
| Lambda concurrency | `aws lambda get-function-concurrency` | Matches provisioned concurrency settings |
| Lambda logs | `/aws/lambda/*` log group shows clean invocations |
| API Gateway logs | `/aws/apigateway/*` log group shows 2xx responses |
| Throttle alarm | Verify `*-throttles` alarm remains `OK` |

---

## Step 7 — Post-Deployment Tasks

1. **Update Documentation**
   - Record new endpoints and validation results in `developer/project_status.md` or project wiki.
2. **Notify Stakeholders**
   - Share change summary, including runtime mode, container tag, and validation outcomes.
3. **Tag Releases**
   - Tag the repository (`git tag runtime-vX.Y.Z`) corresponding to the deployment.
   - Optionally create a change request ticket referencing the terraform plan.

---

## Rollback Procedures

### Fargate Rollback

1. Revert tfvars to the previous known-good container image or configuration.
2. Run `terraform plan` and `terraform apply`.
3. If necessary, manually scale service to prior desired count:
   ```sh
   aws ecs update-service --cluster <cluster> --service <service> --desired-count <n>
   ```

### Lambda Rollback

1. Update `lambda_container_image` to prior image digest/tag or disable provisioned concurrency if causing issues.
2. Apply Terraform.
3. Alternatively, revert to Fargate by switching `search_runtime` back to `"fargate"` and re-applying.

### Emergency Disable

- Use `terraform apply -target=module.search_service_fargate` (or lambda equivalent) with `desired_count = 0` / `provisioned_concurrency_count = 0`.
- Disable upstream routing (ALB listener rule or API Gateway deployment) via AWS Console if immediate shutdown required.

---

## Troubleshooting Tips

- **Health Checks Failing (Fargate)**: Check container logs for startup exceptions; ensure secrets resolved via task role.
- **Lambda Cold Starts**: Increase provisioned concurrency or switch to Fargate for consistent latency.
- **Authentication Issues**: Validate Secrets Manager ARN mapping and ensure IAM roles have decrypt permissions (KMS policy alignment).
- **Metric Visibility**: Confirm runtime emits `QueryLatencyP95` and `QueryErrorRate`; update application config if missing.
- **Terraform Drift**: Run `terraform plan` regularly; enable state locking in remote backends to avoid concurrent writes.

---

## References

- `infrastructure/modules/search_service_fargate/README.md`
- `infrastructure/modules/search_service_lambda/README.md`
- `infrastructure/modules/observability/README.md`
- `developer/project_status.md`
- `developer/container_pipeline.md`
