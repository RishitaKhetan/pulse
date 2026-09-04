import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from pulse.models import Event, FunnelRequest
from pulse.storage import EventStore, QueryEngine

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_DATA_DIR = Path.home() / ".pulse" / "data" / "events"


def create_app(data_dir: Path) -> FastAPI:
    store = EventStore(data_dir=data_dir)
    query = QueryEngine(data_dir=data_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.start()
        yield
        store.stop()

    app = FastAPI(title="Pulse", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    def read_root():
        return (STATIC_DIR / "index.html").read_text()

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    @app.post("/events", status_code=201)
    def ingest_event(event: Event) -> dict:
        store.add(event)
        return {"received": 1}

    @app.post("/events/batch", status_code=201)
    def ingest_events(events: list[Event]) -> dict:
        store.add_many(events)
        return {"received": len(events)}

    @app.get("/events")
    def list_events(limit: int = 50) -> list[Event]:
        from_disk = query.recent_events(limit)
        from_buffer = store.buffered()

        # Buffer holds unflushed events not yet on disk — merge and sort
        on_disk_ids = {e.event_id for e in from_disk}
        buffer_only = [e for e in from_buffer if e.event_id not in on_disk_ids]

        combined = from_disk + buffer_only
        combined.sort(key=lambda e: e.timestamp)
        return combined[-limit:]

    @app.get("/analytics/events")
    def analytics_event_counts():
        return query.event_counts()

    @app.get("/analytics/over-time")
    def analytics_events_over_time(granularity: str = "hour"):
        if granularity not in ("hour", "day"):
            granularity = "hour"
        return query.events_over_time(granularity)

    @app.get("/analytics/top-users")
    def analytics_top_users(limit: int = 10):
        return query.top_users(limit)

    @app.post("/analytics/funnel")
    def analytics_funnel(req: FunnelRequest):
        return query.funnel(req.steps)

    @app.get("/analytics/retention")
    def analytics_retention():
        return query.retention()

    return app


def _open_browser_after_delay(url: str, delay: float = 1.0):
    time.sleep(delay)
    webbrowser.open(url)


def run_server(port: int = 4747, open_browser: bool = True, data_dir: Path = DEFAULT_DATA_DIR):
    app = create_app(data_dir)
    url = f"http://localhost:{port}"
    print(f"\n  Pulse is starting at {url}")
    print(f"  Data directory: {data_dir}\n")

    if open_browser:
        threading.Thread(target=_open_browser_after_delay, args=(url,), daemon=True).start()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
