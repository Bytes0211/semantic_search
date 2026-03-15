interface ScoreBadgeProps {
  score: number;
}

function getScoreStyle(score: number): { label: string; className: string } {
  // Lower cosine distance = stronger semantic match
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
 * Green ≤ 0.3 (strong), amber 0.3–0.6 (moderate), grey > 0.6 (weak).
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
