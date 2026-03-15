import type { Analytics } from "../hooks/useAnalytics";

interface AnalyticsPanelProps {
  analytics: Analytics;
}

/**
 * Premium-tier analytics sidebar.
 * Renders session query count, rolling average latency, top query terms,
 * and a recent query history list.
 *
 * Only mounted when `config.analytics_enabled` is true — the component
 * itself has no gating logic; gating is handled in App.tsx.
 */
export default function AnalyticsPanel({ analytics }: AnalyticsPanelProps) {
  const { history, avgLatencyMs, topTerms } = analytics;

  return (
    <aside
      className="bg-white rounded-lg border border-slate-200 overflow-hidden sticky top-4"
      aria-label="Query analytics"
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-100 bg-amber-50">
        <h2 className="text-sm font-semibold text-amber-800">Query Analytics</h2>
        <p className="text-xs text-amber-600 mt-0.5">Session statistics</p>
      </div>

      {/* Summary counters */}
      <div className="grid grid-cols-2 divide-x divide-slate-100 border-b border-slate-100">
        <div className="px-4 py-3 text-center">
          <p className="text-2xl font-bold text-slate-900 tabular-nums">
            {history.length}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">Queries</p>
        </div>
        <div className="px-4 py-3 text-center">
          <p className="text-2xl font-bold text-slate-900 tabular-nums">
            {avgLatencyMs > 0 ? Math.round(avgLatencyMs).toString() : "—"}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">Avg ms</p>
        </div>
      </div>

      {/* Top terms */}
      {topTerms.length > 0 && (
        <div className="px-4 py-3 border-b border-slate-100">
          <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">
            Top Terms
          </h3>
          <ul className="space-y-1.5">
            {topTerms.slice(0, 8).map(({ term, count }) => (
              <li key={term} className="flex items-center gap-2">
                {/* Proportional bar */}
                <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-400 rounded-full"
                    style={{
                      width: `${Math.min(100, (count / topTerms[0].count) * 100)}%`,
                    }}
                  />
                </div>
                <span className="text-xs text-slate-700 w-20 truncate">{term}</span>
                <span className="text-xs text-slate-400 tabular-nums w-4 text-right">
                  {count}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Recent queries */}
      {history.length > 0 ? (
        <div className="px-4 py-3">
          <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">
            Recent
          </h3>
          <ul className="space-y-1.5 max-h-48 overflow-y-auto">
            {history.slice(0, 10).map((entry, idx) => (
              <li
                key={idx}
                className="flex items-center justify-between gap-2"
              >
                <span className="text-xs text-slate-700 truncate flex-1">
                  {entry.query}
                </span>
                <span className="text-xs text-slate-400 tabular-nums flex-shrink-0">
                  {Math.round(entry.elapsed_ms)}ms
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="px-4 py-6 text-center">
          <p className="text-xs text-slate-400">
            Analytics will appear after your first search
          </p>
        </div>
      )}
    </aside>
  );
}
