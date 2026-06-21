from pathlib import Path

from fastapi import FastAPI

from app.config import Settings
from app.db import make_engine, make_session_factory
from app.events import broadcaster
from app.graphs.chat import build_chat_graph
from app.graphs.triage import build_triage_graph
from app.llm import get_chat_model
from app.main import AppDependencies, create_app
from app.models import Base
from app.vss_client import VSSClient


def build_app(settings: Settings) -> tuple[FastAPI, AppDependencies]:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)
    llm = get_chat_model(settings)
    vss_client = VSSClient(settings.vss_agent_base_url, settings.vss_alert_bridge_base_url)
    triage_graph = build_triage_graph(
        llm, vss_client, session_factory, settings.slack_webhook_url,
        settings.dedupe_window_seconds, broadcaster,
    )
    chat_graph = build_chat_graph(vss_client)
    deps = AppDependencies(
        session_factory=session_factory,
        triage_graph=triage_graph,
        chat_graph=chat_graph,
        vss_client=vss_client,
        broadcaster=broadcaster,
        upload_dir=Path("uploads"),
        mediamtx_rtsp_url=settings.mediamtx_rtsp_url,
        poll_interval_seconds=settings.poll_interval_seconds,
    )
    return create_app(deps), deps
