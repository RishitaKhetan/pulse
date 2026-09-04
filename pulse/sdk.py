import atexit
import json
import threading
import urllib.request
import uuid
from typing import Any


class PulseClient:
    def __init__(self, endpoint: str = "http://localhost:4747", batch_size: int = 20, flush_interval: float = 5.0):
        self._endpoint = endpoint.rstrip("/")
        self._session_id = str(uuid.uuid4())
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._queue: list[dict] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        atexit.register(self.flush)

    def track(self, event_name: str, user_id: str | None = None, properties: dict[str, Any] | None = None) -> None:
        event = {
            "event_name": event_name,
            "user_id": user_id,
            "session_id": self._session_id,
            "properties": properties or {},
        }
        with self._lock:
            self._queue.append(event)
            should_flush = len(self._queue) >= self._batch_size

        if should_flush:
            threading.Thread(target=self._flush, daemon=True).start()
        elif self._timer is None:
            self._schedule_flush()

    def _schedule_flush(self) -> None:
        self._timer = threading.Timer(self._flush_interval, self._flush)
        self._timer.daemon = True
        self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            if not self._queue:
                return
            events = self._queue[:]
            self._queue.clear()
            self._timer = None

        self._send(events)

    def _send(self, events: list[dict]) -> None:
        try:
            data = json.dumps(events).encode()
            req = urllib.request.Request(
                f"{self._endpoint}/events/batch",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass  # never crash the caller's app

    def flush(self) -> None:
        self._flush()


_client: PulseClient | None = None


def init(endpoint: str = "http://localhost:4747") -> None:
    global _client
    _client = PulseClient(endpoint=endpoint)


def track(event_name: str, user_id: str | None = None, properties: dict[str, Any] | None = None) -> None:
    if _client is None:
        return
    _client.track(event_name, user_id=user_id, properties=properties)


def flush() -> None:
    if _client is not None:
        _client.flush()
