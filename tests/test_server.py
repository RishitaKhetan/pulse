"""Tests for the HTTP endpoints of the Pulse server."""
from fastapi.testclient import TestClient

from pulse.server import create_app


def make_client(data_dir):
    # TestClient sends pretend requests to the app without starting a real server.
    # Using it as a context manager runs the app's start-up and shut-down steps.
    return TestClient(create_app(data_dir))


class TestBatchIngest:
    def test_all_good_events_are_saved(self, temp_data_dir):
        with make_client(temp_data_dir) as client:
            res = client.post("/events/batch", json=[
                {"event_name": "page_view", "user_id": "alice"},
                {"event_name": "signup", "user_id": "bob"},
            ])

        assert res.status_code == 201
        assert res.json() == {"received": 2, "rejected": []}

    def test_one_bad_event_does_not_reject_the_rest(self, temp_data_dir):
        # Bug 2: one broken event used to make the server throw away the whole batch
        with make_client(temp_data_dir) as client:
            res = client.post("/events/batch", json=[
                {"event_name": "page_view", "user_id": "alice"},
                {"event_name": "signup", "user_id": "bob"},
                {"user_id": "carol"},  # broken: no event_name
            ])
            saved = client.get("/analytics/events").json()

        assert res.status_code == 201
        body = res.json()
        assert body["received"] == 2
        # The bad event is reported back with its position and the reason
        assert len(body["rejected"]) == 1
        assert body["rejected"][0]["index"] == 2
        assert "event_name" in body["rejected"][0]["error"]

        # The two good events really were saved
        names = {row["event_name"] for row in saved}
        assert names == {"page_view", "signup"}

    def test_non_object_items_are_rejected_not_crashing(self, temp_data_dir):
        with make_client(temp_data_dir) as client:
            res = client.post("/events/batch", json=[
                {"event_name": "page_view"},
                "not an event",
                42,
            ])

        assert res.status_code == 201
        body = res.json()
        assert body["received"] == 1
        assert [r["index"] for r in body["rejected"]] == [1, 2]

    def test_body_that_is_not_a_list_is_refused(self, temp_data_dir):
        with make_client(temp_data_dir) as client:
            res = client.post("/events/batch", json={"event_name": "page_view"})

        assert res.status_code == 422


class TestStaticFiles:
    def test_dashboard_text_is_not_garbled(self, temp_data_dir):
        # Bug 6: on Windows the dashboard was read with the wrong "alphabet",
        # so a dash like — showed up as â€”
        from pulse.server import STATIC_DIR

        with make_client(temp_data_dir) as client:
            res = client.get("/")

        assert res.status_code == 200
        expected = (STATIC_DIR / "index.html").read_bytes().decode("utf-8")
        assert res.text == expected
        assert "â€" not in res.text

    def test_js_sdk_is_served(self, temp_data_dir):
        from pulse.server import STATIC_DIR

        with make_client(temp_data_dir) as client:
            res = client.get("/pulse.js")

        assert res.status_code == 200
        assert "javascript" in res.headers["content-type"]
        assert res.text == (STATIC_DIR / "pulse.js").read_bytes().decode("utf-8")
