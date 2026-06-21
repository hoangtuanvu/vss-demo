# Hazard Alert Rules

The 5 hazard alert rules registered against each uploaded clip's RTSP stream
via `alert-bridge`'s `POST /api/v1/realtime` (see `agent/app/alert_rules.py`
for the source of truth — this table documents the same data).

| alert_type | prompt |
|---|---|
| ppe | "Alert if a person is visible without a hard hat or hi-vis vest in a designated PPE-required zone." |
| zone_intrusion | "Alert if a person enters a marked restricted or no-go zone." |
| forklift_proximity | "Alert if a forklift and a pedestrian are within close proximity (less than approximately 2 meters) of each other." |
| fall | "Alert if a person is on the ground and not moving for more than a few seconds." |
| spill | "Alert if there is a liquid spill, dropped pallet, or other obstruction blocking a walkway." |

All 5 rules share the same `system_prompt` (see `SYSTEM_PROMPT` in
`agent/app/alert_rules.py`). Rules are registered per upload (see Task 8 of
`docs/superpowers/plans/2026-06-21-real-vss-integration.md`) against that
clip's RTSP loopback URL, and the previous upload's rules are deleted first
— this is a single-active-stream demo, not multi-tenant.
