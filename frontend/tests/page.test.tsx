import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "../app/page";

describe("Home", () => {
  it("renders navigation links", () => {
    render(<Home />);
    expect(screen.getByText("Upload")).toBeTruthy();
    expect(screen.getByText("Live Monitor")).toBeTruthy();
    expect(screen.getByText("Stats")).toBeTruthy();
  });
});
