"""Benchmark: how long does an experiment report take on 1 million events?

Target from CLAUDE.md: under 5 seconds, including the statistics summary.

Run it with:   python benchmarks/experiment_report.py
It uses a temporary folder and never touches your real Pulse data.
"""
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient

from pulse.experiments import ExperimentStore
from pulse.models import Experiment
from pulse.server import create_app
from pulse.storage import _SCHEMA

TOTAL_EVENTS = 1_000_000
USERS_IN_EXPERIMENT = 100_000
TARGET_SECONDS = 5.0


def make_data(data_dir: Path) -> None:
    """Write 1M events: one assignment per user, some signups, the rest page views."""
    rng = np.random.default_rng(42)
    exp = Experiment(name="signup_button", variants=["blue", "red"], goal_event="signup")
    store = ExperimentStore(data_dir)
    store.create(exp)

    users = [f"user{i}" for i in range(USERS_IN_EXPERIMENT)]
    variants = [store.assign(exp, u) for u in users]  # same hashing Pulse uses
    # red converts a bit better (12%) than blue (10%)
    converts = [rng.random() < (0.12 if v == "red" else 0.10) for v in variants]

    names = (["$experiment_assignment"] * len(users)
             + ["signup"] * sum(converts))
    user_ids = users + [u for u, c in zip(users, converts) if c]
    props = ([json.dumps({"experiment": exp.name, "variant": v}) for v in variants]
             + ["{}"] * sum(converts))
    filler = TOTAL_EVENTS - len(names)
    names += ["page_view"] * filler
    user_ids += list(rng.choice(users, filler))
    props += ["{}"] * filler

    base_us = int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp() * 1e6)
    day = data_dir / "2026-11-01"
    day.mkdir(parents=True)
    pq.write_table(pa.table({
        "event_id": pa.array([uuid4().hex for _ in range(TOTAL_EVENTS)]),
        "event_name": pa.array(names),
        "timestamp": pa.array(base_us + rng.integers(0, 86400 * 10**6, TOTAL_EVENTS),
                              type=pa.timestamp("us", tz="UTC")),
        "user_id": pa.array(user_ids),
        "session_id": pa.nulls(TOTAL_EVENTS, pa.string()),
        "properties": pa.array(props),
    }, schema=_SCHEMA), day / "events.parquet", row_group_size=100_000)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp) / "events"
        print(f"Creating {TOTAL_EVENTS:,} events with {USERS_IN_EXPERIMENT:,} users in an experiment...")
        make_data(data_dir)

        with TestClient(create_app(data_dir)) as client:
            client.get("/experiments/signup_button/results")  # warm-up
            times = []
            for _ in range(5):
                start = time.perf_counter()
                res = client.get("/experiments/signup_button/results").json()
                times.append(time.perf_counter() - start)

        worst = max(times)
        print("Report times:", " ".join(f"{t:.2f}s" for t in times))
        print("Summary:", res["summary"])
        verdict = "PASS" if worst < TARGET_SECONDS else "FAIL"
        print(f"{verdict}: slowest report {worst:.2f}s (target: under {TARGET_SECONDS:.0f}s)")


if __name__ == "__main__":
    main()
