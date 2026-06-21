# Frontend Dashboard Redesign — Design

**Date:** 2026-06-21
**Status:** Approved for planning
**Repo:** `git@github.com:hoangtuanvu/vss-demo.git` (public)

## Purpose

The frontend currently splits the core demo loop (upload a clip → watch it get
triaged → ask questions → check stats) across three separate pages
(`/upload`, `/monitor`, `/stats`) with no guided path between them — the user
has to manually navigate after uploading to see anything happen. The
industrial/hazard-tape visual language itself is fine; the navigation flow is
the problem. This collapses the core loop into a single dashboard page.

## Decisions

1. **One route, not three.** `/upload`, `/monitor`, `/stats` are deleted.
   Everything lives at `/`. `/incidents/[id]` stays as a separate
   drill-down route (gets a "← Dashboard" back link).
2. **Layout: header + two-column body.** Header holds the title, a live
   connection-status indicator, and a compact inline upload control. Body is
   a two-column grid: left (wide) is the incident feed, right (narrow)
   stacks the chat panel above a stats summary.
3. **Single source of incident state.** The page owns the incidents array
   (seeded by `fetchIncidents()` on mount, appended via the existing
   `subscribeToAlerts()` SSE subscription, deduped by id). `IncidentFeed`
   and `StatsSummary` both receive this array as a prop — neither fetches
   independently. This makes stats live (today's `/stats` only fetched
   once on mount) and removes any chance of the feed and stats drifting
   out of sync.
4. **Extract three components, keep one unchanged.** `UploadBar`,
   `IncidentFeed`, `StatsSummary` are new, extracted from today's
   `/upload`, `/monitor`, `/stats` page bodies respectively, each taking
   data via props rather than owning its own data-fetching (except
   `UploadBar`, which still owns the upload mutation itself).
   `ChatPanel` is unchanged.
5. **No new backend changes.** `lib/api.ts` is untouched — same four
   functions (`uploadVideo`, `fetchIncidents`, `fetchIncident`,
   `sendChatMessage`, `subscribeToAlerts`) cover everything this needs.

## Components

| File | Change |
|---|---|
| `frontend/app/page.tsx` | Rewritten: composes header (title + status + `UploadBar`) + two-column body (`IncidentFeed` left, `ChatPanel` + `StatsSummary` right) |
| `frontend/components/UploadBar.tsx` | New — compact file input + button + inline status/error, condensed from `app/upload/page.tsx`'s form |
| `frontend/components/IncidentFeed.tsx` | New — incident-list rendering extracted from `app/monitor/page.tsx`; takes `incidents: Incident[]` as a prop, no longer owns the SSE subscription |
| `frontend/components/StatsSummary.tsx` | New — hazard:severity count table extracted from `app/stats/page.tsx`; takes `incidents: Incident[]` as a prop, no longer fetches independently |
| `frontend/components/ChatPanel.tsx` | Unchanged |
| `frontend/app/incidents/[id]/page.tsx` | Add a "← Dashboard" link back to `/`; otherwise unchanged |
| `frontend/app/upload/page.tsx`, `app/monitor/page.tsx`, `app/stats/page.tsx` | Deleted |

## Data flow

```
app/page.tsx
  ├─ useEffect: fetchIncidents() → seed state
  ├─ useEffect: subscribeToAlerts() → prepend new incident, dedup by id
  ├─ <UploadBar onUploadSuccess={...}/>      (shows inline status only;
  │                                           new incidents arrive via SSE,
  │                                           not via this callback)
  ├─ <IncidentFeed incidents={incidents} />
  ├─ <ChatPanel />
  └─ <StatsSummary incidents={incidents} />
```

## Error handling

Same patterns as today, relocated:
- Upload failure → inline error message inside `UploadBar`.
- SSE disconnect → existing browser-native `EventSource` retry behavior,
  unchanged — no new reconnect logic introduced.
- Empty states preserved verbatim: "No alerts yet. The floor is clear."
  (feed), "No incidents recorded this shift." (stats).

## Testing

| Old | New |
|---|---|
| `tests/page.test.tsx` | Rewritten as the dashboard integration test — renders the full page, asserts all four pieces compose and an uploaded/SSE-pushed incident shows up in both the feed and the stats count |
| `tests/upload-page.test.tsx` | `tests/upload-bar.test.tsx` — same assertions, against the extracted component |
| `tests/monitor-page.test.tsx` | `tests/incident-feed.test.tsx` — same assertions, against the extracted component, driven by props instead of a page-level SSE mock |
| `tests/stats-page.test.tsx` | `tests/stats-summary.test.tsx` — same assertions, against the extracted component, driven by props instead of `fetchIncidents` mock |
| `tests/chat-panel.test.tsx` | Unchanged |
| `tests/incident-detail-page.test.tsx` | Unchanged, plus one new assertion for the back link |

## Out of scope (this pass)

- Visual/styling changes — the hazard-tape industrial theme stays as-is.
- Chat correctness/backend hardening — separate spec, tracked independently.
- Any backend or `lib/api.ts` changes.
