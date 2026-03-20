import { useId } from "react";

interface ScoreBadgeProps {
  score: number;
}

function getScoreStyle(score: number): { label: string; className: string } {
  // The backend returns cosine DISTANCE (1 − cosine_similarity), so lower = better.
  // score ≈ 0 → near-identical vectors; score → 1 → unrelated.
  // See NumpyVectorStore._METRIC_FUNCTIONS["cosine"] in faiss_store.py.
  if (score <= 0.3) {
    return { label: "Strong match", className: "bg-emerald-100 text-emerald-700" };
  }
  if (score <= 0.6) {
    return { label: "Moderate match", className: "bg-amber-100 text-amber-700" };
  }
  return { label: "Weak match", className: "bg-slate-100 text-slate-500" };
}

/**
 * Displays a cosine distance score as a colour-coded badge with a tooltip.
 *
 * NOTE: The backend returns cosine DISTANCE (1 − cosine_similarity), not
 * cosine similarity. Thresholds are therefore ascending — lower scores
 * indicate stronger matches:
 *   ≤ 0.3  → Strong match  (green)
 *   ≤ 0.6  → Moderate match (amber)
 *   > 0.6  → Weak match    (grey)
 */
export default function ScoreBadge({ score }: ScoreBadgeProps) {
  const { label, className } = getScoreStyle(score);
  const tooltipId = useId();

  return (
    <span className="relative group/score-tooltip">
      {/* Badge */}
      <span
        className={`inline-flex items-center text-xs font-mono font-medium px-2 py-0.5 rounded-full flex-shrink-0 cursor-default ${className}`}
        aria-describedby={tooltipId}
        aria-label={`Score ${score.toFixed(3)}, ${label}`}
      >
        {score.toFixed(3)}
      </span>

      {/* Tooltip panel */}
      <div
        id={tooltipId}
        role="tooltip"
        className="
          absolute bottom-full right-0 mb-2 w-64 z-20
          invisible opacity-0
          group-hover/score-tooltip:visible group-hover/score-tooltip:opacity-100
          transition-opacity duration-150
          bg-slate-800 text-white text-xs rounded-lg shadow-xl p-3
        "
      >
        <p className="leading-snug mb-2.5">
          The distance score tells you how far this result is from your query in
          embedding space. Smaller numbers mean the document is closer in meaning
          and therefore more relevant.
        </p>

        {/* Colour-range key */}
        <ul className="space-y-1.5 pt-2 border-t border-slate-600">
          <li className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0" />
            <span className="text-slate-300">
              <span className="text-white font-medium">&le; 0.3</span> &mdash; Strong match
            </span>
          </li>
          <li className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-400 flex-shrink-0" />
            <span className="text-slate-300">
              <span className="text-white font-medium">0.3 &ndash; 0.6</span> &mdash; Moderate match
            </span>
          </li>
          <li className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-slate-400 flex-shrink-0" />
            <span className="text-slate-300">
              <span className="text-white font-medium">&gt; 0.6</span> &mdash; Weak match
            </span>
          </li>
        </ul>

        {/* Arrow pointing down toward the badge */}
        <div className="absolute top-full right-3 border-4 border-transparent border-t-slate-800" />
      </div>
    </span>
  );
}
