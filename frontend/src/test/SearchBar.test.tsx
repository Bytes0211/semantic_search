import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SearchBar from "../components/SearchBar";

describe("SearchBar", () => {
  it("renders the search input with placeholder", () => {
    render(<SearchBar value="" onChange={() => {}} />);
    expect(
      screen.getByPlaceholderText(/natural language/i),
    ).toBeInTheDocument();
  });

  it("calls onChange with the new value on input change", () => {
    const onChange = vi.fn();
    render(<SearchBar value="" onChange={onChange} />);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "machine learning" },
    });
    expect(onChange).toHaveBeenCalledWith("machine learning");
  });

  it("renders the current value in the input", () => {
    render(<SearchBar value="vector database" onChange={() => {}} />);
    const input = screen.getByRole("searchbox") as HTMLInputElement;
    expect(input.value).toBe("vector database");
  });

  it("shows the loading spinner when loading=true", () => {
    render(<SearchBar value="" onChange={() => {}} loading />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("does not show the loading spinner when loading=false", () => {
    render(<SearchBar value="" onChange={() => {}} loading={false} />);
    expect(screen.queryByRole("status")).toBeNull();
  });
});
