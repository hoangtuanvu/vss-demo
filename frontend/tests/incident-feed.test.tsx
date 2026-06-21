// frontend/tests/incident-feed.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
});
