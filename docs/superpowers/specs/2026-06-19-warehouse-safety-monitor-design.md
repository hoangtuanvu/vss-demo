# Warehouse Safety Monitor — Design

**Date:** 2026-06-19
**Status:** Approved for planning
**Repo:** `git@github.com:hoangtuanvu/vss-demo.git` (public)

## Purpose

Take-home assignment for an NVIDIA interview process. Goal: build an agentic
application that solves a real customer problem, using an NVIDIA AI Blueprint
(`build.nvidia.com`) and NVIDIA's official Agent Skills
(`github.com/NVIDIA/skills`). The interview will reference this application
directly, so the build must demonstrate genuine use of both the blueprint and
the skills, not just a description of them.

Scenario: **Warehouse Safety Monitor** — an agent that watches warehouse
video for safety hazards, triages and escalates real incidents, drafts
incident reports, and answers natural-language questions about what
happened.

## Constraints (from stakeholder)

- **Compute:** NVIDIA Brev (cloud GPU launchable) + NGC API key. No local GPU.
- **Harness:** LangGraph for the application's own agent logic.
- **Frontend:** required — standalone custom dashboard, not an embed of
  VSS's built-in Next.js frontend.
- **Video input:** file upload only (no real camera). Chunked upload is
  used to simulate a live stream rather than batch-processing the whole file
  at once.
- **Hazards (all 5, no scope cut):** PPE compliance, restricted-zone
  intrusion, forklift–pedestrian proximity, fall/man-down detection,
  spill/obstruction in walkway.
- **Agent tier:** "Full ops agent" — triage + severity classification +
  dedupe, auto incident report drafting, conversational Q&A over footage,
  autonomous escalation (webhook/Slack), and SOP-improvement suggestions.
- **Timeline:** development starts 2026-06-19, interview ~2026-06-23/24.
  Build the working integration path first; polish only with time left over.
- **Target repo:** push to the existing `hoangtuanvu/vss-demo` GitHub repo
  (public, remote already configured).

## Why this approach (vs. alternatives considered)

Two alternatives were rejected:

- **Full VSS stack** (Elasticsearch, Kafka, video-analytics-api, full
  behavior-analytics service) — most faithful to the blueprint, but too many
  moving parts to stand up reliably on a multi-day budget.
- **Skip VSS deployment, call Cosmos-Reason2/Nemotron NIMs directly** and
  build the CV/alert pipeline from scratch in LangGraph — fast and fully
  controlled, but doesn't satisfy the assignment's explicit ask to use the
  *blueprint* and its `vss-*` skills, which is what's being evaluated.

**Chosen approach: lean VSS core + LangGraph ops layer.** Deploy VSS's
`warehouse` profile for ingestion, dense-captioning, and alert detection
only. Skip VSS's own analytics stack (Elasticsearch/video-analytics-api).
The LangGraph agent owns its own lightweight incident store and all
triage/escalation/reporting/chat logic, calling VSS's MCP/REST endpoints as
tools. This genuinely deploys and uses the blueprint and the skills, stays
buildable in the available time, and leaves the "agentic" work — the part
actually being assessed — in the LangGraph layer where it's visible.

## Architecture

```
[Video file] --upload--> [Frontend: Next.js]
                              |
                              v
                  [LangGraph Agent Service (FastAPI)]
                   - upload handler: chunks video, feeds
                     ffmpeg -> mediamtx RTSP loopback
                              |
                              v
              [VSS warehouse profile, deployed on Brev GPU]
              - live RTSP ingestion
              - dense-captioning (Cosmos-Reason2 VLM)
              - 5 alert rules (vss-manage-alerts):
                PPE / zone-intrusion / forklift-proximity /
                fall-detection / spill-obstruction
              - MCP/REST endpoints (alerts, ask-video,
                summarize, query-analytics, gen-report)
                              |
                              v (alert/event stream, polled)
                  [LangGraph Agent Service]
                   - Triage graph: classify severity, dedupe
                   - Incident store: Postgres (own, not VSS's ES)
                   - Escalation: webhook/Slack on critical
                   - Report node: calls vss-generate-video-report
                   - Chat graph: vss-ask-video / vss-query-analytics
                              |
                              v
                  [Frontend: live alert feed, incident
                   detail + report, chat panel, stats]
```

### NVIDIA Skills usage

Two distinct roles for skills in this project — keep them separate in the
README so the interview reviewers see both:

1. **Dev-time ops skills (used now, via Claude Code, to build/operate VSS):**
   `vss-deploy-profile` (deploy the `warehouse` profile on Brev),
   `vss-deploy-dense-captioning` + `vss-manage-alerts` (configure the 5
   hazard alert rules), `vss-generate-video-calibration` (camera config for
   the upload-as-stream source). These are run from this Claude Code session
   against the Brev deployment, not shipped as part of the app.
2. **Runtime capabilities the app depends on:** the application's LangGraph
   tools call the underlying VA-MCP/REST endpoints that
   `vss-ask-video`, `vss-query-analytics`, `vss-search-archive`, and
   `vss-generate-video-report` describe. The skills define *how a developer
   configures* these capabilities; the app calls the resulting APIs directly.

