import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import AnalyticsPanel from "../components/AnalyticsPanel";
import type { Analytics } from "../hooks/useAnalytics";

const emptyAnalytics: Analytics = {
  history: [],
  avgLatencyMs: 0,
  topTerms: [],
};

const filledAnalytics: Analytics = {
  history: [
    {
      query: "machine learning models",
      timestamp: 1_700_000_000_000,
      elapsed_ms: 45,
      result_count: 10,
    },
    {
      query: "vector database embeddings",
      timestamp: 1_700_000_001_000,
      elapsed_ms: 31,
      result_count: 5,
    },
  ],
  avgLatencyMs: 38,
  topTerms: [
    { term: "machine", count: 2 },
    { term: "learning", count: 1 },
    { term: "vector", count: 1 },
  ],
};

describe("AnalyticsPanel", () => {
  it("shows the empty-state placeholder before any searches", () => {
    render(<AnalyticsPanel analytics={emptyAnalytics} />);
    expect(
      screen.getByText(/analytics will appear after your first search/i),
    ).toBeInTheDocument();
  });

  it("displays the correct query count", () => {
    render(<AnalyticsPanel analytics={filledAnalytics} />);
    // "2" appears in both the Queries summary and the top-term count badge;
    // getAllByText asserts at least one element with that text exists.
    const twos = screen.getAllByText("2");
    expect(twos.length).toBeGreaterThanOrEqual(1);
    // The large bold stat element should be among them
    const boldTwo = twos.find((el) => el.className.includes("font-bold"));
    expect(boldTwo).toBeDefined();
  });

  it("displays the rounded average latency", () => {
    render(<AnalyticsPanel analytics={filledAnalytics} />);
    expect(screen.getByText("38")).toBeInTheDocument();
  });

  it("renders top terms", () => {
    render(<AnalyticsPanel analytics={filledAnalytics} />);
    expect(screen.getByText("machine")).toBeInTheDocument();
    expect(screen.getByText("vector")).toBeInTheDocument();
  });

  it("renders recent query history", () => {
    render(<AnalyticsPanel analytics={filledAnalytics} />);
    expect(screen.getByText("machine learning models")).toBeInTheDocument();
    expect(screen.getByText("vector database embeddings")).toBeInTheDocument();
  });
});
