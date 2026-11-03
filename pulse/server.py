import math
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from pulse.experiments import ExperimentStore
from pulse.models import Event, Experiment, FunnelRequest
from pulse.storage import EventStore, QueryEngine


def _check_events(items: list[Any]) -> tuple[list[Event], list[dict]]:
    """Check each event on its own: keep the good ones, report the bad ones.

    Returns (good_events, rejected) where each rejected entry says which
    position in the batch was bad and why, e.g.
    {"index": 2, "error": "event_name: Field required"}.
    """
    good: list[Event] = []
    rejected: list[dict] = []
    for index, item in enumerate(items):
        try:
            good.append(Event.model_validate(item))
        except ValidationError as e:
            # Turn pydantic's error list into one short readable sentence
            reasons = []
            for err in e.errors():
                field = ".".join(str(part) for part in err["loc"])
                reasons.append(f"{field}: {err['msg']}" if field else err["msg"])
            rejected.append({"index": index, "error": "; ".join(reasons)})
    return good, rejected


def _z_test_p_value(n1: int, c1: int, n2: int, c2: int) -> float | None:
    if n1 < 1 or n2 < 1 or (c1 + c2) == 0:
        return None
    p_pool = (c1 + c2) / (n1 + n2)
    if p_pool in (0.0, 1.0):
        return None
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return None
    z = abs(c1 / n1 - c2 / n2) / se
    return float(math.erfc(z / math.sqrt(2)))

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_DATA_DIR = Path.home() / ".pulse" / "data" / "events"

# Headers that tell a browser "any website may use this door"
_SDK_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "600",  # browser may remember this for 10 minutes
}


def _is_sdk_door(method: str, path: str) -> bool:
    """True for the few requests the SDKs make from other websites."""
    method = method.upper()
    if method == "POST" and path in ("/events", "/events/batch"):
        return True  # sending events
    if method == "GET" and path.startswith("/experiments/") and path.endswith("/assign"):
        return True  # asking which variant a user gets
    return False


def create_app(data_dir: Path) -> FastAPI:
    # One shared "key" for the event files: saving, merging and querying each
    # hold it, so a chart never reads files while they're being merged
    files_lock = threading.Lock()
    store = EventStore(data_dir=data_dir, files_lock=files_lock)
    query = QueryEngine(data_dir=data_dir, files_lock=files_lock)
    exp_store = ExperimentStore(data_dir=data_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.start()
        yield
        store.stop()

    app = FastAPI(title="Pulse", lifespan=lifespan)

    # Other websites (the developer's app) may only use the "SDK doors":
    # send events and ask for an experiment variant. Everything else (reading
    # analytics, creating experiments, flushing) is for the dashboard only,
    # which Pulse serves itself and so needs no extra permission.
    @app.middleware("http")
    async def allow_other_sites_only_for_sdk(request, call_next):
        # A browser asks first ("preflight") before sending JSON to another site
        if request.method == "OPTIONS":
            asked_method = request.headers.get("access-control-request-method", "")
            if _is_sdk_door(asked_method, request.url.path):
                return Response(status_code=204, headers=_SDK_CORS_HEADERS)
            return Response(status_code=400)

        response = await call_next(request)
        if _is_sdk_door(request.method, request.url.path):
            response.headers.update(_SDK_CORS_HEADERS)
        return response

    @app.get("/", response_class=HTMLResponse)
    def read_root():
        # Say "utf-8" explicitly: on Windows Python otherwise guesses a different
        # alphabet (cp1252) and characters like — turn into â€”
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/pulse.js")
    def serve_sdk():
        return Response(
            content=(STATIC_DIR / "pulse.js").read_text(encoding="utf-8"),
            media_type="application/javascript",
        )

    @app.get("/chart.umd.min.js")
    def serve_chart_library():
        # The dashboard's chart library, shipped inside Pulse so charts work
        # without internet (it used to be downloaded from a CDN website)
        return Response(
            content=(STATIC_DIR / "chart.umd.min.js").read_text(encoding="utf-8"),
            media_type="application/javascript",
            headers={"Cache-Control": "max-age=86400"},  # browser may keep it a day
        )

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    @app.post("/events", status_code=201)
    def ingest_event(event: Event) -> dict:
        store.add(event)
        return {"received": 1}

    @app.post("/events/batch", status_code=201)
    def ingest_events(events: list[Any] = Body(...)) -> dict:
        # Accept the batch as a plain list and check each event separately,
        # so one broken event doesn't make us throw away the good ones.
        good, rejected = _check_events(events)
        store.add_many(good)
        return {"received": len(good), "rejected": rejected}

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

    @app.post("/flush")
    def flush_events():
        # Force flush pending events to disk
        count = store.flush()
        return {"flushed": count}

    @app.get("/analytics/events")
    def analytics_event_counts():
        # Flush buffered events first
        store.flush()
        return query.event_counts()

    @app.get("/analytics/over-time")
    def analytics_events_over_time(granularity: str = "hour"):
        store.flush()
        if granularity not in ("hour", "day"):
            granularity = "hour"
        return query.events_over_time(granularity)

    @app.get("/analytics/top-users")
    def analytics_top_users(limit: int = 10):
        store.flush()
        return query.top_users(limit)

    @app.post("/analytics/funnel")
    def analytics_funnel(req: FunnelRequest):
        store.flush()
        return query.funnel(req.steps)

    @app.get("/analytics/retention")
    def analytics_retention():
        store.flush()
        return query.retention()

    @app.get("/analytics/funnel-suggestions")
    def analytics_funnel_suggestions(max_depth: int = 4, min_users: int = 2, limit: int = 20):
        store.flush()
        suggestions = query.detect_funnel_patterns(max_depth, min_users, limit)
        return {"suggestions": suggestions}

    @app.post("/experiments", status_code=201)
    def create_experiment(exp: Experiment):
        try:
            return exp_store.create(exp)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @app.get("/experiments")
    def list_experiments():
        return exp_store.list_all()

    @app.get("/experiments/{name}/assign")
    def assign_variant(name: str, user_id: str):
        exp = exp_store.get(name)
        if not exp:
            raise HTTPException(status_code=404, detail="Experiment not found")
        variant = exp_store.assign(exp, user_id)
        store.add(Event(
            event_name="$experiment_assignment",
            user_id=user_id,
            properties={"experiment": name, "variant": variant},
        ))
        return {"experiment": name, "user_id": user_id, "variant": variant}

    @app.get("/experiments/{name}/results")
    def get_experiment_results(name: str):
        exp = exp_store.get(name)
        if not exp:
            raise HTTPException(status_code=404, detail="Experiment not found")

        # Save buffered events first so brand-new assignments/conversions count
        store.flush()
        rows = query.experiment_results(name, exp.goal_event)
        variant_results = [
            {
                "variant": r["variant"],
                "users": r["users"],
                "conversions": r["conversions"],
                "conversion_rate": round(r["conversions"] / r["users"], 4) if r["users"] > 0 else 0.0,
            }
            for r in rows
        ]

        p_value = None
        significant = False
        winner = None

        if len(variant_results) == 2:
            v1, v2 = variant_results
            p_value = _z_test_p_value(v1["users"], v1["conversions"], v2["users"], v2["conversions"])
            if p_value is not None:
                significant = p_value < 0.05
                if significant:
                    winner = max(variant_results, key=lambda v: v["conversion_rate"])["variant"]

        return {
            "experiment": name,
            "goal_event": exp.goal_event,
            "status": exp.status,
            "variants": variant_results,
            "p_value": round(p_value, 4) if p_value is not None else None,
            "significant": significant,
            "winner": winner,
        }

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
