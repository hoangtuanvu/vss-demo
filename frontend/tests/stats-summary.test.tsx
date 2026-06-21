// frontend/tests/stats-summary.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import StatsSummary from "../components/StatsSummary";

describe("StatsSummary", () => {
  it("renders incident counts by hazard type and severity", () => {
    render(
      <StatsSummary
        incidents={[
          { id: 1, hazard_type: "ppe", severity: "warning" } as any,
          { id: 2, hazard_type: "ppe", severity: "warning" } as any,
          { id: 3, hazard_type: "fall", severity: "critical" } as any,
        ]}
      />
    );
    const table = screen.getByTestId("stats-table");
    expect(table.textContent).toContain("ppe:warning");
    expect(table.textContent).toContain("2");
    expect(table.textContent).toContain("fall:critical");
  });

  it("shows the empty state when there are no incidents", () => {
    render(<StatsSummary incidents={[]} />);
    expect(screen.getByTestId("stats-table").textContent).toContain("No incidents recorded this shift.");
  });
});
