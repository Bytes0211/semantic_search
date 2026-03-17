# Configuration Reference

This directory holds the YAML configuration that drives the semantic search
platform.  All files are optional — the system falls back to sensible
built-in defaults when no config directory is present.

## Directory Structure

```
config/
├── app.yaml                     # App-level settings (tier, embedding, server)
├── sources/                     # Per-source data configs
│   ├── sample_csv.yaml
│   ├── candidates.yaml
│   ├── support_tickets.yaml
│   ├── products.yaml
│   └── articles.yaml
├── examples/                    # Example app configs (copy to app.yaml)
│   ├── app.basic.yaml
│   ├── app.premium.yaml
│   ├── app.bedrock.yaml
│   └── app.sagemaker.yaml
└── README.md                    # ← you are here
```

## Precedence

Values are resolved in this order (first match wins):

1. **Environment variable** (e.g. `TIER=premium`)
2. **YAML value** in `config/app.yaml`
3. **Built-in default** in `semantic_search/config/app.py`

## app.yaml Schema

```yaml
tier: standard          # basic | standard | premium
embedding:
  backend: spot         # spot | bedrock | sagemaker
  model: sentence-transformers/all-MiniLM-L6-v2
  dimension: 384        # auto-resolved from model presets if omitted
  config: {}            # extra provider-specific config (e.g. region)
server:
  host: "0.0.0.0"
  port: 8000
  log_level: info
  cors_origins: "*"
  search_top_k: 10
```

### Environment Variable Mapping

| Env Var              | YAML Path             | Default                               |
|----------------------|-----------------------|---------------------------------------|
| `TIER`               | `tier`                | `standard`                            |
| `EMBEDDING_BACKEND`  | `embedding.backend`   | `spot`                                |
| `EMBEDDING_MODEL`    | `embedding.model`     | `sentence-transformers/all-MiniLM-L6-v2` |
| `EMBEDDING_DIMENSION`| `embedding.dimension` | Auto from model preset                |
| `HOST`               | `server.host`         | `0.0.0.0`                             |
| `PORT`               | `server.port`         | `8000`                                |
| `LOG_LEVEL`          | `server.log_level`    | `info`                                |
| `CORS_ORIGINS`       | `server.cors_origins` | `*`                                   |
| `SEARCH_TOP_K`       | `server.search_top_k` | `10`                                  |
| `ANALYTICS_ENABLED`  | *(backward compat)*   | `false` → maps to `tier: premium`     |

## Tier Feature Matrix

| Feature              | Basic | Standard | Premium |
|----------------------|:-----:|:--------:|:-------:|
| Semantic search      |  ✓    |    ✓     |    ✓    |
| Drill-down detail    |       |    ✓     |    ✓    |
| Metadata filters     |       |    ✓     |    ✓    |
| Analytics sidebar    |       |          |    ✓    |

## Embedding Model Presets

The system auto-resolves `dimension` for known models:

| Model                                      | Backend   | Dimension |
|--------------------------------------------|-----------|-----------|
| `amazon.titan-embed-text-v1`               | bedrock   | 1536      |
| `amazon.titan-embed-text-v2`               | bedrock   | 1024      |
| `sentence-transformers/all-MiniLM-L6-v2`   | spot      | 384       |
| `sentence-transformers/all-mpnet-base-v2`  | spot      | 768       |

### Adding Custom Models via YAML

Use the `models:` block in `config/app.yaml` to register additional models or
override built-in entries — **no Python source edits required**.

```yaml
models:
  cohere.embed-english-v3:
    dimension: 1024
    backend: bedrock
    description: "Cohere Embed English v3"   # optional
  my-fine-tuned-model:
    dimension: 768
    backend: sagemaker
    description: "Internal fine-tuned model"
```

Field reference:
- `dimension` *(required)* — output vector size; must be a positive integer.
- `backend` *(optional)* — `spot`, `bedrock`, or `sagemaker`. Defaults to `spot`.
- `description` *(optional)* — human-readable label, used in logs and tooling.

