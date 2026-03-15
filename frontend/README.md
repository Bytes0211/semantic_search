# Semantic Search — Web UI

React + TypeScript + Tailwind v4 SPA for the Semantic Search API.

Serves both **Standard** (search + results) and **Premium** (+ query analytics
panel) tiers from a single build. Tier gating is controlled by the
`ANALYTICS_ENABLED` environment variable on the FastAPI backend — no rebuild
required to switch tiers.

## Prerequisites

- Node.js ≥ 18
- npm ≥ 9

## Quick start

```bash
# Install dependencies
cd frontend
npm install

# Start dev server (proxies /v1/* → localhost:8000)
npm run dev
# → http://localhost:5173
```

The FastAPI backend must be running separately:

```bash
# From project root
uv run python main.py
# → http://localhost:8000
```

## Environment

| Variable | Default | Description |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:4173` | Comma-separated allowed origins |
| `ANALYTICS_ENABLED` | `false` | Set `true` for Premium tier analytics panel |

## Scripts

| Command | Description |
|---|---|
| `npm run dev` | Vite dev server with HMR and API proxy |
| `npm run build` | TypeScript check + production build → `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm test` | Run component tests with Vitest |
| `npm run coverage` | Coverage report |

## Tier behaviour

| Tier | `ANALYTICS_ENABLED` | UI behaviour |
|---|---|---|
| Standard | `false` (default) | Search bar, results, filters, pagination |
| Premium | `true` | Standard + sticky analytics sidebar (query history, avg latency, top terms) |

## Production deployment

Build outputs to `frontend/dist/`. Upload to S3 and serve via CloudFront.
CloudFront must forward `/v1/*` requests to the ALB / FastAPI origin.

```bash
npm run build
aws s3 sync dist/ s3://<bucket>/ --delete
aws cloudfront create-invalidation --distribution-id <id> --paths "/*"
```
