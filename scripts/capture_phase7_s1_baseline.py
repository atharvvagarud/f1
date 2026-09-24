"""Capture the pre-change Phase-6 compatibility baseline (Phase-7 S1).

Run this BEFORE any Phase-7 runtime edit. It records, for a frozen
deterministic corpus, the complete ``MonteCarloResult`` (minus the
operational ``runtime_s``) plus the scientific identities produced by the
CURRENT Phase-6 runtime with ``intervention`` absent. The Phase-7 S1
compatibility test re-runs the identical corpus through the extended
runtime with ``intervention=None`` and asserts exact equality.

Provenance of the corpus:
- three real, accepted R7.1 historical states (EARLY / MID / LATE) with pit
  dynamics enabled, reconstructed through the frozen Phase-1..5 replay seam;
- synthetic pit-dynamics and no-pit states on both the scalar and batch
  paths with multiple seeds, to exercise pace, pit-timing, compound,
  pit-loss and stint-target draws.

Usage (from the repository root, with a functional interpreter)::

    /opt/homebrew/bin/python3.11 scripts/capture_phase7_s1_baseline.py

Only the capture step writes the fixture. The compatibility test never
regenerates it.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for extra in (str(ROOT), str(ROOT / "tests")):
    if extra not in sys.path:
        sys.path.insert(0, extra)

FIXTURE_PATH = ROOT / "tests" / "fixtures" / "phase7_s1_phase6_baseline.json"

# Real accepted R7.1 fixtures; parameters are fit strictly before the target
# season and the run uses the leakage-enforced backtest policy (the exact
# R7.1 accepted-state protocol).
REAL_SPECS = (
    {"name": "real_early_2023_r01_alonso_lap2",
     "kind": "real", "season": 2023, "race_id": "2023-r01-R",
     "driver": "alonso", "lap": 2, "seed": 20240101},
    {"name": "real_mid_2022_r01_perez_lap30",
     "kind": "real", "season": 2022, "race_id": "2022-r01-R",
     "driver": "perez", "lap": 30, "seed": 20240101},
    {"name": "real_late_2022_r01_russell_lap38",
     "kind": "real", "season": 2022, "race_id": "2022-r01-R",
     "driver": "russell", "lap": 38, "seed": 20240101},
    {"name": "real_mid_2022_r01_perez_lap30_seed7",
     "kind": "real", "season": 2022, "race_id": "2022-r01-R",
     "driver": "perez", "lap": 30, "seed": 7},
)

# Synthetic states (fixed field, canonical helper builders from the R6
# suite) covering pit and no-pit mechanics on the batch and scalar paths.
SYNTHETIC_SPECS = (
    {"name": "synthetic_pit_seed2024_batch_scalar",
     "kind": "synthetic", "pit": True, "seed": 2024, "count": 100,
     "samples": 10, "scalar": True},
    {"name": "synthetic_nopit_seed2024_batch_scalar",
     "kind": "synthetic", "pit": False, "seed": 2024, "count": 100,
     "samples": 10, "scalar": True},
    {"name": "synthetic_pit_seed5_batch",
     "kind": "synthetic", "pit": True, "seed": 5, "count": 60,
     "samples": 0, "scalar": False},
)

REAL_COUNT = 1000
REAL_SAMPLES = 0


def specs() -> tuple:
    """All capture specs, real first (EARLY / MID / LATE)."""
    return tuple(REAL_SPECS) + tuple(SYNTHETIC_SPECS)


def build_case(spec: dict):
    """Rebuild the exact inputs for one spec (shared by capture and test)."""
    from v2.simulation.config import Assumptions, SimulationConfig
    from v2.simulation.engine import ExecutionPolicy

    if spec["kind"] == "real":
        from test_v2_phase6_r71 import _params_through, _real_state
        state = _real_state(spec["season"], spec["race_id"],
                            spec["driver"], spec["lap"])
        params = _params_through(spec["season"] - 1)
        policy = ExecutionPolicy.HISTORICAL_BACKTEST
        count = spec.get("count", REAL_COUNT)
        samples = spec.get("samples", REAL_SAMPLES)
    else:
        from test_v2_phase6_r6 import make_pit_params, noisy_residual, pit_field
        state = pit_field(3, scheduled=15)
        params = make_pit_params(residual=noisy_residual(),
                                 stint_length=(3.0,), stint_min=2.0,
                                 stint_max=6.0, pit_loss=20.0)
        policy = ExecutionPolicy.RETROSPECTIVE_PRODUCT
        count = spec["count"]
        samples = spec["samples"]

    config = SimulationConfig(
        simulation_count=count, master_seed=spec["seed"],
        sample_orders=samples,
        pit_dynamics_enabled=bool(spec.get("pit", True)))
    return state, params, config, policy


def _snapshot(result) -> dict:
    payload = result.to_dict()
    # Wall-clock runtime is operational metadata and is the only genuinely
    # nondeterministic field; excluded exactly as MonteCarloResult.identity()
    # excludes it.
    payload.pop("runtime_s", None)
    return {"identity": result.identity(), "result": payload}


def run_case(spec: dict) -> dict:
    from v2.simulation.config import Assumptions
    from v2.simulation.monte_carlo import MonteCarloEngine

    state, params, config, policy = build_case(spec)
    engine = MonteCarloEngine(chunk_size=spec.get("chunk", 512))
    batch = engine.run(state, params, config, Assumptions(),
                       execution_policy=policy)
    record = {
        "name": spec["name"],
        "state_identity": state.identity(),
        "config_identity": config.identity(),
        "parameter_identity": params.parameter_identity().identity(),
        "batch": _snapshot(batch),
        "scalar": None,
    }
    if spec.get("scalar"):
        scalar = engine.run_scalar(state, params, config, Assumptions(),
                                   execution_policy=policy)
        record["scalar"] = _snapshot(scalar)
    return record


def _environment() -> dict:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
    }


def capture() -> dict:
    cases = [run_case(spec) for spec in specs()]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "v2-monte-carlo-phase6^{commit}"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:  # pragma: no cover - git optional for capture
        commit = None
    payload = {
        "generated_by": "scripts/capture_phase7_s1_baseline.py",
        "purpose": ("pre-change Phase-6 baseline for the Phase-7 S1 "
                    "default-off intervention seam"),
        "historical_phase6_commit": commit,
        "historical_phase6_tag": "v2-monte-carlo-phase6",
        "environment": _environment(),
        "exclusions": ["runtime_s (wall-clock, operational metadata only)"],
        "cases": cases,
    }
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True)
                            + "\n")
    return payload


if __name__ == "__main__":
    result = capture()
    print(f"wrote {FIXTURE_PATH} with {len(result['cases'])} cases")
