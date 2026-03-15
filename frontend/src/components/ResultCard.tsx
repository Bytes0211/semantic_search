import ScoreBadge from "./ScoreBadge";
import type { SearchResultItem } from "../types/api";

interface ResultCardProps {
  item: SearchResultItem;
  rank: number;
}

/**
 * Renders a single search result.
 * Shows the record ID, a score badge, and any metadata as key:value tags.
 */
export default function ResultCard({ item, rank }: ResultCardProps) {
  const metaEntries = Object.entries(item.metadata ?? {});

  return (
    <article className="bg-white rounded-lg border border-slate-200 px-4 py-3 hover:border-slate-300 transition-colors">
      <div className="flex items-start gap-3">
        {/* Rank number */}
        <span className="text-xs text-slate-400 font-mono mt-0.5 w-6 flex-shrink-0 select-none">
          #{rank}
        </span>

        <div className="flex-1 min-w-0">
          {/* Header row: record ID + score badge */}
          <div className="flex items-center justify-between gap-2">
            <h3
              className="text-sm font-semibold text-slate-900 truncate"
              title={item.record_id}
            >
              {item.record_id}
            </h3>
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
        </div>
      </div>
    </article>
  );
}
