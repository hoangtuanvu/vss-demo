// frontend/tests/incident-feed.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import IncidentFeed from "../components/IncidentFeed";

describe("IncidentFeed", () => {
  it("renders incidents passed as props, linked to their detail page", () => {
    render(
      <IncidentFeed
        incidents={[
          { id: 1, hazard_type: "ppe", severity: "warning", caption: "no hard hat" } as any,
        ]}
      />
    );
    const list = screen.getByTestId("incident-list");
    expect(list.textContent).toContain("no hard hat");
    expect(list.querySelector('a[href="/incidents/1"]')).toBeTruthy();
  });

  it("shows the empty state when there are no incidents", () => {
    render(<IncidentFeed incidents={[]} />);
    expect(screen.getByTestId("incident-list").textContent).toContain("No alerts yet");
  });

  it("shows a Play clip button when video_offset_seconds is set and calls onPlayClip with it", () => {
    const onPlayClip = vi.fn();
    render(
      <IncidentFeed
        incidents={[
          { id: 1, hazard_type: "ppe", severity: "warning", caption: "no hard hat", video_offset_seconds: 42.5 } as any,
        ]}
        onPlayClip={onPlayClip}
      />
    );
    fireEvent.click(screen.getByText("Play clip"));
    expect(onPlayClip).toHaveBeenCalledWith(42.5);
  });

  it("does not show a Play clip button when video_offset_seconds is null", () => {
    render(
      <IncidentFeed
        incidents={[
          { id: 1, hazard_type: "ppe", severity: "warning", caption: "no hard hat", video_offset_seconds: null } as any,
        ]}
      />
    );
    expect(screen.queryByText("Play clip")).toBeNull();
  });
});
