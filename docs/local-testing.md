# Local testing: mock VSS vs. real VSS

The agent never talks to anything except `VSS_BASE_URL`. Swapping that one
value between a local mock and a real Brev deployment is the only difference
between the two setups below — everything else (compose, frontend, mediamtx)
stays the same.

## 0. Start the base stack

```bash
docker compose up -d --build
```

This brings up `mediamtx` (RTSP loopback), `agent` (FastAPI on `:8000`), and
`frontend` (Next.js on `:3001`). `agent`'s default `VSS_BASE_URL` points at
`http://localhost:8001`, which is nothing — every `/upload` will 503 until
you point it somewhere real (below).

Check it's up: `curl localhost:8000/health` → `{"status":"ok"}`.

## 1a. Test against the mock VSS

`infra/mock_vss.py` is a stdlib-only fake implementing every endpoint
`VSSClient` calls (`/health`, `/alerts`, `/ask-video`, `/query-analytics`,
`/search-archive`, `/generate-report`). It returns 5 canned hazard alerts
(one per type) and generic mock answers — enough to drive the full
poll → triage → persist → SSE → chat pipeline with no GPU, no NIM key, no
real footage.

Run it on the host (not in a container — the agent reaches it via
`host.docker.internal`):

```bash
python3 infra/mock_vss.py
```

Point the agent at it and restart just that service:

```bash
VSS_BASE_URL=http://host.docker.internal:9000 docker compose up -d agent
```

**Limitation:** `classify_severity` calls the real NVIDIA NIM endpoint. With
no `NVIDIA_API_KEY` set, that call fails and every incident falls back to
`severity: warning` (this is the documented fallback behavior, not a bug).
To see real critical/warning/info classification, set `NVIDIA_API_KEY` in
the `agent` environment even while using the mock VSS — NIM and VSS are
independent.

To make the mock emit a *new* alert while a page is already watching
`/monitor` (to prove SSE is live, not historical), append an entry to the
`ALERTS` list in `infra/mock_vss.py` with the next `cursor` value and restart
the script — the next poll cycle (`POLL_INTERVAL_SECONDS`, default 8s) picks
it up.

## 1b. Test against a real VSS deployment

Real VSS is a billed Brev GPU instance — see
`docs/superpowers/plans/2026-06-19-warehouse-safety-monitor.md` Tasks 2–3 for
the deploy + alert-rule-configuration steps (not yet done in this repo as of
this writing; `infra/brev_deploy.md` and `infra/alert_rules.md` don't exist
yet). Once deployed:

```bash
VSS_BASE_URL=https://<your-brev-instance-url> \
NVIDIA_API_KEY=<your-ngc-key> \
docker compose up -d agent
```

Verify VSS itself is reachable before testing the agent:

```bash
curl -s "$VSS_BASE_URL/health"
```

## 2. Upload a clip

```bash
curl -s -i -X POST localhost:8000/upload \
  -F "file=@sample-videos/ppe.mp4;filename=ppe.mp4;type=video/mp4"
```

- `200` + `{"stream_url": "rtsp://mediamtx:8554/ppe"}` — VSS reachable, ffmpeg
  loopback started.
- `503` — VSS unreachable. Check `VSS_BASE_URL` is correct and the
  mock/real service is actually listening.
- `502` — ffmpeg failed to start (shouldn't happen in the container image,
  which has ffmpeg installed).

Or upload through the frontend at `http://localhost:3001/upload`.

## 3. Check the output

| Where | What to look for |
|---|---|
| `curl localhost:8000/incidents` | Full incident history (works regardless of when you opened any page) |
| `http://localhost:3001/stats` | Counts by `hazard_type:severity` |
| `http://localhost:3001/monitor` | **Live only** — open this *before* the next alert lands, it does not replay history |
| Chat panel on `/monitor` | Ask something; routes through `/chat` → intent classification → `ask-video`/`query-analytics`/`search-archive`/SOP node on the VSS client in use |
| `docker compose logs agent` | Poller/triage errors, e.g. malformed alert payloads |

## 4. Tear down

```bash
docker compose down
# if you started infra/mock_vss.py: Ctrl-C it, or
pkill -f infra/mock_vss.py
```
