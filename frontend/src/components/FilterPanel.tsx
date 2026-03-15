import type { KeyboardEvent } from "react";
import type { SearchFilters } from "../types/api";

interface FilterPanelProps {
  filters: SearchFilters;
  availableFields: string[];
  onFiltersChange: (filters: SearchFilters) => void;
}

/**
 * Renders active filter chips and an inline `field:value` input for adding new ones.
 * Available metadata field names are surfaced in a `<datalist>` for autocomplete.
 */
export default function FilterPanel({
  filters,
  availableFields,
  onFiltersChange,
}: FilterPanelProps) {
  const activeFilters = Object.entries(filters);

  function removeFilter(key: string) {
    const next = { ...filters };
    delete next[key];
    onFiltersChange(next);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key !== "Enter") return;
    const raw = e.currentTarget.value.trim();
    const colonIdx = raw.indexOf(":");
    if (colonIdx === -1) return;
    const key = raw.slice(0, colonIdx).trim();
    const value = raw.slice(colonIdx + 1).trim();
    if (!key || !value) return;
    onFiltersChange({ ...filters, [key]: value });
    e.currentTarget.value = "";
  }

  if (availableFields.length === 0 && activeFilters.length === 0) return null;

  return (
    <div
      className="flex flex-wrap items-center gap-2 text-sm"
      aria-label="Active filters"
    >
      <span className="text-slate-400 text-xs font-medium select-none">
        Filters:
      </span>

      {/* Active filter chips */}
      {activeFilters.map(([key, value]) => (
        <span
          key={key}
          className="inline-flex items-center gap-1 bg-blue-50 text-blue-700 px-2.5 py-0.5 rounded-full text-xs font-medium"
        >
          {key}: {Array.isArray(value) ? value.join(", ") : value}
          <button
            type="button"
            onClick={() => removeFilter(key)}
            className="ml-0.5 leading-none hover:text-blue-900 focus:outline-none"
            aria-label={`Remove ${key} filter`}
          >
            ×
          </button>
        </span>
      ))}

      {/* Inline filter input: type "field:value" and press Enter */}
      <input
        type="text"
        placeholder="field:value + Enter"
        onKeyDown={handleKeyDown}
        list="filter-field-suggestions"
        className="text-xs px-2.5 py-1 border border-slate-300 rounded-full bg-white focus:outline-none focus:ring-1 focus:ring-blue-400 w-40"
        aria-label="Add filter"
      />
      <datalist id="filter-field-suggestions">
        {availableFields.map((f) => (
          <option key={f} value={`${f}:`} />
        ))}
      </datalist>

      {/* Clear all */}
      {activeFilters.length > 0 && (
        <button
          type="button"
          onClick={() => onFiltersChange({})}
          className="text-xs text-slate-400 hover:text-slate-700 underline"
        >
          Clear all
        </button>
      )}
    </div>
  );
}