User-defined entries take precedence over built-in presets with the same ID,
so you can also override a built-in dimension without touching Python.

The resolved registry is available at `AppConfig.models` for any downstream
code that needs to enumerate available models.

For one-off use, you can still provide `dimension` explicitly in the `embedding:`
block instead of adding a `models:` entry — that always takes highest precedence.

## Source Config Schema (sources/*.yaml)

```yaml
connector:
  type: csv             # csv | sql | json | api | xml | mongodb
  config:               # connector-specific params
    path: ./data/sample.csv

id_field: id
id_prefix: ""           # optional prefix prepended to record IDs
text_fields:
  - title
  - content
metadata_fields:
  - category
  - author
detail_fields:
  - content

display:
  result_card:
    title_field: title
    columns:
      - field: category
        label: Category
      - field: author
        label: Author
  record_detail:
    sections:
      - field: content
        label: Full Content
```

### Connector Types

| Type     | Required Config Keys                                           |
|----------|----------------------------------------------------------------|
| `csv`    | `path` (supports glob)                                         |
| `sql`    | `connection_string`, `query`                                   |
| `json`   | `path`, optional `jq_filter`                                   |
| `xml`    | `path`, `xpath`                                                |
| `api`    | `url`, optional `headers`, `params`, `pagination`              |
| `mongodb`| `uri`, `database`, `collection`                                |

## Unified Index Builder

Build a combined index from all configured sources:

```bash
uv run python scripts/generate_index.py
```

Options:
- `--config-dir ./config` — Config directory (default: `./config`)
- `--source sample_csv` — Build only one source
- `--backend spot` — Override embedding backend
- `--model <model>` — Override embedding model
- `--output ./vector_index` — Output directory

## Preprocessing

The `preprocessing` block controls the
[`PreprocessingPipeline`](../semantic_search/preprocessing/) that cleans and
optionally chunks records **before** they reach the embedding provider.

```yaml
preprocessing:
  enabled: true        # false → pass-through (no cleaning or chunking)
  clean: true          # HTML stripping, Unicode NFKC, whitespace collapsing
  chunk: false         # split long records at word boundaries (disabled by default)
  chunk_size: 512      # max characters per chunk (only used when chunk: true)
  overlap: 64          # overlap characters between consecutive chunks
```

### Environment Variable Mapping

| Env Var                    | YAML Path                    | Default |
|----------------------------|------------------------------|---------|
| `PREPROCESSING_ENABLED`    | `preprocessing.enabled`      | `true`  |
| `PREPROCESSING_CLEAN`      | `preprocessing.clean`        | `true`  |
| `PREPROCESSING_CHUNK`      | `preprocessing.chunk`        | `false` |
| `PREPROCESSING_CHUNK_SIZE` | `preprocessing.chunk_size`   | `512`   |
| `PREPROCESSING_OVERLAP`    | `preprocessing.overlap`      | `64`    |

### Behaviour

- **`clean: true`** — strips HTML tags, applies NFKC Unicode normalisation, and
  collapses whitespace.  Recommended for all deployments.
- **`chunk: false` (default)** — records are embedded as single units.  Suitable
  for short-to-medium text (titles, summaries, support tickets).
- **`chunk: true`** — long records (e.g. multi-paragraph documents) are split
  at word boundaries.  Each chunk is stored as a separate vector with ID
  `{original_id}#chunk-{n}`.  **Review embedding cost impact** before enabling
  in production — chunking multiplies the number of embedding calls.

To disable preprocessing entirely (embed raw text):

```bash
uv run python scripts/generate_index.py --no-preprocessing
```

---

## Switching Tiers

Copy an example to `config/app.yaml`:

```bash
cp config/examples/app.premium.yaml config/app.yaml
```

Or set via env var:

```bash
TIER=premium uv run python main.py
```
