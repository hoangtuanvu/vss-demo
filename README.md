# vss-demo — Warehouse Safety Monitor

Agentic warehouse safety monitor built on NVIDIA's
[VSS `warehouse` blueprint](https://build.nvidia.com/nvidia/video-search-and-summarization/blueprintcard)
+ LangGraph. Takes an uploaded video, replays it as a simulated live camera
feed, watches it for 5 hazard types, triages/dedupes detections, escalates
critical incidents (Slack/webhook), drafts incident reports, and answers
natural-language questions about what happened.

Design rationale, architecture, and
out-of-scope decisions: `docs/superpowers/specs/2026-06-19-warehouse-safety-monitor-design.md`.
Implementation plans: `docs/superpowers/plans/`.

## Hazards detected

PPE compliance, restricted-zone intrusion, forklift–pedestrian proximity,
fall/man-down, spill/obstruction in walkway.

## Architecture

```
Video upload -> Frontend (Next.js) -> Agent (FastAPI)
                                          | ffmpeg loopback -> mediamtx RTSP
                                          v
                       VSS warehouse profile (dense-captioning + 5 alert
                       rules, on a Brev GPU) — or infra/mock_vss.py locally
                                          | polled
                                          v
                       Agent: LangGraph triage (classify severity, dedupe,
                       persist, escalate) -> incident store -> SSE -> Frontend
```

The agent owns its own incident store and all triage/report/chat logic; VSS
is used only for ingestion, alerting, and ask-video/report generation — not
its own Elasticsearch/analytics stack. See the design doc for why.

### VSS deployment (Brev)

Real VSS runs as its own [NVIDIA Brev](https://brev.nvidia.com) GPU instance
(`vss-warehouse`, 2×A6000), deployed via the `vss-deploy-profile` skill from
[nvidia/skills](https://github.com/nvidia/skills) with the `warehouse`
profile + an NGC API key. Two services on that box, hit directly
by IP (not behind Brev's HAProxy):

- `vss-agent`, port `8000` — `POST /chat` (drives ask-video / report
  generation). `VSS_AGENT_BASE_URL`.
- `alert-bridge`, port `9080` — alert-rule CRUD + incident feed
  (Elasticsearch-backed on VSS's side; the agent only reads it).
  `VSS_ALERT_BRIDGE_BASE_URL`.

Both ports opened via `sudo ufw allow 8000/tcp` / `9080/tcp` on the
instance — no auth in front (fine for a time-boxed demo, not production).
Point the agent's env vars at `http://<brev-instance-ip>:8000` / `:9080`.

Deploying/redeploying to Brev is billed GPU compute — confirm with the user
before running any launch command. There's no committed step-by-step
`infra/brev_deploy.md` runbook yet; see
`docs/superpowers/specs/2026-06-21-real-vss-integration-design.md` for the
narrative of what was actually deployed.

## Repo layout

```
agent/          FastAPI + LangGraph backend
frontend/       Next.js + Tailwind dashboard
infra/          mediamtx config, mock VSS server, alert rule notes
docs/           design specs + implementation plans
sample-videos/  one short clip per hazard type
```

## Running locally

```bash
docker compose up -d --build
```

Brings up `mediamtx` (RTSP), `agent` (`:8000`), `frontend` (`:3001`). The
agent needs a reachable VSS (real Brev deployment, or `infra/mock_vss.py`
for local dev without a GPU/NIM key) — see `docs/local-testing.md` for the
exact env vars and a step-by-step mock vs. real walkthrough.

Backend tests: `cd agent && python -m pytest`
Frontend tests: `cd frontend && npm test`

## Status

Working end-to-end pipeline (upload -> simulated stream -> VSS alerts ->
triage -> incident store -> live SSE feed -> chat). See
`docs/superpowers/plans/` for in-progress/planned work — not every plan doc
is fully merged; check the code, not just the doc, before relying on a
described feature.

More detail (module-by-module backend/frontend guide, conventions): `CLAUDE.md`.
