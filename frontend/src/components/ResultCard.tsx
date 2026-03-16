import { useMemo, useState } from "react";
import ScoreBadge from "./ScoreBadge";
import type { DisplayDef, SearchResultItem } from "../types/api";

interface ResultCardProps {
  item: SearchResultItem;
  rank: number;
  /** Whether the drill-down detail panel is enabled (tier-gated). */
  detailEnabled?: boolean;
  /** Per-source display configs keyed by source name. */
  displayMap?: Record<string, DisplayDef>;
}

/**
 * Renders a single search result.
 * Shows the record ID, a score badge, metadata as key:value tags,
 * and an inline expand/collapse panel for detail fields.
 */
export default function ResultCard({
  item,
  rank,
  detailEnabled = true,
  displayMap,
}: ResultCardProps) {
  const [expanded, setExpanded] = useState(false);

  // Resolve the display config for this item's source (if available)
  const sourceName = item.metadata?.source as string | undefined;
  const display = useMemo(
    () => (sourceName && displayMap ? displayMap[sourceName] : undefined),
    [sourceName, displayMap],
  );

  // Title: use display title_field if available, else fall back to record_id
  const titleField = display?.title_field;
  const title = titleField
    ? String(item.metadata?.[titleField] ?? item.record_id)
    : item.record_id;

  // Metadata tags: use configured columns if available, else show all metadata
  const metaTags = useMemo(() => {
    if (display?.columns && display.columns.length > 0) {
      return display.columns
        .filter((col) => item.metadata?.[col.field] !== undefined)
        .map((col) => ({
          key: col.field,
          label: col.label,
          value: String(item.metadata[col.field]),
        }));
    }
    // Fallback: show all metadata except 'source' and title field
    return Object.entries(item.metadata ?? {})
      .filter(([k]) => k !== "source" && k !== titleField)
      .map(([k, v]) => ({
        key: k,
        label: k,
        value: String(v),
      }));
  }, [display, item.metadata, titleField]);

  // Detail sections: use configured sections if available, else raw detail entries
  const detailSections = useMemo(() => {
    const raw = item.detail ?? {};
    if (display?.detail_sections && display.detail_sections.length > 0) {
      return display.detail_sections
        .filter((sec) => raw[sec.field] !== undefined)
        .map((sec) => ({
          key: sec.field,
          label: sec.label,
          value: String(raw[sec.field]),
        }));
    }
    return Object.entries(raw).map(([k, v]) => ({
      key: k,
      label: k,
      value: String(v),
    }));
  }, [display, item.detail]);

  const hasDetail = detailEnabled && detailSections.length > 0;

  return (
    <article className="bg-white rounded-lg border border-slate-200 px-4 py-3 hover:border-slate-300 transition-colors">
      <div className="flex items-start gap-3">
        {/* Rank number */}
        <span className="text-xs text-slate-400 font-mono mt-0.5 w-6 flex-shrink-0 select-none">
          #{rank}
        </span>

        <div className="flex-1 min-w-0">
          {/* Header row: title + score badge + expand toggle */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <h3
                className="text-sm font-semibold text-slate-900 truncate"
                title={item.record_id}
              >
                {title}
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

          {/* Metadata tags (config-driven labels) */}
          {metaTags.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Metadata">
              {metaTags.map((tag) => (
                <li
                  key={tag.key}
                  className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded"
                >
                  <span className="text-slate-400">{tag.label}:</span>{" "}
                  {tag.value}
                </li>
              ))}
            </ul>
          )}

          {/* Detail panel (inline expand — tier-gated) */}
          {hasDetail && expanded && (
            <dl
              className="mt-3 border-t border-slate-100 pt-2 space-y-2"
              aria-label="Record details"
            >
              {detailSections.map((sec) => (
                <div key={sec.key}>
                  <dt className="text-xs font-medium text-slate-400">
                    {sec.label}
                  </dt>
                  <dd className="text-sm text-slate-700 mt-0.5 whitespace-pre-wrap">
                    {sec.value}
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
