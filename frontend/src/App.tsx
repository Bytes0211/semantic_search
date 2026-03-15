import { useCallback, useEffect, useState } from "react";
import { useConfig } from "./hooks/useConfig";
import { useSearch } from "./hooks/useSearch";
import { useAnalytics } from "./hooks/useAnalytics";
import { useDebounce } from "./hooks/useDebounce";
import SearchBar from "./components/SearchBar";
import ResultCard from "./components/ResultCard";
import FilterPanel from "./components/FilterPanel";
import Pagination from "./components/Pagination";
import AnalyticsPanel from "./components/AnalyticsPanel";
import type { SearchFilters, SearchResultItem } from "./types/api";

const PAGE_SIZE = 10;
/** Number of results to request from the API; paginated client-side. */
const REQUEST_TOP_K = 50;

function getInitialQuery(): string {
  return new URLSearchParams(window.location.search).get("q") ?? "";
}

export default function App() {
  const [query, setQuery] = useState(getInitialQuery);
  const [filters, setFilters] = useState<SearchFilters>({});
  const [page, setPage] = useState(1);

  const debouncedQuery = useDebounce(query, 350);

  const { data: config } = useConfig();
  const analyticsEnabled = config?.analytics_enabled ?? false;

  const hasFilters = Object.keys(filters).length > 0;
  const searchParams =
    debouncedQuery.trim().length > 0
      ? {
          query: debouncedQuery,
          top_k: REQUEST_TOP_K,
          filters: hasFilters ? filters : undefined,
        }
      : null;

  const { data: searchData, isFetching, error } = useSearch(searchParams);
  const { analytics, record } = useAnalytics();

  // Record analytics whenever new results arrive
  useEffect(() => {
    if (searchData) record(searchData);
  }, [searchData, record]);

  // Reset to page 1 whenever the query or filters change
  useEffect(() => {
    setPage(1);
  }, [debouncedQuery, filters]);

  // Sync query to URL query-string for shareable links
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (debouncedQuery) {
      params.set("q", debouncedQuery);
    } else {
      params.delete("q");
    }
    const newUrl = params.toString()
      ? `?${params.toString()}`
      : window.location.pathname;
    window.history.replaceState(null, "", newUrl);
  }, [debouncedQuery]);

  // Client-side pagination over the full result set
  const allResults: SearchResultItem[] = searchData?.results ?? [];
  const totalResults = allResults.length;
  const pageStart = (page - 1) * PAGE_SIZE;
  const pageResults = allResults.slice(pageStart, pageStart + PAGE_SIZE);

  // Discover filterable field names from current result metadata
  const availableFields = [
    ...new Set(allResults.flatMap((r) => Object.keys(r.metadata))),
  ];

  const handleQueryChange = useCallback((value: string) => {
    setQuery(value);
  }, []);

  const handleFiltersChange = useCallback((next: SearchFilters) => {
    setFilters(next);
  }, []);

  return (
    <div className="min-h-screen bg-slate-50">
      {/* ── Header ─────────────────────────────────────── */}
      <header className="bg-white border-b border-slate-200 px-4 py-4 sm:px-6">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">
              <span className="text-blue-600 mr-1.5" aria-hidden="true">
                ⬡
              </span>
              Semantic Search
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Natural-language search powered by vector embeddings
            </p>
          </div>
          {analyticsEnabled && (
            <span className="text-xs font-medium bg-amber-100 text-amber-700 px-2.5 py-1 rounded-full">
              Premium
            </span>
          )}
        </div>
      </header>

      {/* ── Search bar + filters ────────────────────────── */}
      <div className="bg-white border-b border-slate-200 px-4 py-5 sm:px-6">
        <div className="max-w-7xl mx-auto space-y-3">
          <SearchBar
            value={query}
            onChange={handleQueryChange}
            loading={isFetching}
          />
          {(allResults.length > 0 || hasFilters) && (
            <FilterPanel
              filters={filters}
              availableFields={availableFields}
              onFiltersChange={handleFiltersChange}
            />
          )}
        </div>
      </div>

      {/* ── Main content ────────────────────────────────── */}
      <main className="max-w-7xl mx-auto px-4 py-6 sm:px-6">
        <div
          className={`flex gap-6 ${analyticsEnabled ? "items-start" : ""}`}
        >
          {/* Results column */}
          <div className="flex-1 min-w-0">
            {/* Status bar */}
            {debouncedQuery && (
              <div className="flex items-center justify-between mb-4">
                <p className="text-sm text-slate-600">
                  {isFetching ? (
                    <span className="animate-pulse text-slate-400">
                      Searching…
                    </span>
                  ) : searchData ? (
                    <>
                      <span className="font-medium">{totalResults}</span>{" "}
                      {totalResults === 1 ? "result" : "results"}
                      <span className="text-slate-400">
                        {" "}
                        · {searchData.elapsed_ms.toFixed(0)} ms
                        {searchData.embedding_model &&
                          ` · ${searchData.embedding_model}`}
                      </span>
                    </>
                  ) : null}
                </p>
              </div>
            )}

            {/* Error banner */}
            {error && (
              <div
                role="alert"
                className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 mb-4"
              >
                {error instanceof Error
                  ? error.message
                  : "Search failed. Please try again."}
              </div>
            )}

            {/* Result list */}
            {pageResults.length > 0 ? (
              <ul className="space-y-3" aria-label="Search results">
                {pageResults.map((item, idx) => (
                  <li key={item.record_id}>
                    <ResultCard item={item} rank={pageStart + idx + 1} />
                  </li>
                ))}
              </ul>
            ) : debouncedQuery && !isFetching && searchData ? (
              <div className="text-center py-16 text-slate-400">
                <p className="text-lg">No results found</p>
                <p className="text-sm mt-1">
                  Try a different query or remove filters
                </p>
              </div>
            ) : !debouncedQuery ? (
              <div className="text-center py-16 text-slate-400">
                <p className="text-lg">Enter a query to begin searching</p>
              </div>
            ) : null}

            {/* Pagination */}
            {totalResults > PAGE_SIZE && (
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={totalResults}
                onChange={setPage}
              />
            )}
          </div>

          {/* Analytics panel — Premium tier only */}
          {analyticsEnabled && (
            <div className="w-72 flex-shrink-0">
              <AnalyticsPanel analytics={analytics} />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
