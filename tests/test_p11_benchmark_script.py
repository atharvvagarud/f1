"""Focused unit tests for the P11-3 benchmark script helpers.

Pure computation only: no server, no corpus, no Docker, no network.
Does not touch the scientific suite.
"""

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_p11_performance_benchmark import (  # noqa: E402
    SemanticFailure,
    check,
    compute_stats,
    percentile_linear,
    v_predict,
)


def test_percentile_linear_matches_numpy():
    np = pytest.importorskip("numpy")
    xs = [3.0, 1.0, 9.0, 2.0, 7.0, 5.0, 8.0, 4.0, 6.0, 10.0]
    for q in (0, 1, 25, 50, 95, 99, 100):
        assert percentile_linear(xs, q) == pytest.approx(
            float(np.percentile(xs, q, method="linear")))


def test_percentile_single_sample():
    assert percentile_linear([4.5], 99) == 4.5


def test_compute_stats_shape_and_ordering():
    xs = [float(i) for i in range(1, 201)]
    s = compute_stats(xs)
    assert set(s) == {"min", "p50", "mean", "p95", "p99", "max", "stddev"}
    assert s["min"] <= s["p50"] <= s["p95"] <= s["p99"] <= s["max"]
    assert all(math.isfinite(v) for v in s.values())


def test_compute_stats_empty_fails_closed():
    with pytest.raises(ValueError):
        compute_stats([])


def test_check_raises_semantic_failure():
    with pytest.raises(SemanticFailure):
        check(False, "bad response")
    check(True, "fine")


def test_no_absolute_developer_paths_in_script():
    text = (ROOT / "scripts" / "run_p11_performance_benchmark.py").read_text()
    assert "/Users/" not in text
    assert "SECRET" not in text.upper() or "no secrets" in text.lower()


def test_v_predict_accepts_null_with_null_reason():
    body = {"probability_semantics": "INDEPENDENT_BINARY",
            "predictions": [
                {"driver_id": "bottas", "probability": 0.56,
                 "unavailable_reason": None},
                {"driver_id": "albon", "probability": None,
                 "winner_probability": None,
                 "unavailable_reason": "NO_OBSERVATION_AT_SNAPSHOT"}]}
    v_predict(200, body)
    with pytest.raises(SemanticFailure):
        v_predict(200, {"probability_semantics": "INDEPENDENT_BINARY",
                        "predictions": [{"probability": None,
                                         "unavailable_reason": None}]})


def test_http_raw_and_run_op_raw_against_local_server():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from scripts.run_p11_performance_benchmark import http_raw, run_op_raw

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = b"<!DOCTYPE html><html></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, dt = http_raw(f"http://127.0.0.1:{port}", "GET", "/")
        assert status == 200
        assert dt > 0
        durations, failures = run_op_raw(
            f"http://127.0.0.1:{port}", "GET", "/", 2, 5)
        assert failures == 0
        assert len(durations) == 5
        assert all(d > 0 for d in durations)
    finally:
        server.shutdown()
