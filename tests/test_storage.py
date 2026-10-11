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


class TestFunnelDetection:
    def test_detect_funnel_patterns(self, temp_data_dir):
        from pulse.storage import QueryEngine

        store = EventStore(data_dir=temp_data_dir)
        store.start()

        # Create events that form a funnel pattern
        events = [
            Event(event_name="page_view", user_id="alice"),
            Event(event_name="button_click", user_id="alice"),
            Event(event_name="signup", user_id="alice"),
            Event(event_name="page_view", user_id="bob"),
            Event(event_name="button_click", user_id="bob"),
            Event(event_name="signup", user_id="bob"),
            Event(event_name="page_view", user_id="charlie"),
            Event(event_name="signup", user_id="charlie"),
        ]
        store.add_many(events)
        store.flush()
        store.stop()

        # Query for funnel patterns
        query = QueryEngine(data_dir=temp_data_dir)
        patterns = query.detect_funnel_patterns(max_depth=3, min_users=1)

        assert len(patterns) > 0
        # Should find page_view -> button_click -> signup (2 users)
        funnel_steps = [p["steps"] for p in patterns]
        assert ["page_view", "button_click", "signup"] in funnel_steps

    def test_detect_funnel_patterns_filters_by_min_users(self, temp_data_dir):
        from pulse.storage import QueryEngine

        store = EventStore(data_dir=temp_data_dir)
        store.start()

        # Create a pattern with only 1 user
        events = [
            Event(event_name="page_view", user_id="alice"),
            Event(event_name="signup", user_id="alice"),
        ]
        store.add_many(events)
        store.flush()
        store.stop()

        query = QueryEngine(data_dir=temp_data_dir)
        # Should return nothing because min_users=2
        patterns = query.detect_funnel_patterns(max_depth=3, min_users=2)
        assert len(patterns) == 0
