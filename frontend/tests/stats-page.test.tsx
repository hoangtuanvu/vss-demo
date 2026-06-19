import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ fetchIncidents: vi.fn() }));

import StatsPage from "../app/stats/page";
import { fetchIncidents } from "../lib/api";

describe("StatsPage", () => {
  it("renders incident counts by hazard type and severity", async () => {
    (fetchIncidents as any).mockResolvedValue([
      { id: 1, hazard_type: "ppe", severity: "warning" },
      { id: 2, hazard_type: "ppe", severity: "warning" },
      { id: 3, hazard_type: "fall", severity: "critical" },
    ]);

    render(<StatsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("stats-table").textContent).toContain("ppe:warning");
    });
    expect(screen.getByTestId("stats-table").textContent).toContain("2");
    expect(screen.getByTestId("stats-table").textContent).toContain("fall:critical");
  });
});
