interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  loading?: boolean;
}

/**
 * Search input field. Typing fires `onChange` immediately; the parent
 * is responsible for debouncing before issuing API calls.
 */
export default function SearchBar({
  value,
  onChange,
  loading = false,
}: SearchBarProps) {
  return (
    <div className="flex items-center gap-3 max-w-3xl">
      <div className="relative flex-1">
        {/* Search icon */}
        <svg
          className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"
          />
        </svg>
        <input
          type="search"
          role="searchbox"
          aria-label="Search query"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Search your data with natural language…"
          className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-slate-300 bg-white text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
          autoFocus
        />
      </div>

      {/* Loading indicator */}
      {loading && (
        <div
          className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin flex-shrink-0"
          aria-label="Searching…"
          role="status"
        />
      )}
    </div>
  );
}
