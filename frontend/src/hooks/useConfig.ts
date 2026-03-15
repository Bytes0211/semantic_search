import { useQuery } from "@tanstack/react-query";
import type { ConfigResponse } from "../types/api";

async function fetchConfig(): Promise<ConfigResponse> {
  const res = await fetch("/v1/config");
  if (!res.ok) throw new Error(`Config fetch failed: ${res.status}`);
  return res.json() as Promise<ConfigResponse>;
}

/**
 * Fetches feature flags from GET /v1/config once at app startup.
 * The result is cached indefinitely (no refetch on window focus or stale).
 */
export function useConfig() {
  return useQuery<ConfigResponse>({
    queryKey: ["config"],
    queryFn: fetchConfig,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  });
}
