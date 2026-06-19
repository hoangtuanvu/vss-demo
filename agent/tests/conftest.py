import pytest

from app.db import make_engine, make_session_factory
from app.models import Base


@pytest.fixture
def session_factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)
