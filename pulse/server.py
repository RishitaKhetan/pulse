"""
This file starts a small local web server using FastAPI.

Think of it like this: when Pulse "runs", it's really just a program
sitting on your computer, listening for two kinds of requests:
  1. Requests from your app's SDK, sending events ("a user clicked X")
  2. Requests from your browser, asking to see the dashboard

Right now, in Phase 0, this server doesn't do any of that real work yet.
It just proves the whole chain works: `pulse start` -> server boots ->
browser opens -> you see a page. Every later phase adds one more piece
on top of this.
"""

import threading
import time
import webbrowser
from collections import deque
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from pulse.models import Event

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Pulse")

# Capped at 50k to bound memory use before Phase 2 adds Parquet persistence.
_buffer: deque[Event] = deque(maxlen=50_000)
_buffer_lock = threading.Lock()


@app.get("/", response_class=HTMLResponse)
def read_root():
    index_file = STATIC_DIR / "index.html"
    return index_file.read_text()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/events", status_code=201)
def ingest_event(event: Event) -> dict:
    with _buffer_lock:
        _buffer.append(event)
    return {"received": 1}


@app.post("/events/batch", status_code=201)
def ingest_events(events: list[Event]) -> dict:
    with _buffer_lock:
        _buffer.extend(events)
    return {"received": len(events)}


@app.get("/events")
def list_events(limit: int = 50) -> list[Event]:
    with _buffer_lock:
        events = list(_buffer)
    return events[-limit:]


def _open_browser_after_delay(url: str, delay_seconds: float = 1.0):
    # We wait a moment before opening the browser, so the server
    # has time to actually start accepting requests first.
    time.sleep(delay_seconds)
    webbrowser.open(url)


def run_server(port: int = 4747, open_browser: bool = True):
    url = f"http://localhost:{port}"
    print(f"\n  Pulse is starting at {url}\n")

    if open_browser:
        # Run the browser-opening in the background so it doesn't
        # block the server from starting.
        threading.Thread(
            target=_open_browser_after_delay, args=(url,), daemon=True
        ).start()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")