## LangGraph agent design

All LLM calls use `ChatNVIDIA` (`langchain-nvidia-ai-endpoints`) against
NIM models on `build.nvidia.com` with the NGC API key — same stack
end-to-end, no other LLM vendor in the agent loop.

### Monitoring/Triage graph

Event-driven: an async poll loop (~5-10s) against VSS's alert endpoint
invokes this graph once per batch of new events.

```
poll_alerts -> classify_severity (Nemotron-Nano-9B-v2:
                 hazard type + VLM caption + history -> critical/warning/info)
            -> dedupe (check incident store for open incident,
                 same hazard+zone, within time window -> merge or new)
            -> persist_incident (Postgres)
            -> [branch on severity]
                 critical -> generate_report (vss-generate-video-report)
                          -> escalate_notify (Slack/webhook)
                 warning  -> surface in feed only
                 info     -> log, suppressed from main feed
```

### Chat/Q&A graph

Request/response, one invocation per user chat message.

```
parse_intent -> route:
   - specific clip question      -> vss-ask-video
   - aggregate/stats question    -> vss-query-analytics
   - "search footage for X"      -> vss-search-archive
   - "how do we prevent this"    -> SOP-suggestion (LLM drafts corrective
                                     text from incident pattern, no VSS call)
            -> synthesize_answer (LLM composes final NL reply)
```

The triage graph's severity classification and dedupe is the core agentic
contribution: VSS supplies raw VLM-detected events, the agent decides what's
real and what matters, merges repeated detections of the same incident, and
escalates only genuine hazards. The SOP-suggestion node is the clearest
"full ops agent" differentiator for the interview discussion.

## Frontend

Next.js + Tailwind, standalone (does not embed VSS's own frontend):

1. **Upload** — drop a video file, kicks off ingestion.
2. **Live Monitor** — simulated camera view + live alert feed pushed over
   SSE/WebSocket, severity-color badges, hazard-type icons.
3. **Incident detail** — VLM caption, snapshot, severity, auto-generated
   report, escalation status.
4. **Chat panel** — "ask the footage" Q&A and SOP-suggestion replies.
5. **Stats** — incident counts by hazard type and severity over time.

## End-to-end data flow

1. User uploads a video file → backend saves it, starts an ffmpeg → mediamtx
   RTSP loopback that replays the file as a simulated live camera.
2. VSS's `warehouse` profile ingests that RTSP source, running
   dense-captioning and the 5 alert rules in real time as the simulated
   stream plays.
3. The monitoring graph polls VSS's alert endpoint, triages each new event,
   persists it to Postgres, and pushes it to the frontend over SSE.
4. Critical incidents trigger an auto-generated report and a Slack/webhook
   notification.
5. Chat messages run the chat graph, which calls VSS tools as needed and
   returns a natural-language answer.
6. Clicking an incident shows full detail, generating a report on demand if
   one wasn't already produced.

## Error handling

- **VSS unreachable:** backend health-checks VSS before accepting an upload;
  frontend shows a clear error rather than silently failing.
- **NIM API timeout/rate-limit:** tool wrapper retries with backoff;
  frontend shows a degraded-mode banner if retries exhaust.
- **RTSP loopback failure:** fall back to direct batch processing of the
  uploaded file (skip the live-stream simulation) rather than failing the
  upload outright.
- **Dedupe miscalculation:** the raw VSS alert payload is always persisted
  regardless of dedupe/triage outcome, so no event is silently dropped even
  if triage logic misclassifies it.
- **Chat tool call failure:** the chat graph catches the failure and returns
  a graceful "couldn't fetch that, try rephrasing" reply instead of erroring
  out to the user.

## Testing strategy

- **Unit tests** (pytest) for the triage/dedupe/intent-routing nodes, with
  VSS and NIM responses mocked.
- **Integration check:** one short sample clip per hazard run end-to-end
  through the live Brev deployment, asserting the correct incident is
  created. This stays a manual/integration check rather than CI — the VLM
  can't be meaningfully mocked for a true integration test.
- **Frontend:** component tests plus a manual demo script. That script
  doubles as the interview walkthrough.

## Repo layout

```
agent/          LangGraph + FastAPI backend
frontend/       Next.js dashboard
infra/          Brev launch config, VSS deploy notes, skills usage log
docs/           this design doc, demo script
sample-videos/  one short clip per hazard
```

## Out of scope

- VSS's own Elasticsearch-backed video-analytics-api and behavior-analytics
  service (the agent owns its own incident store instead).
- Embedding or extending VSS's built-in Next.js frontend.
- Real camera/RTSP hardware integration (upload + simulated stream only).
- Automated CI integration tests against the live VLM (manual/integration
  only, per Testing strategy above).

## Open implementation items

- Source one short sample clip per hazard (PPE, zone intrusion,
  forklift-proximity, fall, spill) — not a design decision, tracked as
  implementation work.
- Exact natural-language phrasing of each of the 5 VSS alert rules.
- Slack webhook URL / target channel for escalation (or generic webhook if
  Slack isn't set up in time).
