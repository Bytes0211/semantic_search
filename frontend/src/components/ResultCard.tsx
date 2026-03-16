import { useState } from "react";
import ScoreBadge from "./ScoreBadge";
import type { SearchResultItem } from "../types/api";

interface ResultCardProps {
  item: SearchResultItem;
  rank: number;
}

/**
 * Renders a single search result.
 * Shows the record ID, a score badge, metadata as key:value tags,
 * and an inline expand/collapse panel for detail fields.
 */
export default function ResultCard({ item, rank }: ResultCardProps) {
  const metaEntries = Object.entries(item.metadata ?? {});
  const detailEntries = Object.entries(item.detail ?? {});
  const hasDetail = detailEntries.length > 0;
  const [expanded, setExpanded] = useState(false);

  return (
    <article className="bg-white rounded-lg border border-slate-200 px-4 py-3 hover:border-slate-300 transition-colors">
      <div className="flex items-start gap-3">
        {/* Rank number */}
        <span className="text-xs text-slate-400 font-mono mt-0.5 w-6 flex-shrink-0 select-none">
          #{rank}
        </span>

        <div className="flex-1 min-w-0">
          {/* Header row: record ID + score badge + expand toggle */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <h3
                className="text-sm font-semibold text-slate-900 truncate"
                title={item.record_id}
              >
                {item.record_id}
              </h3>
              {hasDetail && (
                <button
                  type="button"
                  onClick={() => setExpanded((prev) => !prev)}
                  className="text-slate-400 hover:text-slate-600 transition-colors flex-shrink-0"
                  aria-expanded={expanded}
                  aria-label={expanded ? "Collapse details" : "Expand details"}
                >
                  <svg
                    className={`w-4 h-4 transition-transform ${
                      expanded ? "rotate-90" : ""
                    }`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M9 5l7 7-7 7"
                    />
                  </svg>
                </button>
              )}
            </div>
            <ScoreBadge score={item.score} />
          </div>

          {/* Metadata tags */}
          {metaEntries.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Metadata">
              {metaEntries.map(([key, value]) => (
                <li
                  key={key}
                  className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded"
                >
                  <span className="text-slate-400">{key}:</span>{" "}
                  {String(value)}
                </li>
              ))}
            </ul>
          )}

          {/* Detail panel (inline expand) */}
          {hasDetail && expanded && (
            <dl
              className="mt-3 border-t border-slate-100 pt-2 space-y-2"
              aria-label="Record details"
            >
              {detailEntries.map(([key, value]) => (
                <div key={key}>
                  <dt className="text-xs font-medium text-slate-400">{key}</dt>
                  <dd className="text-sm text-slate-700 mt-0.5 whitespace-pre-wrap">
                    {String(value)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </div>
    </article>
  );
}
