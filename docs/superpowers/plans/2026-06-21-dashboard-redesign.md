# Frontend Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the frontend's three-page flow (`/upload`, `/monitor`, `/stats`) into a single dashboard at `/`, so the core demo loop (upload → watch triage → ask questions → check stats) needs no manual navigation.

**Architecture:** Extract `UploadBar`, `IncidentFeed`, `StatsSummary` as prop-driven components from the existing three pages, then rewrite `app/page.tsx` to compose them plus the unchanged `ChatPanel` around one shared incidents array (seeded by `fetchIncidents`, kept live by the existing `subscribeToAlerts` SSE subscription). Old pages and their tests are deleted once the dashboard supersedes them.

**Tech Stack:** Next.js 14, React 18, TypeScript, Tailwind CSS, Vitest + React Testing Library — same stack as the rest of `frontend/`.

## Global Constraints

- No backend or `lib/api.ts` changes — this is frontend-only.
- Keep the existing industrial/hazard-tape visual language (dark theme, `font-mono` uppercase labels, `caution`/`alarm`/`signal` color tokens) — this redesign is about navigation flow, not visual style.
- `IncidentFeed` and `StatsSummary` take `incidents: Incident[]` as a prop — neither fetches independently.
- `/incidents/[id]` stays a separate route, unchanged except for one added back-link.
- Test runner: `cd frontend && npm test` (vitest run).

---

### Task 1: Extract `UploadBar`

**Files:**
- Create: `frontend/components/UploadBar.tsx`
- Create: `frontend/tests/upload-bar.test.tsx`

**Interfaces:**
- Consumes: `uploadVideo(file: File): Promise<{ stream_url: string }>` from `frontend/lib/api.ts` (unchanged).
- Produces: `UploadBar` — a self-contained component, no props. Used by Task 4's dashboard.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/upload-bar.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ uploadVideo: vi.fn() }));

import UploadBar from "../components/UploadBar";
import { uploadVideo } from "../lib/api";

