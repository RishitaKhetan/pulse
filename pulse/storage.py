import atexit
import json
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from pulse.models import Event

_SCHEMA = pa.schema([
    pa.field("event_id", pa.string()),
    pa.field("event_name", pa.string()),
    pa.field("timestamp", pa.timestamp("us", tz="UTC")),
    pa.field("user_id", pa.string()),
    pa.field("session_id", pa.string()),
    pa.field("properties", pa.string()),
])


class EventStore:
    def __init__(self, data_dir: Path, flush_interval: int = 30):
        self._data_dir = data_dir
        self._flush_interval = flush_interval
        self._buffer: deque[Event] = deque(maxlen=50_000)
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def start(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        atexit.register(self.flush)
        self._schedule_flush()

    def stop(self) -> None:
        if self._timer:
            self._timer.cancel()
        self.flush()

    def add(self, event: Event) -> None:
        with self._lock:
            self._buffer.append(event)

    def add_many(self, events: list[Event]) -> None:
        with self._lock:
            self._buffer.extend(events)

    def buffered(self) -> list[Event]:
        with self._lock:
            return list(self._buffer)

    def flush(self) -> int:
        with self._lock:
            if not self._buffer:
                return 0
            events = list(self._buffer)
            self._buffer.clear()

        self._write_parquet(events)
        return len(events)

    def _write_parquet(self, events: list[Event]) -> None:
        now = datetime.now(timezone.utc)
        day_dir = self._data_dir / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / now.strftime(f"%H_{int(now.timestamp())}.parquet")

        table = pa.table(
            {
                "event_id": [e.event_id for e in events],
                "event_name": [e.event_name for e in events],
                "timestamp": pa.array(
                    [e.timestamp for e in events],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "user_id": [e.user_id for e in events],
                "session_id": [e.session_id for e in events],
                "properties": [json.dumps(e.properties) for e in events],
            },
            schema=_SCHEMA,
        )
        pq.write_table(table, path)

    def _schedule_flush(self) -> None:
        self._timer = threading.Timer(self._flush_interval, self._flush_and_reschedule)
        self._timer.daemon = True
        self._timer.start()

    def _flush_and_reschedule(self) -> None:
        self.flush()
        self._schedule_flush()


class QueryEngine:
    """Read-only DuckDB query layer over the Parquet event store."""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._conn = duckdb.connect()
        self._lock = threading.Lock()

    def _glob(self) -> str:
        return str(self._data_dir / "**" / "*.parquet").replace("\\", "/")

    def _has_data(self) -> bool:
        return any(self._data_dir.rglob("*.parquet"))

    def _run(self, sql: str) -> list[tuple]:
        with self._lock:
            return self._conn.execute(sql).fetchall()

    def _to_event(self, row: tuple) -> Event:
        event_id, event_name, timestamp, user_id, session_id, properties = row
        return Event(
            event_id=event_id,
            event_name=event_name,
            timestamp=timestamp,
            user_id=user_id,
            session_id=session_id,
            properties=json.loads(properties) if properties else {},
        )

    def recent_events(self, limit: int = 50) -> list[Event]:
        if not self._has_data():
            return []
        glob = self._glob()
        rows = self._run(
            f"SELECT event_id, event_name, timestamp, user_id, session_id, properties "
            f"FROM read_parquet('{glob}', union_by_name=true) "
            f"ORDER BY timestamp DESC LIMIT {limit}"
        )
        return [self._to_event(r) for r in rows]

    def event_counts(self) -> list[dict]:
        if not self._has_data():
            return []
        glob = self._glob()
        rows = self._run(
            f"SELECT event_name, COUNT(*) as count "
            f"FROM read_parquet('{glob}', union_by_name=true) "
            f"GROUP BY event_name ORDER BY count DESC"
        )
        return [{"event_name": r[0], "count": r[1]} for r in rows]

    def events_over_time(self, granularity: str = "hour") -> list[dict]:
        if not self._has_data():
            return []
        trunc = "hour" if granularity == "hour" else "day"
        glob = self._glob()
        rows = self._run(
            f"SELECT date_trunc('{trunc}', timestamp) as bucket, COUNT(*) as count "
            f"FROM read_parquet('{glob}', union_by_name=true) "
            f"GROUP BY bucket ORDER BY bucket"
        )
        return [{"bucket": str(r[0]), "count": r[1]} for r in rows]

    def top_users(self, limit: int = 10) -> list[dict]:
        if not self._has_data():
            return []
        glob = self._glob()
        rows = self._run(
            f"SELECT user_id, COUNT(*) as event_count "
            f"FROM read_parquet('{glob}', union_by_name=true) "
            f"WHERE user_id IS NOT NULL "
            f"GROUP BY user_id ORDER BY event_count DESC LIMIT {limit}"
        )
        return [{"user_id": r[0], "event_count": r[1]} for r in rows]

    def funnel(self, steps: list[str]) -> list[dict]:
        if not self._has_data() or not steps:
            return []
        glob = self._glob()

        # Escape single quotes in step names
        safe = [s.replace("'", "''") for s in steps]

        step_cases = ", ".join(
            f"MAX(CASE WHEN event_name = '{s}' THEN 1 ELSE 0 END) as s{i}"
            for i, s in enumerate(safe)
        )
        step_counts = ", ".join(
            f"SUM({'*'.join(f's{j}' for j in range(i + 1))}) as step_{i}"
            for i in range(len(safe))
        )

        rows = self._run(f"""
            WITH base AS (
                SELECT user_id, event_name
                FROM read_parquet('{glob}', union_by_name=true)
                WHERE user_id IS NOT NULL
            ),
            user_steps AS (
                SELECT user_id, {step_cases} FROM base GROUP BY user_id
            )
            SELECT {step_counts} FROM user_steps
        """)

        if not rows:
            return []

        counts = [rows[0][i] or 0 for i in range(len(steps))]
        top = counts[0] or 1
        result = []
        for i, step in enumerate(steps):
            prev = counts[i - 1] if i > 0 else counts[0]
            result.append({
                "step": step,
                "users": counts[i],
                "conversion_from_previous": round(counts[i] / prev, 3) if prev > 0 else 1.0,
                "conversion_from_top": round(counts[i] / top, 3),
            })
        return result

    def experiment_results(self, experiment_name: str, goal_event: str) -> list[dict]:
        if not self._has_data():
            return []
        glob = self._glob()
        safe_exp = experiment_name.replace("'", "''")
        safe_goal = goal_event.replace("'", "''")
        rows = self._run(f"""
            WITH assignments AS (
                SELECT
                    json_extract_string(properties, '$.variant') AS variant,
                    user_id
                FROM read_parquet('{glob}', union_by_name=true)
                WHERE event_name = '$experiment_assignment'
                  AND json_extract_string(properties, '$.experiment') = '{safe_exp}'
                  AND user_id IS NOT NULL
            ),
            conversions AS (
                SELECT DISTINCT user_id
                FROM read_parquet('{glob}', union_by_name=true)
                WHERE event_name = '{safe_goal}'
                  AND user_id IS NOT NULL
            ),
            per_variant AS (
                SELECT variant, COUNT(DISTINCT user_id) AS users
                FROM assignments
                GROUP BY variant
            ),
            converted AS (
                SELECT a.variant, COUNT(DISTINCT a.user_id) AS conversions
                FROM assignments a
                INNER JOIN conversions c ON a.user_id = c.user_id
                GROUP BY a.variant
            )
            SELECT p.variant, p.users, COALESCE(cv.conversions, 0) AS conversions
            FROM per_variant p
            LEFT JOIN converted cv ON p.variant = cv.variant
            ORDER BY p.variant
        """)
        return [{"variant": r[0], "users": r[1], "conversions": r[2]} for r in rows]

    def retention(self) -> list[dict]:
        if not self._has_data():
            return []
        glob = self._glob()
        rows = self._run(f"""
            WITH first_seen AS (
                SELECT user_id, MIN(DATE_TRUNC('day', timestamp)) AS cohort
                FROM read_parquet('{glob}', union_by_name=true)
                WHERE user_id IS NOT NULL
                GROUP BY user_id
            ),
            activity AS (
                SELECT DISTINCT user_id, DATE_TRUNC('day', timestamp) AS active_day
                FROM read_parquet('{glob}', union_by_name=true)
                WHERE user_id IS NOT NULL
            ),
            cohort_sizes AS (
                SELECT cohort, COUNT(*) AS total_users FROM first_seen GROUP BY cohort
            )
            SELECT
                CAST(f.cohort AS VARCHAR)   AS cohort,
                DATEDIFF('day', f.cohort, a.active_day) AS day_number,
                COUNT(DISTINCT a.user_id)   AS retained_users,
                cs.total_users,
                ROUND(COUNT(DISTINCT a.user_id) * 100.0 / cs.total_users, 1) AS retention_rate
            FROM first_seen f
            JOIN activity a ON f.user_id = a.user_id
            JOIN cohort_sizes cs ON f.cohort = cs.cohort
            WHERE DATEDIFF('day', f.cohort, a.active_day) BETWEEN 0 AND 30
            GROUP BY f.cohort, day_number, cs.total_users
            ORDER BY f.cohort, day_number
        """)
        return [
            {
                "cohort": r[0][:10],
                "day": r[1],
                "retained_users": r[2],
                "cohort_size": r[3],
                "retention_rate": float(r[4]),
            }
            for r in rows
        ]
