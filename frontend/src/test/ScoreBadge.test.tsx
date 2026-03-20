import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ScoreBadge from "../components/ScoreBadge";

describe("ScoreBadge", () => {
  it("renders the score formatted to 3 decimal places", () => {
    render(<ScoreBadge score={0.25} />);
    expect(screen.getByText("0.250")).toBeInTheDocument();
  });

  it("tooltip explanation text is present in the DOM", () => {
    render(<ScoreBadge score={0.25} />);
    expect(
      screen.getByText(/smaller numbers mean the document is closer in meaning/i)
    ).toBeInTheDocument();
  });

  it("tooltip contains all three colour-range labels", () => {
    render(<ScoreBadge score={0.25} />);
    expect(screen.getByText(/strong match/i)).toBeInTheDocument();
    expect(screen.getByText(/moderate match/i)).toBeInTheDocument();
    expect(screen.getByText(/weak match/i)).toBeInTheDocument();
  });

  it("tooltip has role=tooltip for accessibility", () => {
    render(<ScoreBadge score={0.25} />);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
  });

  it("badge aria-label reflects score and match quality for strong match", () => {
    render(<ScoreBadge score={0.2} />);
    expect(screen.getByLabelText(/score 0\.200, strong match/i)).toBeInTheDocument();
  });

  it("badge aria-label reflects moderate match", () => {
    render(<ScoreBadge score={0.45} />);
    expect(screen.getByLabelText(/score 0\.450, moderate match/i)).toBeInTheDocument();
  });

  it("badge aria-label reflects weak match", () => {
    render(<ScoreBadge score={0.75} />);
    expect(screen.getByLabelText(/score 0\.750, weak match/i)).toBeInTheDocument();
  });
});
