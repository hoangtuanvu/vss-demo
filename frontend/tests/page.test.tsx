import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  fetchIncidents: vi.fn(),
  subscribeToAlerts: vi.fn(),
  uploadVideo: vi.fn(),
  sendChatMessage: vi.fn(),
}));

import Home from "../app/page";
import { fetchIncidents, subscribeToAlerts } from "../lib/api";

describe("Home", () => {
  it("renders the dashboard and keeps the feed and stats in sync as alerts stream in", async () => {
    (fetchIncidents as any).mockResolvedValue([]);
    let pushIncident: (incident: any) => void = () => {};
    (subscribeToAlerts as any).mockImplementation((onIncident: any) => {
      pushIncident = onIncident;
      return { close: vi.fn() };
    });

    render(<Home />);

    await waitFor(() => {
      expect(screen.getByTestId("incident-list")).toBeTruthy();
    });
    expect(screen.getByTestId("chat-input")).toBeTruthy();
    expect(screen.getByTestId("stats-table")).toBeTruthy();
    expect(screen.getByTestId("file-input")).toBeTruthy();

    act(() => {
      pushIncident({ id: 1, hazard_type: "ppe", severity: "warning", caption: "no hard hat" });
    });

    expect(screen.getByTestId("incident-list").textContent).toContain("no hard hat");
    expect(screen.getByTestId("stats-table").textContent).toContain("ppe:warning");
  });
});