describe("UploadBar", () => {
  it("shows the stream status after a successful upload", async () => {
    (uploadVideo as any).mockResolvedValue({ stream_url: "rtsp://localhost:8554/cam1" });
    render(<UploadBar />);

    const file = new File(["fake"], "clip.mp4", { type: "video/mp4" });
    const input = screen.getByTestId("file-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload"));

    await waitFor(() => {
      expect(screen.getByTestId("upload-status").textContent).toContain("rtsp://localhost:8554/cam1");
    });
  });

  it("shows an error message when the upload fails", async () => {
    (uploadVideo as any).mockRejectedValue(new Error("boom"));
    render(<UploadBar />);

    const file = new File(["fake"], "clip.mp4", { type: "video/mp4" });
    const input = screen.getByTestId("file-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload"));

    await waitFor(() => {
      expect(screen.getByTestId("upload-error")).toBeTruthy();
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- tests/upload-bar.test.tsx`
Expected: FAIL with `Failed to resolve import "../components/UploadBar"`

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/components/UploadBar.tsx
"use client";
import { useState } from "react";

import { uploadVideo } from "../lib/api";

export default function UploadBar() {
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fileInput = event.currentTarget.elements.namedItem("file") as HTMLInputElement;
    const file = fileInput.files?.[0];
    if (!file) return;
    try {
      const result = await uploadVideo(file);
      setStatus(`Streaming at ${result.stream_url}`);
      setError(null);
    } catch {
      setError("Upload failed. Try again.");
      setStatus(null);
    }
  }

  return (
    <div className="border border-paper/15 bg-panel p-4">
      <form onSubmit={handleSubmit} className="flex flex-wrap items-center gap-3">
        <label htmlFor="file" className="font-mono text-xs uppercase tracking-widest text-paper/50">
          New clip
        </label>
        <input
          id="file"
          type="file"
          name="file"
          accept="video/*"
          data-testid="file-input"
          className="block text-sm text-paper/80 file:mr-4 file:border file:border-paper/20 file:bg-ink file:px-3 file:py-1.5 file:text-sm file:text-paper file:transition-colors hover:file:border-caution"
        />
        <button
          type="submit"
          className="border border-caution bg-caution px-4 py-1.5 font-mono text-xs uppercase tracking-widest text-ink transition-colors hover:bg-ink hover:text-caution"
        >
          Upload
        </button>
      </form>
      {status && (
        <p data-testid="upload-status" className="mt-3 border-l-2 border-signal pl-3 font-mono text-sm text-signal">
          {status}
        </p>
      )}
      {error && (
        <p data-testid="upload-error" className="mt-3 border-l-2 border-alarm pl-3 font-mono text-sm text-alarm">
          {error}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- tests/upload-bar.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/components/UploadBar.tsx frontend/tests/upload-bar.test.tsx
git commit -m "feat: extract UploadBar component for the dashboard redesign"
```

---

### Task 2: Extract `IncidentFeed`

**Files:**
- Create: `frontend/components/IncidentFeed.tsx`
- Create: `frontend/tests/incident-feed.test.tsx`

**Interfaces:**
- Consumes: `Incident` type from `frontend/lib/api.ts` (unchanged).
- Produces: `IncidentFeed({ incidents }: { incidents: Incident[] })`. Renders each incident as a link to `/incidents/{id}` (new — today's `/monitor` page renders incidents as plain non-linked `<li>`s; this redesign makes the detail page reachable from the UI for the first time). Used by Task 4's dashboard.

- [ ] **Step 1: Write the failing test**

```tsx
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- tests/incident-feed.test.tsx`
Expected: FAIL with `Failed to resolve import "../components/IncidentFeed"`

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/components/IncidentFeed.tsx
import Link from "next/link";

import { Incident } from "../lib/api";

const SEVERITY: Record<string, { label: string; border: string; text: string }> = {
  critical: { label: "Critical", border: "border-alarm", text: "text-alarm" },
  warning: { label: "Caution", border: "border-caution", text: "text-caution" },
  info: { label: "Clear", border: "border-signal", text: "text-signal" },
};

export default function IncidentFeed({ incidents }: { incidents: Incident[] }) {
  return (
    <ul data-testid="incident-list" className="space-y-2">
      {incidents.length === 0 && (
        <li className="border border-paper/15 bg-panel p-4 text-sm text-paper/50">
          No alerts yet. The floor is clear.
        </li>
      )}
      {incidents.map((incident) => {
        const severity = SEVERITY[incident.severity] ?? SEVERITY.info;
        return (
          <li key={incident.id} className={`border-l-2 ${severity.border} bg-panel`}>
            <Link href={`/incidents/${incident.id}`} className="block p-4 hover:bg-ink/40">
              <span className={`font-mono text-xs uppercase tracking-widest ${severity.text}`}>
                {severity.label}
              </span>
              <p className="mt-1 text-sm">
                <span className="font-mono text-paper/50">{incident.hazard_type}</span>: {incident.caption}
              </p>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- tests/incident-feed.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/components/IncidentFeed.tsx frontend/tests/incident-feed.test.tsx
git commit -m "feat: extract IncidentFeed component, link incidents to their detail page"
```

---

### Task 3: Extract `StatsSummary`

**Files:**
- Create: `frontend/components/StatsSummary.tsx`
- Create: `frontend/tests/stats-summary.test.tsx`

**Interfaces:**
- Consumes: `Incident` type from `frontend/lib/api.ts` (unchanged).
- Produces: `StatsSummary({ incidents }: { incidents: Incident[] })`. Used by Task 4's dashboard.

- [ ] **Step 1: Write the failing test**

```tsx
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- tests/stats-summary.test.tsx`
Expected: FAIL with `Failed to resolve import "../components/StatsSummary"`

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/components/StatsSummary.tsx
import { Incident } from "../lib/api";

export default function StatsSummary({ incidents }: { incidents: Incident[] }) {
  const counts: Record<string, number> = {};
  for (const incident of incidents) {
    const key = `${incident.hazard_type}:${incident.severity}`;
    counts[key] = (counts[key] || 0) + 1;
  }
  const rows = Object.entries(counts);

  return (
    <div className="border border-paper/15 bg-panel p-4">
      <p className="font-mono text-xs uppercase tracking-widest text-paper/50">Shift report</p>
      <table data-testid="stats-table" className="mt-3 w-full">
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={2} className="py-4 text-center text-sm text-paper/40">
                No incidents recorded this shift.
              </td>
            </tr>
          )}
          {rows.map(([key, count]) => (
            <tr key={key} className="border-b border-paper/10 odd:bg-panel/50">
              <td className="py-1.5 font-mono text-sm">{key}</td>
              <td className="py-1.5 text-right font-mono text-sm">{count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- tests/stats-summary.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/components/StatsSummary.tsx frontend/tests/stats-summary.test.tsx
git commit -m "feat: extract StatsSummary component"
```

---

### Task 4: Rewrite the dashboard at `/`, delete the old pages

**Files:**
- Modify: `frontend/app/page.tsx` (full rewrite)
- Modify: `frontend/tests/page.test.tsx` (full rewrite)
- Delete: `frontend/app/upload/page.tsx`, `frontend/app/monitor/page.tsx`, `frontend/app/stats/page.tsx`
- Delete: `frontend/tests/upload-page.test.tsx`, `frontend/tests/monitor-page.test.tsx`, `frontend/tests/stats-page.test.tsx`

**Interfaces:**
- Consumes: `UploadBar` (Task 1), `IncidentFeed` (Task 2), `StatsSummary` (Task 3), `ChatPanel` (unchanged), `fetchIncidents`/`subscribeToAlerts` from `frontend/lib/api.ts` (unchanged).
- Produces: the dashboard at `/`. Nothing later depends on this beyond the app itself — this is the terminal composition.

- [ ] **Step 1: Delete the now-superseded pages and their tests**

```bash
rm frontend/app/upload/page.tsx frontend/app/monitor/page.tsx frontend/app/stats/page.tsx
rm frontend/tests/upload-page.test.tsx frontend/tests/monitor-page.test.tsx frontend/tests/stats-page.test.tsx
```

- [ ] **Step 2: Write the failing test**

```tsx
// frontend/tests/page.test.tsx
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npm test -- tests/page.test.tsx`
Expected: FAIL — old `Home` still renders the three nav links, no `incident-list`/`chat-input`/`stats-table`/`file-input` testids exist yet on `/`

- [ ] **Step 4: Write the implementation**

```tsx
// frontend/app/page.tsx
"use client";
import { useEffect, useState } from "react";

import ChatPanel from "../components/ChatPanel";
import IncidentFeed from "../components/IncidentFeed";
import StatsSummary from "../components/StatsSummary";
import UploadBar from "../components/UploadBar";
import { Incident, fetchIncidents, subscribeToAlerts } from "../lib/api";

export default function Home() {
  const [incidents, setIncidents] = useState<Incident[]>([]);

  useEffect(() => {
    fetchIncidents().then(setIncidents);
  }, []);

  useEffect(() => {
    const source = subscribeToAlerts((incident) => {
      setIncidents((prev) => [incident, ...prev.filter((i) => i.id !== incident.id)]);
    });
    return () => source.close();
  }, []);

  return (
    <main className="min-h-screen">
      <div className="hazard-tape h-2 w-full" aria-hidden="true" />
      <div className="mx-auto max-w-6xl px-6 py-12">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.3em] text-caution">Live ops console</p>
            <h1 className="mt-4 font-display text-3xl sm:text-4xl">Warehouse Safety Monitor</h1>
          </div>
          <span className="flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-alarm">
            <span className="h-2 w-2 rounded-full bg-alarm" aria-hidden="true" />
            Recording
          </span>
        </div>

        <div className="mt-6">
          <UploadBar />
        </div>

        <div className="mt-8 grid gap-8 lg:grid-cols-[2fr_1fr]">
          <IncidentFeed incidents={incidents} />
          <aside className="space-y-8">
            <div className="border border-paper/15 bg-panel p-4">
              <p className="font-mono text-xs uppercase tracking-widest text-paper/50">Ask the floor</p>
              <ChatPanel />
            </div>
            <StatsSummary incidents={incidents} />
          </aside>
        </div>
      </div>
    </main>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm test -- tests/page.test.tsx`
Expected: PASS

- [ ] **Step 6: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS, no references to the deleted pages remain

- [ ] **Step 7: Commit**

```bash
git add frontend/app/page.tsx frontend/tests/page.test.tsx
git add frontend/app/upload frontend/app/monitor frontend/app/stats frontend/tests/upload-page.test.tsx frontend/tests/monitor-page.test.tsx frontend/tests/stats-page.test.tsx
git commit -m "feat: collapse upload/monitor/stats into one dashboard at /"
```

---

### Task 5: Back-link from the incident detail page

**Files:**
- Modify: `frontend/app/incidents/[id]/page.tsx`
- Modify: `frontend/tests/incident-detail-page.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new consumed elsewhere — this is the last task.

- [ ] **Step 1: Write the failing test**

Add to `frontend/tests/incident-detail-page.test.tsx`, inside the existing `it` block, after the existing assertions:

```tsx
    expect(screen.getByTestId("back-link").textContent).toContain("Dashboard");
```

(Full file after the change:)

```tsx
// frontend/tests/incident-detail-page.test.tsx
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
    expect(screen.getByTestId("back-link").textContent).toContain("Dashboard");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- tests/incident-detail-page.test.tsx`
Expected: FAIL with `Unable to find an element by: [data-testid="back-link"]`

- [ ] **Step 3: Add the back-link**

In `frontend/app/incidents/[id]/page.tsx`, add the import at the top:

```tsx
import Link from "next/link";
```

Then, inside the `<main>` element, immediately before the `<div className={...border-l-4...}>` incident card, add:

```tsx
        <Link
          href="/"
          data-testid="back-link"
          className="font-mono text-xs uppercase tracking-widest text-paper/50 hover:text-caution"
        >
          ← Dashboard
        </Link>
```

So the relevant section reads:

```tsx
      <div className="mx-auto max-w-2xl px-6 py-16">
        <Link
          href="/"
          data-testid="back-link"
          className="font-mono text-xs uppercase tracking-widest text-paper/50 hover:text-caution"
        >
          ← Dashboard
        </Link>
        <div className={`mt-6 border-l-4 ${borderColor} border-y border-r border-paper/15 bg-panel p-6`}>
```

(Note the `mt-6` added to the incident card's className to keep spacing under the new link.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- tests/incident-detail-page.test.tsx`
Expected: PASS

- [ ] **Step 5: Run the full frontend suite one more time**

Run: `cd frontend && npm test`
Expected: PASS, all suites green

- [ ] **Step 6: Commit**

```bash
git add frontend/app/incidents/[id]/page.tsx frontend/tests/incident-detail-page.test.tsx
git commit -m "feat: add back-link from incident detail to the dashboard"
```
