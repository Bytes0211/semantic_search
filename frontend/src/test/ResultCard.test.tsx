import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ResultCard from "../components/ResultCard";
import type { SearchResultItem } from "../types/api";

const mockItem: SearchResultItem = {
  record_id: "doc-001",
  score: 0.25,
  metadata: { category: "documents", region: "us-east-1" },
  detail: {},
};

const mockItemWithDetail: SearchResultItem = {
  record_id: "candidate-1",
  score: 0.15,
  metadata: { full_name: "Jane Smith", location: "NYC" },
  detail: { summary: "Experienced operator with M&A background", skills: "Python, SQL" },
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
    const item: SearchResultItem = { record_id: "bare", score: 0.5, metadata: {}, detail: {} };
    render(<ResultCard item={item} rank={1} />);
    expect(screen.getByText("bare")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: /metadata/i })).toBeNull();
  });

  it("does not show expand button when detail is empty", () => {
    render(<ResultCard item={mockItem} rank={1} />);
    expect(screen.queryByRole("button", { name: /expand/i })).toBeNull();
  });

  it("shows expand button when detail has fields", () => {
    render(<ResultCard item={mockItemWithDetail} rank={1} />);
    expect(screen.getByRole("button", { name: /expand details/i })).toBeInTheDocument();
  });

  it("expands detail fields on click", async () => {
    const user = userEvent.setup();
    render(<ResultCard item={mockItemWithDetail} rank={1} />);

    // Detail not visible initially
    expect(screen.queryByText("Experienced operator with M&A background")).toBeNull();

    // Click expand
    await user.click(screen.getByRole("button", { name: /expand details/i }));

    // Detail now visible
    expect(screen.getByText("Experienced operator with M&A background")).toBeInTheDocument();
    expect(screen.getByText("Python, SQL")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /collapse details/i })).toBeInTheDocument();
  });

  it("collapses detail fields on second click", async () => {
    const user = userEvent.setup();
    render(<ResultCard item={mockItemWithDetail} rank={1} />);

    // Expand then collapse
    await user.click(screen.getByRole("button", { name: /expand details/i }));
    expect(screen.getByText("Experienced operator with M&A background")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /collapse details/i }));
    expect(screen.queryByText("Experienced operator with M&A background")).toBeNull();
  });
});
