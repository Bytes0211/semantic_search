import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ResultCard from "../components/ResultCard";
import type { SearchResultItem } from "../types/api";

const mockItem: SearchResultItem = {
  record_id: "doc-001",
  score: 0.25,
  metadata: { category: "documents", region: "us-east-1" },
};

describe("ResultCard", () => {
  it("renders the record ID", () => {
    render(<ResultCard item={mockItem} rank={1} />);
    expect(screen.getByText("doc-001")).toBeInTheDocument();
  });

  it("renders the rank number", () => {
    render(<ResultCard item={mockItem} rank={3} />);
    expect(screen.getByText("#3")).toBeInTheDocument();
  });

  it("renders metadata key:value tags", () => {
    render(<ResultCard item={mockItem} rank={1} />);
    expect(screen.getByText("documents")).toBeInTheDocument();
    expect(screen.getByText("us-east-1")).toBeInTheDocument();
  });

  it("renders the score badge", () => {
    render(<ResultCard item={mockItem} rank={1} />);
    expect(screen.getByText("0.250")).toBeInTheDocument();
  });

  it("renders gracefully when metadata is empty", () => {
    const item: SearchResultItem = { record_id: "bare", score: 0.5, metadata: {} };
    render(<ResultCard item={item} rank={1} />);
    expect(screen.getByText("bare")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: /metadata/i })).toBeNull();
  });
});
