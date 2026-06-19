from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def make_engine(database_url: str):
    if not database_url.startswith("sqlite"):
        return create_engine(database_url)
    kwargs = {"connect_args": {"check_same_thread": False}}
    if ":memory:" in database_url:
        kwargs["poolclass"] = StaticPool
    return create_engine(database_url, **kwargs)


def make_session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)
