import { useQuery } from "@tanstack/react-query";
import type { SearchRequest, SearchResponse } from "../types/api";

async function executeSearch(params: SearchRequest): Promise<SearchResponse> {
  const res = await fetch("/v1/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Search failed with status ${res.status}`);
  }
  return res.json() as Promise<SearchResponse>;
}

/**
 * Issues a semantic search request.
 *
 * @param params - Search parameters; pass `null` to disable the query.
 *
 * TanStack Query keeps the previous result visible while a new fetch is
 * in flight (`placeholderData: keepPreviousData` equivalent via `enabled`
 * gating), which prevents layout flicker between keystrokes.
 */
export function useSearch(params: SearchRequest | null) {
  return useQuery<SearchResponse>({
    queryKey: ["search", params],
    queryFn: () => executeSearch(params!),
    enabled: params !== null && params.query.trim().length > 0,
    placeholderData: (prev) => prev,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}
