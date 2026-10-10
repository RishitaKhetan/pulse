"""Tests for event storage and querying."""
import pytest

from pulse.models import Event
from pulse.storage import EventStore


class TestEventStore:
    def test_add_event(self, temp_data_dir):
        store = EventStore(data_dir=temp_data_dir)
        store.start()

        event = Event(event_name="test", user_id="alice")
        store.add(event)

        buffered = store.buffered()
        assert len(buffered) == 1
        assert buffered[0].event_name == "test"

        store.stop()

    def test_add_many_events(self, temp_data_dir):
        store = EventStore(data_dir=temp_data_dir)
        store.start()

        events = [
            Event(event_name="click", user_id="alice"),
            Event(event_name="view", user_id="bob"),
        ]
        store.add_many(events)

        buffered = store.buffered()
        assert len(buffered) == 2

        store.stop()

    def test_flush_writes_parquet(self, temp_data_dir):
        store = EventStore(data_dir=temp_data_dir)
        store.start()

        event = Event(event_name="test", user_id="alice")
        store.add(event)

        count = store.flush()
        assert count == 1

        # Check that Parquet file was written
        parquet_files = list(temp_data_dir.glob("*/*.parquet"))
        assert len(parquet_files) > 0

        store.stop()
