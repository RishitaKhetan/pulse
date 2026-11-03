"""Tests for merging small Parquet files into one ("compaction")."""
import threading
from datetime import datetime, timezone
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from pulse.compaction import COMPACT_AT_FILES, compact_if_needed, recover
from pulse.storage import _SCHEMA, QueryEngine


def _write_small_files(day_dir, count, start=0):
    """Write `count` files with one event each, like many quick saves would."""
    day_dir.mkdir(parents=True, exist_ok=True)
    for i in range(start, start + count):
        table = pa.table({
            "event_id": [f"e{i}"],
            "event_name": ["page_view"],
            "timestamp": pa.array([datetime(2026, 11, 1, tzinfo=timezone.utc)],
                                  type=pa.timestamp("us", tz="UTC")),
            "user_id": [f"user{i}"],
            "session_id": [None],
            "properties": ["{}"],
        }, schema=_SCHEMA)
        pq.write_table(table, day_dir / f"00_{i}_{uuid4().hex}.parquet")


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _total(data_dir):
    return sum(row["count"] for row in QueryEngine(data_dir).event_counts())


class TestCompaction:
    def test_many_small_files_become_one(self, temp_data_dir):
        day = temp_data_dir / _today()
        _write_small_files(day, COMPACT_AT_FILES + 10)

        compact_if_needed(temp_data_dir)

        files = list(day.glob("*.parquet"))
        assert len(files) == 1
        assert files[0].name.startswith("compacted_")
        assert _total(temp_data_dir) == COMPACT_AT_FILES + 10  # nothing lost

    def test_today_with_few_files_is_left_alone(self, temp_data_dir):
        day = temp_data_dir / _today()
        _write_small_files(day, 3)

        compact_if_needed(temp_data_dir)

        assert len(list(day.glob("*.parquet"))) == 3

    def test_finished_day_is_merged_even_with_few_files(self, temp_data_dir):
        old_day = temp_data_dir / "2026-10-01"
        _write_small_files(old_day, 3)

        compact_if_needed(temp_data_dir)

        assert len(list(old_day.glob("*.parquet"))) == 1
        assert _total(temp_data_dir) == 3

    def test_merging_twice_keeps_everything(self, temp_data_dir):
        old_day = temp_data_dir / "2026-10-01"
        _write_small_files(old_day, 3)
        compact_if_needed(temp_data_dir)
        _write_small_files(old_day, 2, start=100)  # more files arrive later
        compact_if_needed(temp_data_dir)

        assert len(list(old_day.glob("*.parquet"))) == 1
        assert _total(temp_data_dir) == 5


class TestCrashRecovery:
    def test_half_written_merge_is_thrown_away(self, temp_data_dir):
        # Crash while writing the merged file: only a .tmp file exists,
        # the original small files are all still there.
        day = temp_data_dir / "2026-10-01"
        _write_small_files(day, 3)
        (day / "compacted_abc.parquet.tmp").write_bytes(b"half written")

        recover(temp_data_dir)

        assert not list(day.glob("*.tmp"))
        assert _total(temp_data_dir) == 3

    def test_crash_after_merge_does_not_double_count(self, temp_data_dir):
        # Crash after the merged file was made visible but before the small
        # files were deleted: the same events now exist twice on disk.
        day = temp_data_dir / "2026-10-01"
        _write_small_files(day, 3)
        sources = sorted(p.name for p in day.glob("*.parquet"))
        merged = pa.concat_tables([pq.read_table(day / name) for name in sources])
        merged = merged.replace_schema_metadata({"pulse_sources": "\n".join(sources)})
        pq.write_table(merged, day / "compacted_crash.parquet")
        assert _total(temp_data_dir) == 6  # double counted before recovery

        recover(temp_data_dir)

        assert [p.name for p in day.glob("*.parquet")] == ["compacted_crash.parquet"]
        assert _total(temp_data_dir) == 3


class TestCompactionWhileQuerying:
    def test_charts_stay_correct_during_compaction(self, temp_data_dir):
        day = temp_data_dir / "2026-10-01"
        _write_small_files(day, COMPACT_AT_FILES + 10)
        files_lock = threading.Lock()
        query = QueryEngine(temp_data_dir, files_lock=files_lock)

        totals, errors = [], []

        def keep_querying():
            for _ in range(30):
                try:
                    totals.append(sum(r["count"] for r in query.event_counts()))
                except Exception as e:  # a crash here would mean a race
                    errors.append(e)

        reader = threading.Thread(target=keep_querying)
        reader.start()
        compact_if_needed(temp_data_dir, files_lock=files_lock)
        reader.join()

        assert errors == []
        assert set(totals) == {COMPACT_AT_FILES + 10}  # never more, never less
        assert len(list(day.glob("*.parquet"))) == 1


class TestEventStoreUsesCompaction:
    def test_timer_tick_merges_small_files(self, temp_data_dir):
        from pulse.storage import EventStore

        day = temp_data_dir / _today()
        _write_small_files(day, COMPACT_AT_FILES)
        store = EventStore(data_dir=temp_data_dir)
        store.start()
        try:
            store._flush_and_reschedule()  # what the 30-second timer runs
        finally:
            store.stop()

        assert len(list(day.glob("*.parquet"))) == 1
        assert _total(temp_data_dir) == COMPACT_AT_FILES

    def test_start_cleans_up_after_a_crash(self, temp_data_dir):
        from pulse.storage import EventStore

        day = temp_data_dir / "2026-10-01"
        _write_small_files(day, 2)
        (day / "compacted_x.parquet.tmp").write_bytes(b"half written")

        store = EventStore(data_dir=temp_data_dir)
        store.start()
        store.stop()

        assert not list(day.glob("*.tmp"))
