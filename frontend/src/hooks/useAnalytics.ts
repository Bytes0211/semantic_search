import { useCallback, useMemo, useState } from "react";
import type { SearchResponse } from "../types/api";

/** A single recorded search event. */
export interface SearchRecord {
  /** Stable unique identifier generated at record time via crypto.randomUUID(). */
  id: string;
  query: string;
  timestamp: number;
  elapsed_ms: number;
  result_count: number;
}

/** Computed session analytics derived from accumulated search history. */
export interface Analytics {
  history: SearchRecord[];
  avgLatencyMs: number;
  topTerms: Array<{ term: string; count: number }>;
}

const MAX_HISTORY = 50;

/** Stop-words excluded from top-term frequency analysis. */
const STOP_WORDS = new Set([
  "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "do",
  "for", "from", "get", "has", "have", "i", "if", "in", "is", "it", "its",
  "me", "my", "not", "of", "on", "or", "our", "so", "the", "their", "them",
  "this", "to", "up", "us", "was", "we", "what", "with",
]);

function computeTopTerms(
  records: SearchRecord[]
): Array<{ term: string; count: number }> {
  const freq = new Map<string, number>();
  for (const { query } of records) {
    const words = query
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, " ")
      .split(/\s+/)
      .filter((w) => w.length > 2 && !STOP_WORDS.has(w));
    for (const w of words) {
      freq.set(w, (freq.get(w) ?? 0) + 1);
    }
  }
  return [...freq.entries()]
    .map(([term, count]) => ({ term, count }))
    .sort((a, b) => b.count - a.count);
}

/**
 * Accumulates search history for the current session and computes
 * rolling analytics (average latency, top query terms).
 *
 * This is entirely client-side — no data leaves the browser.
 */
export function useAnalytics() {
  const [history, setHistory] = useState<SearchRecord[]>([]);

  const record = useCallback((response: SearchResponse) => {
    const entry: SearchRecord = {
      id: crypto.randomUUID(),
      query: response.query,
      timestamp: Date.now(),
      elapsed_ms: response.elapsed_ms,
      result_count: response.results.length,
    };
    setHistory((prev) => [entry, ...prev].slice(0, MAX_HISTORY));
  }, []);

  const analytics = useMemo<Analytics>(() => {
    const avgLatencyMs =
      history.length > 0
        ? history.reduce((sum, r) => sum + r.elapsed_ms, 0) / history.length
        : 0;
    return {
      history,
      avgLatencyMs,
      topTerms: computeTopTerms(history),
    };
  }, [history]);

  return { analytics, record };
}
