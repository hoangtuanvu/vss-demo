import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from app import store
from app.alert_rules import HAZARD_ALERT_RULES
from app.events import IncidentBroadcaster
from app.models import Severity, incident_to_dict
from app.poller import poll_loop
from app.streaming import get_video_duration_seconds, start_rtsp_loopback
from app.upload_state import ActiveUploadState

logger = logging.getLogger(__name__)


@dataclass
class AppDependencies:
    session_factory: object
    triage_graph: object
    chat_graph: object
    vss_client: object
    broadcaster: IncidentBroadcaster
    upload_dir: Path
    mediamtx_rtsp_url: str
    upload_state: ActiveUploadState
    poll_interval_seconds: int = 8
    active_rule_ids: list[str] = field(default_factory=list)
    active_sensor_id: str | None = None


async def _alert_event_generator(broadcaster: IncidentBroadcaster):
    queue = broadcaster.subscribe()
    try:
        while True:
            incident = await queue.get()
            yield {"event": "incident", "data": json.dumps(incident)}
    finally:
        broadcaster.unsubscribe(queue)


def create_app(deps: AppDependencies) -> FastAPI:
    stop_event = asyncio.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        poll_task = None
        if deps.triage_graph is not None:
            poll_task = asyncio.create_task(
                poll_loop(deps.vss_client, deps.triage_graph, deps.session_factory, deps.poll_interval_seconds, stop_event)
            )
        yield
        stop_event.set()
        if poll_task is not None:
            poll_task.cancel()

    app = FastAPI(title="Warehouse Safety Monitor Agent", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/upload")
    def upload(file: UploadFile = File(...)):
        if not deps.vss_client.health_check():
            raise HTTPException(status_code=503, detail="VSS is unreachable")
        deps.upload_dir.mkdir(parents=True, exist_ok=True)
        dest = deps.upload_dir / file.filename
        dest.write_bytes(file.file.read())
        try:
            stream_url = start_rtsp_loopback(dest, dest.stem, deps.mediamtx_rtsp_url)
        except Exception:
            raise HTTPException(status_code=502, detail="Failed to start video stream ingestion")

        deps.active_sensor_id = dest.stem
        deps.upload_state.filename = dest.name
        deps.upload_state.stream_start_at = datetime.utcnow()
        deps.upload_state.duration_seconds = get_video_duration_seconds(dest)

        if deps.active_rule_ids:
            try:
                deps.vss_client.delete_alert_rules(deps.active_rule_ids)
            except Exception:
                logger.warning("Failed to delete previous alert rules: %s", deps.active_rule_ids)
            deps.active_rule_ids = []
        try:
            deps.active_rule_ids = deps.vss_client.register_alert_rules(
                stream_url, dest.stem, HAZARD_ALERT_RULES
            )
        except Exception:
            logger.warning("Failed to register alert rules for stream %s", stream_url)

        return {"stream_url": stream_url, "filename": dest.name}

    @app.get("/uploads/{filename}")
    def get_uploaded_file(filename: str):
        safe_name = Path(filename).name
        path = deps.upload_dir / safe_name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        return FileResponse(path)

    @app.get("/incidents")
    def list_incidents_route():
        with deps.session_factory() as session:
            return [incident_to_dict(i) for i in store.list_incidents(session)]

    @app.get("/incidents/{incident_id}")
    def incident_detail(incident_id: int):
        with deps.session_factory() as session:
            incident = store.get_incident(session, incident_id)
            if incident is None:
                raise HTTPException(status_code=404, detail="incident not found")
            if incident.report_text is None and incident.severity == Severity.CRITICAL:
                report_text = deps.vss_client.generate_report(incident_to_dict(incident))
                incident = store.update_incident(session, incident.id, report_text=report_text)
            return incident_to_dict(incident)

    @app.post("/chat")
    def chat(payload: dict):
        message = payload["message"]
        if deps.active_sensor_id:
            message = f"For camera/sensor '{deps.active_sensor_id}': {message}"
        result = deps.chat_graph.invoke({"message": message, "intent": None, "answer": None})
        return {"answer": result["answer"]}

    @app.get("/alerts/stream")
    async def alerts_stream():
        return EventSourceResponse(_alert_event_generator(deps.broadcaster))

    return app
