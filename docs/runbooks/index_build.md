# Index Build & Upload Runbook

This runbook covers building a FAISS index from source data, uploading it to
S3, and activating live search on the deployed ECS service.

## Prerequisites

- AWS CLI configured with credentials for account `696056865313` (`us-east-1`).
- Python environment: `uv` available and `pyproject.toml` dependencies installed.
- For the Bedrock backend: IAM permissions for
  `bedrock:InvokeModel` on `amazon.titan-embed-text-v1`.
- For the PostgreSQL backend: `semantic_search_test` database accessible.
- For the Spot (local) backend: no AWS credentials required.

---

## 1. Build the index locally

### Option A — Unified config-driven builder (all sources)

```bash
uv run python scripts/generate_index.py \
  --config-dir ./config \
  --output ./vector_index
```

Override the embedding backend without editing YAML:

```bash
uv run python scripts/generate_index.py \
  --backend bedrock \
  --output ./vector_index
```

Skip preprocessing (embed raw text):

```bash
uv run python scripts/generate_index.py --no-preprocessing --output ./vector_index
```

### Option B — CSV (Spot backend, no AWS required)

```bash
uv run python scripts/generate_csv_index.py \
  --csv ./data/sample.csv \
  --output ./csv_spot_index
```

### Option C — PostgreSQL (Bedrock backend)

```bash
uv run python scripts/generate_pg_index.py \
  --region us-east-1 \
  --output ./pg_bedrock_index
```

### Verify the index

```bash
ls -lh ./vector_index/
# Expect: vectors.npy  metadata.json
```

---

## 2. Upload the index to S3

The ECS task reads from
`s3://semantic-search-dev-faiss-index/vector_store/current/`.

```bash
aws s3 cp ./vector_index/vectors.npy \
    s3://semantic-search-dev-faiss-index/vector_store/current/vectors.npy

aws s3 cp ./vector_index/metadata.json \
    s3://semantic-search-dev-faiss-index/vector_store/current/metadata.json
```

Verify the upload:

```bash
aws s3 ls s3://semantic-search-dev-faiss-index/vector_store/current/
```

---

## 3. Activate live search on ECS

### 3a. Update the task definition environment variable

Set `VECTOR_STORE_PATH` in `infrastructure/environments/dev/terraform.tfvars`:

```hcl
vector_store_path = "s3://semantic-search-dev-faiss-index/vector_store/current"
```

Apply the change:

```bash
cd infrastructure/environments/dev
terraform apply -auto-approve
```

### 3b. Force a new ECS deployment

```bash
aws ecs update-service \
  --cluster semantic-search-dev-search-cluster \
  --service semantic-search-dev-search-service \
  --force-new-deployment \
  --region us-east-1
```

### 3c. Confirm readiness

Poll until `/readyz` returns 200 (allow up to 2 minutes for task startup):

```bash
ALB="http://semantic-search-dev-search-alb-396758317.us-east-1.elb.amazonaws.com"
until curl -sf "$ALB/readyz" | grep -q '"status":"ready"'; do
  echo "Waiting for /readyz..."; sleep 10
done
echo "Search service is ready"
```

Smoke-test a search query:

```bash
curl -s -X POST "$ALB/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "operator with M&A experience", "top_k": 3}' | jq .
```

---

## 4. Run the validation suite

### Relevance evaluation

```bash
uv run semantic-search-eval \
  --host "$ALB" \
  --queries tests/evaluation/sample_queries.json \
  --threshold 0.90
```

A non-zero exit code means hit rate fell below the 90 % threshold.

### Load test (Locust)

```bash
uv run locust \
  -f tests/load/locustfile.py \
  --headless \
  -u 20 -r 5 \
  --run-time 60s \
  --host "$ALB"
```

Acceptance criteria: **P95 ≤ 1 s**, **error rate < 1 %**.

---

## 5. Rollback procedure

If `/readyz` fails or search returns 503 after activation:

1. Revert `VECTOR_STORE_PATH` in `terraform.tfvars` to the previous value (or
   remove it to return to the dormant state).
2. Run `terraform apply`.
3. Force a new ECS deployment to pick up the reverted task definition.

---

## Notes

- Index files are small for `data/sample.csv` (~20 records) but will grow with
  real PostgreSQL data. Monitor S3 storage costs.
- The Spot embedding provider uses a deterministic hash stub — scores are not
  semantically meaningful. Use the Bedrock or SageMaker backend for production
  quality results.
- Re-indexing is idempotent: `NumpyVectorStore.upsert` silently overwrites
  existing records.
