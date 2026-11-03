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


class TestWhoCanTalkToPulse:
    # Other websites (like the developer's own app) must be able to SEND events,
    # but must NOT be able to READ the analytics data back.
    EVIL = {"Origin": "http://some-other-website.com"}

    def test_other_sites_can_send_events(self, temp_data_dir):
        with make_client(temp_data_dir) as client:
            # The browser first asks "may I send JSON here?" (a "preflight" check)
            pre = client.options("/events/batch", headers={
                **self.EVIL,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            })
            res = client.post("/events/batch", headers=self.EVIL,
                              json=[{"event_name": "page_view"}])

        assert pre.status_code in (200, 204)
        assert pre.headers.get("access-control-allow-origin") == "*"
        assert res.headers.get("access-control-allow-origin") == "*"

    def test_other_sites_can_get_their_experiment_variant(self, temp_data_dir):
        with make_client(temp_data_dir) as client:
            client.post("/experiments", json={"name": "btn", "goal_event": "signup"})
            res = client.get("/experiments/btn/assign?user_id=alice", headers=self.EVIL)

        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "*"

    def test_other_sites_cannot_read_data(self, temp_data_dir):
        with make_client(temp_data_dir) as client:
            for path in ["/events", "/analytics/events", "/analytics/top-users",
                         "/experiments", "/analytics/retention"]:
                res = client.get(path, headers=self.EVIL)
                # Without this header, the browser hides the answer from the other site
                assert "access-control-allow-origin" not in res.headers, path

    def test_other_sites_cannot_create_experiments_or_flush(self, temp_data_dir):
        with make_client(temp_data_dir) as client:
            for path in ["/experiments", "/flush", "/analytics/funnel"]:
                pre = client.options(path, headers={
                    **self.EVIL,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                })
                assert "access-control-allow-origin" not in pre.headers, path

    def test_dashboard_itself_still_works(self, temp_data_dir):
        # The dashboard is served by Pulse itself, so it is "same site" and
        # needs no special permission.
        with make_client(temp_data_dir) as client:
            assert client.get("/analytics/events").status_code == 200
            assert client.get("/events").status_code == 200


class TestExperimentResults:
    def test_results_include_events_that_just_arrived(self, temp_data_dir):
        # The results page must save the in-memory buffer first (like every other
        # chart does), otherwise brand-new assignments and signups are missing.
        with make_client(temp_data_dir) as client:
            client.post("/experiments", json={
                "name": "signup_button", "variants": ["blue", "red"], "goal_event": "signup",
            })
            variants = {}
            for user in ["alice", "bob", "carol", "dan"]:
                variants[user] = client.get(
                    f"/experiments/signup_button/assign?user_id={user}"
                ).json()["variant"]
            client.post("/events/batch", json=[{"event_name": "signup", "user_id": "alice"}])

            res = client.get("/experiments/signup_button/results").json()

        by_variant = {v["variant"]: v for v in res["variants"]}
        assert sum(v["users"] for v in by_variant.values()) == 4
        assert by_variant[variants["alice"]]["conversions"] == 1


class TestFirstFiveMinutes:
    def test_chart_library_is_served_by_pulse(self, temp_data_dir):
        # E: charts must work without internet, so Pulse serves Chart.js itself
        with make_client(temp_data_dir) as client:
            res = client.get("/chart.umd.min.js")

        assert res.status_code == 200
        assert "javascript" in res.headers["content-type"]
        assert "Chart" in res.text

    def test_dashboard_loads_no_scripts_from_the_internet(self, temp_data_dir):
        import re

        with make_client(temp_data_dir) as client:
            page = client.get("/").text

        external = re.findall(r'<script[^>]+src="(https?://[^"]+)"', page)
        assert external == []
        assert '<script src="/chart.umd.min.js"></script>' in page

    def test_dashboard_has_welcome_screen_and_fast_refresh(self, temp_data_dir):
        with make_client(temp_data_dir) as client:
            page = client.get("/").text

        assert 'id="welcome"' in page            # C: shown when there are no events
        assert "Send a test event" in page
        assert "REFRESH_EVERY_MS = 5000" in page  # D: refresh every 5 seconds
        assert 'id="refresh-button"' in page
