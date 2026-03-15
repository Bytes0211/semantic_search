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
 * Displays a cosine distance score as a colour-coded badge.
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
  return (
    <span
      className={`inline-flex items-center text-xs font-mono font-medium px-2 py-0.5 rounded-full flex-shrink-0 ${className}`}
      title={`${label} — distance: ${score.toFixed(4)}`}
      aria-label={`Score ${score.toFixed(3)}, ${label}`}
    >
      {score.toFixed(3)}
    </span>
  );
}
