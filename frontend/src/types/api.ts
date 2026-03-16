/**
 * TypeScript types that mirror the FastAPI Pydantic models.
 * Keep in sync with semantic_search/runtime/api.py.
 */

/** A single result item returned by POST /v1/search. */
export interface SearchResultItem {
  record_id: string;
  score: number;
  metadata: Record<string, unknown>;
  /** Detail fields for drill-down display, extracted from `_detail` at query time. */
  detail: Record<string, unknown>;
}

/** Full response body from POST /v1/search. */
export interface SearchResponse {
  query: string;
  results: SearchResultItem[];
  elapsed_ms: number;
  embedding_model: string | null;
}

/** Response body from GET /v1/config. */
export interface ConfigResponse {
  analytics_enabled: boolean;
  /** Maximum number of results to request per query. Defaults to 50. */
  search_top_k: number;
}

/**
 * Metadata filter map sent as part of SearchRequest.
 * Values can be a scalar or an array for multi-value "any of" matching.
 */
export type SearchFilters = Record<string, string | string[]>;

/** Request body for POST /v1/search. */
export interface SearchRequest {
  query: string;
  top_k?: number;
  filters?: SearchFilters;
}
