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

    def test_two_flushes_in_same_second_keep_all_events(self, temp_data_dir, monkeypatch):
        # Bug 1: two saves within the same second used to get the same file
        # name, so the second file overwrote the first and events were lost.
        from datetime import datetime, timezone

        import pulse.storage
        from pulse.storage import QueryEngine

        # Freeze the clock so both saves happen at exactly the same moment
        frozen = datetime(2026, 11, 3, 14, 0, 0, tzinfo=timezone.utc)

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return frozen

        monkeypatch.setattr(pulse.storage, "datetime", FrozenDatetime)

        store = EventStore(data_dir=temp_data_dir)
        store.start()

        store.add(Event(event_name="first", user_id="alice"))
        store.flush()
        store.add(Event(event_name="second", user_id="bob"))
        store.flush()
        store.stop()

        # Both saves must produce their own file...
        parquet_files = list(temp_data_dir.glob("*/*.parquet"))
        assert len(parquet_files) == 2

        # ...and both events must still be readable
        names = {row["event_name"] for row in QueryEngine(temp_data_dir).event_counts()}
        assert names == {"first", "second"}


def _save_events(data_dir, events):
    """Helper: write (event_name, user_id, minute) tuples to disk, in a known time order."""
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
    store = EventStore(data_dir=data_dir)
    store.start()
    store.add_many([
        Event(event_name=name, user_id=user, timestamp=start + timedelta(minutes=minute))
        for name, user, minute in events
    ])
    store.stop()


class TestFunnel:
    def test_steps_must_happen_in_order(self, temp_data_dir):
        # Bug 4: a user who did the steps in the wrong order used to be counted
        from pulse.storage import QueryEngine

        _save_events(temp_data_dir, [
            ("view_pricing", "alice", 1), ("signup", "alice", 2),  # right order
            ("signup", "bob", 1), ("view_pricing", "bob", 2),      # wrong order
        ])

        result = QueryEngine(temp_data_dir).funnel(["view_pricing", "signup"])

        assert [r["users"] for r in result] == [2, 1]  # only alice finishes
        assert result[1]["conversion_from_previous"] == 0.5

    def test_earlier_wrong_order_does_not_block_later_right_order(self, temp_data_dir):
        # carol signs up first, but later views pricing and signs up again -> counts
        from pulse.storage import QueryEngine

        _save_events(temp_data_dir, [
            ("signup", "carol", 1), ("view_pricing", "carol", 2), ("signup", "carol", 3),
        ])

        result = QueryEngine(temp_data_dir).funnel(["view_pricing", "signup"])
        assert [r["users"] for r in result] == [1, 1]

    def test_three_steps_and_drop_off(self, temp_data_dir):
        from pulse.storage import QueryEngine

        _save_events(temp_data_dir, [
            ("page_view", "a", 1), ("add_to_cart", "a", 2), ("purchase", "a", 3),
            ("page_view", "b", 1), ("add_to_cart", "b", 2),
            ("page_view", "c", 1), ("purchase", "c", 2),  # skipped add_to_cart
        ])

        result = QueryEngine(temp_data_dir).funnel(["page_view", "add_to_cart", "purchase"])
        assert [r["users"] for r in result] == [3, 2, 1]

    def test_same_step_twice_needs_two_separate_events(self, temp_data_dir):
        # Funnel "page_view -> page_view" means two different page views
        from pulse.storage import QueryEngine

        _save_events(temp_data_dir, [
            ("page_view", "a", 1), ("page_view", "a", 2),
            ("page_view", "b", 1),
        ])

        result = QueryEngine(temp_data_dir).funnel(["page_view", "page_view"])
        assert [r["users"] for r in result] == [2, 1]


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
