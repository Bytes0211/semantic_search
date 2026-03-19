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

/** A column definition from the display config. */
export interface ColumnDef {
  field: string;
  label: string;
  /** Optional type hint for rendering. When `"link"`, the value is rendered
   *  as a clickable anchor. */
  type?: string;
  /** When set on a `type: "link"` column, this metadata key provides the
   *  URL/href while `field` provides the display text. */
  link_field?: string;
}

/** A detail section definition from the display config. */
export interface DetailSectionDef {
  field: string;
  label: string;
}

/** Per-source display configuration returned by the API. */
export interface DisplayDef {
  title_field: string | null;
  columns: ColumnDef[];
  detail_sections: DetailSectionDef[];
}

/** Response body from GET /v1/config. */
export interface ConfigResponse {
  /** Client subscription tier: "basic" | "standard" | "premium". */
  tier: string;
  /** Whether drill-down detail is enabled for this tier. */
  detail_enabled: boolean;
  /** Whether metadata filters are enabled for this tier. */
  filters_enabled: boolean;
  analytics_enabled: boolean;
  /** Maximum number of results to request per query. Defaults to 50. */
  search_top_k: number;
  /** Per-source display configuration (keyed by source name). */
  display?: Record<string, DisplayDef>;
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
