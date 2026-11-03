"""Tests for the Python SDK (pulse.sdk)."""
import threading
import time

from pulse.sdk import PulseClient


class FakeServer:
    """Stands in for the network: records batches, can fail on purpose."""

    def __init__(self, fail_times=0):
        self.batches = []
        self.fail_times = fail_times
        self.lock = threading.Lock()

    def send(self, events):
        with self.lock:
            if self.fail_times > 0:
                self.fail_times -= 1
                raise OSError("Pulse is not reachable")
            self.batches.append(list(events))

    def received(self):
        with self.lock:
            return [e for batch in self.batches for e in batch]


def make_client(server, **kwargs):
    client = PulseClient(endpoint="http://127.0.0.1:1", **kwargs)
    client._send = server.send  # don't use the real network in tests
    return client


def wait_until(condition, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.01)
    return False


class TestPythonSDK:
    def test_events_are_delivered_in_batches(self):
        server = FakeServer()
        client = make_client(server, batch_size=20)

        for i in range(50):
            client.track("page_view", user_id=f"u{i}")
        client.flush()

        events = server.received()
        assert len(events) == 50
        assert events[0]["event_name"] == "page_view"
        assert all(len(b) <= 20 for b in server.batches)

    def test_uses_one_background_thread_not_one_per_batch(self):
        # Bug: the old SDK started 2 new threads every batch and never stopped them
        server = FakeServer()
        before = threading.active_count()
        client = make_client(server, batch_size=20)

        for i in range(2000):
            client.track("page_view")
        assert wait_until(lambda: len(server.received()) >= 2000)

        assert threading.active_count() - before <= 1
        client.close()

    def test_full_batch_is_sent_without_waiting_for_the_timer(self):
        server = FakeServer()
        client = make_client(server, batch_size=10, flush_interval=60)

        for _ in range(10):
            client.track("click")

        assert wait_until(lambda: len(server.received()) == 10, timeout=2)
        client.close()

    def test_failed_send_is_retried(self):
        server = FakeServer(fail_times=1)  # first attempt fails
        client = make_client(server)

        client.track("signup", user_id="alice")
        client.flush()          # fails, events are kept
        assert server.received() == []
        client.flush()          # works this time

        assert [e["user_id"] for e in server.received()] == ["alice"]

    def test_never_crashes_the_app_when_pulse_is_down(self):
        server = FakeServer(fail_times=10**9)  # always fails
        client = make_client(server, max_queue=100)

        for i in range(500):
            client.track("page_view")  # must not raise
        client.flush()

        # memory stays bounded: only the newest events are kept
        assert client.pending() <= 100

    def test_events_carry_session_and_properties(self):
        server = FakeServer()
        client = make_client(server)

        client.track("purchase", user_id="bob", properties={"total": 42})
        client.flush()

        event = server.received()[0]
        assert event["properties"] == {"total": 42}
        assert event["session_id"]

    def test_busy_app_still_sends_full_batches(self):
        # Bug: while one batch was being sent, the few events that arrived
        # meanwhile were sent as their own tiny batch, again and again
        # (519 sends for 1,000 events instead of about 10).
        server = FakeServer()
        slow_send = server.send

        def send_slowly(events):
            time.sleep(0.005)  # a send takes a few ms
            slow_send(events)

        client = make_client(server, batch_size=100, flush_interval=60)
        client._send = send_slowly
        for i in range(1000):
            client.track("page_view")
            time.sleep(0.0002)  # app keeps working between events
        assert wait_until(lambda: len(server.received()) == 1000)

        assert len(server.batches) <= 12
        assert all(len(b) == 100 for b in server.batches)
        client.close()
