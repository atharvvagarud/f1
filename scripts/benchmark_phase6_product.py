"""R8 Phase-6 product benchmark (Phase 6, R8-S/AG).

Measures the *product* path, not the engine alone:

    service initialization (corpus + frozen parameters + service build)
    HTTP request -> exact state reconstruction -> adaptation -> eligibility
    -> Monte Carlo simulation -> response serialization

Fixtures reuse the R7 engine benchmark states (2023-r01-R early/mid/late) so
the engine-only R7 numbers stay comparable. Counts default to the product
policy: 1 000 (default) at early/mid/late and 10 000 (high-quality ceiling) at
mid. It never regenerates scientific data and never touches 2025.

Usage:
    python scripts/benchmark_phase6_product.py
    python scripts/benchmark_phase6_product.py --json out.json

Output is reproducible except for timing / memory.
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402
from api.v2_service import load_v2_service  # noqa: E402
from api.v2_simulation_service import (  # noqa: E402
    DEFAULT_SIMULATION_COUNT,
    MAX_SYNCHRONOUS_SIMULATIONS,
    build_v2_simulation_service,
    get_v2_simulation_service,
    load_production_parameters,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Supported real fixtures (the R7/R7.1 accepted contemporaneous states). The
# pre-R7.1 engine-only benchmark used 2023-r01-R mid/late anchors that the
# R7.1 runtime now correctly refuses (non-contemporaneous roster), so the
# product benchmark uses supported states only.
FIXTURES = (
    ("early", dict(race_id="2023-r01-R", anchor_driver_id="alonso",
                   anchor_lap_number=2, anchor_state_time_s=None)),
    ("mid", dict(race_id="2022-r01-R", anchor_driver_id="perez",
                 anchor_lap_number=30, anchor_state_time_s=None)),
    ("late", dict(race_id="2022-r01-R", anchor_driver_id="russell",
                  anchor_lap_number=38, anchor_state_time_s=None)),
)

CASES = (
    ("early", DEFAULT_SIMULATION_COUNT),
    ("mid", DEFAULT_SIMULATION_COUNT),
    ("late", DEFAULT_SIMULATION_COUNT),
    ("mid", MAX_SYNCHRONOUS_SIMULATIONS),
)

SEED = 20240101


def peak_rss_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return value / (1024.0 * 1024.0)
    return value / 1024.0


def resolve_anchor(states, anchor: dict) -> dict:
    frame = states[(states["race_id"] == anchor["race_id"])
                   & (states["driver_id"] == anchor["anchor_driver_id"])
                   & (states["lap_number"] == anchor["anchor_lap_number"])]
    if frame.empty:
        raise SystemExit(f"anchor not found: {anchor!r}")
    row = frame.iloc[0]
    return {
        "race_id": anchor["race_id"],
        "anchor_driver_id": anchor["anchor_driver_id"],
        "anchor_lap_number": int(row.lap_number),
        "anchor_state_time_s": float(row.state_time_s),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=None,
                        help="optional path to write measured metrics as JSON")
    parser.add_argument("--counts", type=int, nargs="*", default=None,
                        help="override case counts (fixture order)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    corpus_started = time.perf_counter()
    v2_service = load_v2_service()
    corpus_s = time.perf_counter() - corpus_started

    params_started = time.perf_counter()
    parameters = load_production_parameters()
    parameters_s = time.perf_counter() - params_started

    build_started = time.perf_counter()
    simulation_service = build_v2_simulation_service(
        v2_service, parameters=parameters)
    service_build_s = time.perf_counter() - build_started

    app.dependency_overrides[get_v2_simulation_service] = (
        lambda: simulation_service)
    client = TestClient(app)

    cases = CASES
    if args.counts:
        names = [name for name, _ in CASES]
        cases = tuple(zip(names, args.counts))

    report = {
        "product_path": "POST /v2/simulations/race",
        "parameter_version": parameters.parameter_version,
        "parameter_set_id": parameters.parameter_set_id,
        "parameter_hash": parameters.scientific_hash(),
        "mechanics_enabled": ["pit_dynamics"],
        "seed": SEED,
        "default_count": DEFAULT_SIMULATION_COUNT,
        "max_synchronous_count": MAX_SYNCHRONOUS_SIMULATIONS,
        "service_initialization": {
            "corpus_load_s": corpus_s,
            "parameter_load_s": parameters_s,
            "service_build_s": service_build_s,
            "total_s": corpus_s + parameters_s + service_build_s,
        },
        "cases": [],
    }

    print(f"parameter_version={parameters.parameter_version}")
    print(f"service init: corpus={corpus_s:.3f}s params={parameters_s:.3f}s "
          f"build={service_build_s:.3f}s")

    anchors = {name: resolve_anchor(v2_service._states,  # noqa: SLF001
                                    anchor)
               for name, anchor in FIXTURES}

    for name, count in cases:
        anchor = anchors[name]
        body = {**anchor, "simulation_count": count, "master_seed": SEED}
        started = time.perf_counter()
        response = client.post("/v2/simulations/race", json=body)
        http_total_s = time.perf_counter() - started
        record = {
            "fixture": name,
            "anchor": anchor,
            "simulation_count": count,
            "http_status": response.status_code,
        }
        if response.status_code != 200:
            record["error"] = response.json()
            report["cases"].append(record)
            print(f"  {name:<6} N={count:>6} HTTP {response.status_code} "
                  f"{record['error']}")
            continue
        payload = response.json()
        server = payload["runtime"]
        record.update({
            "engine_runtime_s": payload["engine_runtime_s"],
            "reconstruction_s": server["reconstruction_s"],
            "adaptation_s": server["adaptation_s"],
            "simulation_s": server["simulation_s"],
            "server_total_s": server["total_s"],
            "serialization_s": max(0.0, http_total_s - server["total_s"]),
            "http_total_s": http_total_s,
            "valid_simulations": payload["valid_simulations"],
            "invalid_simulations": payload["invalid_simulations"],
            "peak_rss_mb": peak_rss_mb(),
            "scientific_result_identity": payload["scientific_result_identity"],
        })
        report["cases"].append(record)
        print(f"  {name:<6} N={count:>6} HTTP {http_total_s:.3f}s "
              f"engine={payload['engine_runtime_s']:.3f}s "
              f"recon={server['reconstruction_s']:.3f}s "
              f"sim={server['simulation_s']:.3f}s "
              f"serial={record['serialization_s']:.3f}s "
              f"valid={payload['valid_simulations']} "
              f"invalid={payload['invalid_simulations']} "
              f"rss={record['peak_rss_mb']:.1f}MB")

    app.dependency_overrides.pop(get_v2_simulation_service, None)

    if args.json:
        Path(args.json).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
