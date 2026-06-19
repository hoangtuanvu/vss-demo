import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ subscribeToAlerts: vi.fn() }));

import MonitorPage from "../app/monitor/page";
import { subscribeToAlerts } from "../lib/api";

describe("MonitorPage", () => {
  it("renders an incident pushed over the alert subscription", () => {
    let pushIncident: (incident: any) => void = () => {};
    (subscribeToAlerts as any).mockImplementation((onIncident: any) => {
      pushIncident = onIncident;
      return { close: vi.fn() };
    });

    render(<MonitorPage />);
    act(() => {
      pushIncident({ id: 1, hazard_type: "ppe", severity: "warning", caption: "no hard hat" });
    });

    expect(screen.getByTestId("incident-list").textContent).toContain("no hard hat");
  });
});
