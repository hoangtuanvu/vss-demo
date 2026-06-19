from app.config import get_settings
from app.wiring import build_app

app, _deps = build_app(get_settings())
