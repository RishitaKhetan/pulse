"""Benchmark: how much does the Python SDK slow down an app?

Target from CLAUDE.md: under 2% overhead.

A tiny fake app handles "requests" that each do about 2 ms of work (build a
page, encode some data). We time it WITHOUT Pulse and WITH one pulse.track()
per request, sending to a real Pulse server. Rounds alternate so background
noise affects both sides equally.

Run it with:   python benchmarks/sdk_overhead.py
It starts its own Pulse server on port 4810 with a temporary data folder.
"""
import hashlib
import json
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request

import pulse

PORT = 4810
REQUESTS_PER_ROUND = 200
ROUNDS = 20
TARGET_PERCENT = 2.0


def handle_request(i: int) -> str:
    """Pretend web request: about 2 ms of ordinary work."""
    items = [{"id": n, "name": f"product {n}", "price": n * 1.5} for n in range(3500)]
    page = json.dumps({"request": i, "items": items})
    return hashlib.sha256(page.encode()).hexdigest()


def run_app(with_pulse: bool) -> float:
    start = time.perf_counter()
    for i in range(REQUESTS_PER_ROUND):
        handle_request(i)
        if with_pulse:
            pulse.track("page_view", user_id=f"user{i % 50}", properties={"page": "/shop"})
    return time.perf_counter() - start


def wait_for_server(url: str) -> None:
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/health", timeout=1)
            return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("Pulse server did not start")


def main() -> None:
    url = f"http://127.0.0.1:{PORT}"
    with tempfile.TemporaryDirectory() as tmp:
        server = subprocess.Popen(
            [sys.executable, "-m", "pulse.cli", "start", "--port", str(PORT),
             "--no-browser", "--data-dir", f"{tmp}/events"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            wait_for_server(url)
            pulse.init(endpoint=url)
            run_app(False), run_app(True)  # warm-up

            # Swap the order every round (A-B, B-A, ...). Laptops slow down as
            # they warm up; always running "with Pulse" second would blame
            # Pulse for that slowdown.
            without, with_, ratios = [], [], []
            for r in range(ROUNDS):
                if r % 2 == 0:
                    a = run_app(False); b = run_app(True)
                else:
                    b = run_app(True); a = run_app(False)
                without.append(a); with_.append(b); ratios.append(b / a)
            pulse.flush()

            base, tracked = statistics.median(without), statistics.median(with_)
            overhead = (statistics.median(ratios) - 1) * 100
            per_call_us = overhead / 100 * base / REQUESTS_PER_ROUND * 1e6
            print(f"Without Pulse: {base * 1000 / REQUESTS_PER_ROUND:.2f} ms per request")
            print(f"With Pulse:    {tracked * 1000 / REQUESTS_PER_ROUND:.2f} ms per request")
            print(f"Cost of one pulse.track(): about {per_call_us:.0f} microseconds")
            verdict = "PASS" if overhead < TARGET_PERCENT else "FAIL"
            print(f"{verdict}: overhead {overhead:.2f}% (target: under {TARGET_PERCENT:.0f}%)")
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
