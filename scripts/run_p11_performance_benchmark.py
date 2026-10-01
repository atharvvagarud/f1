"""P11-3 final performance benchmark (measurement only).

Measures the frozen release candidate exactly as it exists. Changes no
application, scientific, Docker, or frontend behavior; trains nothing;
generates nothing; requires no network.

Usage:
    python scripts/run_p11_performance_benchmark.py \
        --base-url http://localhost:8000 --env-label native \
        --out results/v2_final_validation/p11_3_performance_benchmark.json
    # add --frontend-url http://localhost:3000 for optional frontend timing
    # add --skip-expensive to run only the cheap (sub-second) operations

Method: time.perf_counter_ns around complete local HTTP requests,
concurrency 1, documented warm-ups excluded from statistics, NumPy
linear percentiles, one consistent method for every operation.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import numpy as np
except ImportError:  # fail closed: percentiles must be linear-method
    np = None

# Frozen P11-2 anchors (perez lap-20: lap-30 does not exist in served data).
A19 = {"race_id": "2019-r01-R", "anchor_driver_id": "bottas",
       "anchor_lap_number": 1, "anchor_state_time_s": 2106.767}
A22 = {"race_id": "2022-r01-R", "anchor_driver_id": "perez",
       "anchor_lap_number": 20, "anchor_state_time_s": 5761.839}
MC_SEED = 7
STRAT_SEED = 7
STRAT_OBJECTIVE = "MAXIMIZE_WIN_PROBABILITY"
STRAT_SIMS = 100
PARAM_IDENTITY = "phase6-r3-empirical"


def percentile_linear(samples, q):
    """Linear-interpolation percentile (NumPy 'linear' method)."""
    if np is not None:
        return float(np.percentile(samples, q, method="linear"))
    ordered = sorted(samples)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (q / 100.0) * (len(ordered) - 1)
    low = int(rank)
    frac = rank - low
    if low + 1 >= len(ordered):
        return float(ordered[-1])
    return float(ordered[low] + frac * (ordered[low + 1] - ordered[low]))


def compute_stats(samples_ms):
    """Summary statistics over recorded samples (warm-ups already excluded)."""
    if not samples_ms:
        raise ValueError("no samples recorded")
    return {
        "min": round(min(samples_ms), 3),
        "p50": round(percentile_linear(samples_ms, 50), 3),
        "mean": round(sum(samples_ms) / len(samples_ms), 3),
        "p95": round(percentile_linear(samples_ms, 95), 3),
        "p99": round(percentile_linear(samples_ms, 99), 3),
        "max": round(max(samples_ms), 3),
        "stddev": round(float(np.std(samples_ms)) if np is not None
                        else _stddev(samples_ms), 3),
    }


def _stddev(xs):
    mean = sum(xs) / len(xs)
    return (sum((x - mean) ** 2 for x in xs) / len(xs)) ** 0.5


class SemanticFailure(Exception):
    """A benchmark response violated its frozen semantic contract."""


def http_json(base, method, path, payload=None, timeout=600):
    url = base + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter_ns()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()[:500]
        status = exc.code
    dt_ms = (time.perf_counter_ns() - t0) / 1e6
    return status, body, dt_ms


def check(cond, msg):
    if not cond:
        raise SemanticFailure(msg)


def http_raw(base, method, path, timeout=600):
    """Client-observed duration for non-JSON (HTML) responses."""
    url = base + path
    req = urllib.request.Request(url, method=method)
    t0 = time.perf_counter_ns()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    return status, (time.perf_counter_ns() - t0) / 1e6


def run_op_raw(base, method, path, warmups, samples, timeout=600):
    for _ in range(warmups):
        status, _ = http_raw(base, method, path, timeout=timeout)
        check(status == 200, f"expected 200, got {status}")
    durations, failures = [], 0
    for _ in range(samples):
        status, dt = http_raw(base, method, path, timeout=timeout)
        if status != 200:
            failures += 1
            raise SemanticFailure(f"{method} {path}: status {status}")
        durations.append(round(dt, 3))
    return durations, failures


def run_op(base, method, path, payload, warmups, samples, validator,
           timeout=600):
    """Warm up (discarded), then record client-observed durations in ms."""
    for _ in range(warmups):
        status, body, _ = http_json(base, method, path, payload,
                                    timeout=timeout)
        validator(status, body, warmup=True)
    durations, failures, server_ms = [], 0, []
    last_body = None
    for _ in range(samples):
        status, body, dt = http_json(base, method, path, payload,
                                     timeout=timeout)
        try:
            validator(status, body, warmup=False)
        except SemanticFailure as exc:
            failures += 1
            raise SemanticFailure(f"{method} {path}: {exc}") from exc
        durations.append(round(dt, 3))
        last_body = body
    return durations, failures, last_body


def v200(status, body, warmup=False):
    check(status == 200, f"expected 200, got {status}: {body!r}"[:200])


def v_predict(status, body, warmup=False):
    v200(status, body)
    check(body.get("probability_semantics") == "INDEPENDENT_BINARY",
          "prediction semantics drift")
    finite = 0
    for row in body.get("predictions", []):
        # Unobservable drivers carry null probability with a null reason
        # (null semantics); only finite served probabilities are checked.
        p = row.get("probability", row.get("winner_probability"))
        if p is None:
            check(row.get("unavailable_reason") is not None,
                  "null probability without null reason")
            continue
        check(isinstance(p, (int, float)) and 0.0 <= p <= 1.0,
              f"probability out of range: {p!r}")
        finite += 1
    check(finite > 0, "no finite probabilities served")


def v_replay_pred(status, body, warmup=False):
    v200(status, body)
    check(body.get("cache_status") == "HIT", "expected CACHE_HIT")
    check(body.get("frame", {}).get("frame_index") == 0, "wrong checkpoint")


def v_mc(trials):
    def _v(status, body, warmup=False):
        v200(status, body)
        check(body.get("valid_simulations") == trials,
              f"valid {body.get('valid_simulations')} != requested {trials}")
        check(body.get("parameter_set_id") == PARAM_IDENTITY,
              "simulation parameter identity drift")
    return _v


def v_strat(status, body, warmup=False):
    v200(status, body)
    check(body.get("objective") == STRAT_OBJECTIVE, "objective drift")
    check(len(body.get("candidates", [])) == 4, "candidate count drift")
    check(body.get("target_driver_id") == "perez", "target drift")


def build_operations():
    """(operation_id, description, classification, anchor, method, path,
    payload, warmups, samples, validator, unit, extra)."""
    return [
        ("B1-health", "GET /health baseline service overhead",
         "STATIC_SERVICE", None, "GET", "/health", None, 5, 200, v200,
         "ms", {}),
        ("B2-readiness", "GET /ready deployability readiness",
         "WARM_READINESS", None, "GET", "/ready", None, 5, 100, v200,
         "ms", {"note": "server may use its internal readiness cache"}),
        ("B3a-racestate", "RaceState retrieval at frozen anchor",
         "COMPUTE", dict(A19), "GET",
         "/v2/races/2019-r01-R/state?anchor_driver_id=bottas"
         "&anchor_lap_number=1&anchor_state_time_s=2106.767",
         None, 5, 200, v200, "ms", {}),
        ("B3b-predict", "winner-snapshot INDEPENDENT_BINARY prediction",
         "COMPUTE", dict(A19), "POST", "/v2/predictions/winner-snapshot",
         dict(A19), 5, 200, v_predict, "ms",
         {"semantics": "INDEPENDENT_BINARY"}),
        ("B4a-replay-timeline", "replay timeline retrieval",
         "CACHE_HIT", {"race_id": "2019-r01-R"}, "GET",
         "/v2/races/2019-r01-R/replay/timeline", None, 5, 200, v200,
         "ms", {}),
        ("B4b-replay-pred", "exact cached replay prediction frame 0",
         "CACHE_HIT", {"race_id": "2019-r01-R", "frame_index": 0},
         "GET", "/v2/races/2019-r01-R/replay/predictions/0", None,
         5, 200, v_replay_pred, "ms", {}),
        ("B5a-explain", "local LOG_ODDS explanation",
         "COMPUTE_CACHE_BACKED", {"race_id": "2019-r01-R",
                                  "frame_index": 0, "driver_id": "bottas"},
         "GET", "/v2/replay/2019-r01-R/frames/0/predictions/bottas"
                "/explanation", None, 5, 100, v200, "ms", {}),
        ("B5b-change", "timeline-change explanation frame 20 from 0",
         "COMPUTE_CACHE_BACKED", {"race_id": "2019-r01-R",
                                  "frame_index": 20, "driver_id": "bottas"},
         "GET", "/v2/replay/2019-r01-R/frames/20/predictions/bottas"
                "/change", None, 5, 100, v200, "ms", {}),
        ("B6a-mc-1k", "Monte Carlo simulation, 1000 trials",
         "COMPUTE", dict(A22), "POST", "/v2/simulations/race",
         dict(A22, simulation_count=1000, master_seed=MC_SEED),
         2, 30, v_mc(1000), "ms",
         {"trial_count": 1000, "seed": MC_SEED,
          "parameter_set_id": PARAM_IDENTITY}),
        ("B6b-mc-10k", "Monte Carlo simulation, 10000 trials",
         "COMPUTE", dict(A22), "POST", "/v2/simulations/race",
         dict(A22, simulation_count=10000, master_seed=MC_SEED),
         1, 10, v_mc(10000), "ms",
         {"trial_count": 10000, "seed": MC_SEED,
          "parameter_set_id": PARAM_IDENTITY,
          "p99_note": "empirical percentile over 10 samples; "
                      "not a production SLO"}),
        ("B7-strategy", "strategy comparison latency (not optimizer)",
         "COMPUTE", dict(A22), "POST", "/v2/strategies/compare",
         dict(A22, target_driver_id="perez", objective=STRAT_OBJECTIVE,
              simulation_count=STRAT_SIMS, master_seed=STRAT_SEED),
         1, 20, v_strat, "ms",
         {"candidate_count": 4, "simulation_count": STRAT_SIMS,
          "seed": STRAT_SEED, "objective": STRAT_OBJECTIVE}),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--env-label", required=True, choices=["native",
                                                           "container"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--frontend-url", default=None)
    ap.add_argument("--skip-expensive", action="store_true")
    ap.add_argument("--frontend-only", action="store_true")
    args = ap.parse_args()

    operations = []
    if not args.frontend_only:
        for spec in build_operations():
            (op_id, desc, cls, anchor, method, path, payload, warm,
             n, validator, unit, extra) = spec
            if args.skip_expensive and op_id in ("B6a-mc-1k", "B6b-mc-10k",
                                                "B7-strategy"):
                continue
            durations, failures, _ = run_op(
                args.base_url.rstrip("/"), method, path, payload, warm, n,
                validator)
            entry = {"operation_id": op_id, "description": desc,
                     "environment": args.env_label,
                     "measurement_boundary":
                         "client-observed complete local HTTP request "
                         "duration (perf_counter_ns), concurrency 1",
                     "classification": cls,
                     "anchor": anchor, "warmups": warm, "samples": n,
                     "concurrency": 1, "unit": unit,
                     "failures": failures,
                     "semantic_checks": "pass",
                     "samples_ms": durations}
            entry.update(compute_stats(durations))
            entry.update(extra)
            operations.append(entry)
            print(f"{op_id} [{args.env_label}]: n={n} "
                  f"p50={entry['p50']} p95={entry['p95']} "
                  f"p99={entry['p99']} max={entry['max']} ms", flush=True)

    if args.frontend_url:
        for route in ["/", "/replay", "/simulator", "/strategy",
                      "/models", "/about"]:
            durations, failures = run_op_raw(
                args.frontend_url.rstrip("/"), "GET", route, 5, 100)
            entry = {"operation_id": f"F-frontend{route}",
                     "description": "LOCAL FRONTEND SERVER RESPONSE TIME "
                                    f"for {route} (not page load, render, "
                                    "hydration, or browser performance)",
                     "environment": args.env_label,
                     "measurement_boundary":
                         "client-observed complete local HTTP response "
                         "duration (perf_counter_ns), concurrency 1",
                     "classification": "STATIC_SERVER",
                     "anchor": {"route": route}, "warmups": 5, "samples": 100,
                     "concurrency": 1, "unit": "ms", "failures": failures,
                     "semantic_checks": "pass", "samples_ms": durations}
            entry.update(compute_stats(durations))
            operations.append(entry)
            print(f"F-frontend{route}: p50={entry['p50']} "
                  f"p95={entry['p95']} ms", flush=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"operations": operations}, indent=1)
                        + "\n")
    print(f"wrote {len(operations)} operations to {out_path.name}")


if __name__ == "__main__":
    sys.exit(main())
