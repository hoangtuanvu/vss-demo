import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ fetchIncident: vi.fn() }));

import IncidentDetailPage from "../app/incidents/[id]/page";
import { fetchIncident } from "../lib/api";

describe("IncidentDetailPage", () => {
  it("renders incident detail once fetched", async () => {
    (fetchIncident as any).mockResolvedValue({
      id: 1, hazard_type: "fall", severity: "critical", status: "escalated",
      zone: "aisle-3", caption: "person down", report_text: "Incident report text",
      created_at: "2026-06-19T10:00:00", updated_at: "2026-06-19T10:01:00",
    });

    render(<IncidentDetailPage params={{ id: "1" }} />);

    await waitFor(() => {
      expect(screen.getByTestId("incident-caption").textContent).toBe("person down");
    });
    expect(screen.getByTestId("incident-severity").textContent).toBe("critical");
    expect(screen.getByTestId("incident-report").textContent).toBe("Incident report text");
  });
});
