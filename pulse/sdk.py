"""Python SDK: send events from your backend or scripts to Pulse.

How it works (like a helper with a notepad):
- track() only writes the event on the notepad (an in-memory queue). That's
  very quick, so your app is not slowed down.
- ONE background "delivery" thread sends the notes to Pulse in batches: as
  soon as a batch is full, or every few seconds.
- If Pulse can't be reached, the notes stay on the notepad and are retried
  next time. The notepad has a size limit, so memory can't grow forever.
- Nothing here ever raises an error into your app.
"""
import atexit
import http.client
import json
import threading
import urllib.request
import uuid
from collections import deque
from typing import Any
from urllib.parse import urlsplit


class PulseClient:
    def __init__(
        self,
        endpoint: str = "http://localhost:4747",
        batch_size: int = 100,      # bigger batches = fewer trips = less CPU
        flush_interval: float = 5.0,
        max_queue: int = 10_000,
    ):
        self._endpoint = endpoint.rstrip("/")
        self._base_path = urlsplit(self._endpoint).path  # e.g. "" or "/pulse"
        self._conn: http.client.HTTPConnection | None = None  # reused for every batch
        self._session_id = str(uuid.uuid4())
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        # The notepad. maxlen = when full, the OLDEST events are dropped.
        self._queue: deque[dict] = deque(maxlen=max_queue)
        self._lock = threading.Lock()        # protects the queue
        self._send_lock = threading.Lock()   # only one batch is sent at a time
        self._wake = threading.Event()       # "a batch is full, send now!"
        self._stopped = False
        self._worker: threading.Thread | None = None
        atexit.register(self.close)  # send what's left when the program exits

    def track(self, event_name: str, user_id: str | None = None, properties: dict[str, Any] | None = None) -> None:
        """Record an event. Returns immediately; sending happens in the background."""
        try:
            event = {
                "event_name": event_name,
                "user_id": user_id,
                "session_id": self._session_id,
                "properties": properties or {},
            }
            with self._lock:
                self._queue.append(event)
                batch_full = len(self._queue) >= self._batch_size
            self._start_worker()
            if batch_full:
                self._wake.set()
        except Exception:
            pass  # never crash the caller's app

    def flush(self) -> None:
        """Send everything that's waiting, right now (blocks until tried once)."""
        try:
            self._send_pending()
        except Exception:
            pass

    def pending(self) -> int:
        """How many events are waiting to be sent."""
        with self._lock:
            return len(self._queue)

    def close(self) -> None:
        """Stop the background thread and send what's left."""
        self._stopped = True
        self._wake.set()
        self.flush()

    def experiment(self, experiment_name: str, user_id: str) -> str | None:
        """Ask Pulse which variant this user gets (None if Pulse is unreachable)."""
        try:
            from urllib.parse import quote, urlencode
            qs = urlencode({"user_id": user_id})
            req = urllib.request.Request(
                f"{self._endpoint}/experiments/{quote(experiment_name)}/assign?{qs}",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read()).get("variant")
        except Exception:
            return None

    # ---- background delivery ----

    def _start_worker(self) -> None:
        """Start the single delivery thread the first time it's needed."""
        if self._worker is None and not self._stopped:
            with self._lock:
                if self._worker is None:
                    self._worker = threading.Thread(target=self._run, daemon=True)
                    self._worker.start()

    def _run(self) -> None:
        # Wake up when a batch is full, or every flush_interval seconds
        while not self._stopped:
            batch_full = self._wake.wait(timeout=self._flush_interval)
            self._wake.clear()
            try:
                # Woken by a full batch: send only FULL batches. Otherwise, while
                # one batch is on its way, the 2-3 events that arrive meanwhile
                # would each go out as their own tiny batch, over and over.
                # The timer (every flush_interval) sends whatever is left.
                self._send_pending(only_full_batches=batch_full and not self._stopped)
            except Exception:
                pass

    def _send_pending(self, only_full_batches: bool = False) -> None:
        with self._send_lock:
            while True:
                with self._lock:
                    if only_full_batches and len(self._queue) < self._batch_size:
                        return
                    batch = [self._queue.popleft()
                             for _ in range(min(self._batch_size, len(self._queue)))]
                if not batch:
                    return
                try:
                    self._send(batch)
                except Exception:
                    # Pulse unreachable: put the batch back at the front and try
                    # again next time (oldest first, so the order is kept)
                    with self._lock:
                        self._queue.extendleft(reversed(batch))
                    return

    def _send(self, events: list[dict]) -> None:
        """POST one batch to Pulse. Raises if it fails (caller retries later).

        Keeps one connection open and reuses it ("keep-alive"). Opening a new
        connection for every batch cost about 2-3 ms of CPU each time.
        """
        body = json.dumps(events).encode()
        try:
            if self._conn is None:
                self._conn = self._open_connection()
            self._conn.request(
                "POST", f"{self._base_path}/events/batch", body=body,
                headers={"Content-Type": "application/json"},
            )
            resp = self._conn.getresponse()
            resp.read()
            if resp.status >= 400:
                raise OSError(f"Pulse answered {resp.status}")
        except Exception:
            # Connection broken or Pulse restarted: start fresh next time
            if self._conn is not None:
                self._conn.close()
            self._conn = None
            raise

    def _open_connection(self) -> http.client.HTTPConnection:
        parts = urlsplit(self._endpoint)
        conn_class = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        return conn_class(parts.hostname, parts.port, timeout=5)


_client: PulseClient | None = None


def init(endpoint: str = "http://localhost:4747") -> None:
    global _client
    if _client is not None:
        _client.close()  # replacing an earlier client: send its events first
    _client = PulseClient(endpoint=endpoint)


def track(event_name: str, user_id: str | None = None, properties: dict[str, Any] | None = None) -> None:
    if _client is None:
        return
    _client.track(event_name, user_id=user_id, properties=properties)


def experiment(experiment_name: str, user_id: str) -> str | None:
    if _client is None:
        return None
    return _client.experiment(experiment_name, user_id)


def flush() -> None:
    if _client is not None:
        _client.flush()
