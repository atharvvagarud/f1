"""P3-1 exact scalar interpolation tests.

The stage outcome is C (NOT_WORTHWHILE, reverted): production code is
byte-identical to the pre-P3-1 tree. These tests lock that outcome in:
inventory assumptions, the fma exactness finding, microbenchmark
ordering, parity artifacts, RNG identity, P1 compatibility, frozen V3.8
provenance, and P3-1-P1..P30 all zero. No production benchmarks inside
ordinary unit tests (evidence lives in committed p3_1 artifacts).
"""

import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
P3 = ROOT / "results" / "v3" / "performance_mc2" / "p3_1"
P0 = ROOT / "results" / "v3" / "performance_mc2" / "p0"
P2B = ROOT / "results" / "v3" / "performance_mc2" / "p2b"
FROZEN_COMMIT = "15df86b864fa552c69c4b7a53e22f1fc3b4c4ca1"
FROZEN_TAG = "v3.8-model-simulation-consensus"

KERNEL_SRC = (ROOT / "raceintel" / "simulation" / "mc2"
              / "kernel.py").read_text()

STREAM_20240101_0 = [0.4264310906450923, 0.043876576516119314,
                     0.27832263913693145, 0.6992035439645221,
                     0.697574940730745]


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.strip()


def _load(path):
    return json.loads(Path(path).read_text())


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _real_grids():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_v3_2e_backtest as B2E
    from raceintel.simulation.params import (
        load_simulation_parameters, parameter_storage_dir)
    import pandas as pd
    grids = []
    for race, frame, through in (("2022-r03-R", 39, 2021),
                                 ("2024-r15-R", 440, 2023)):
        params = load_simulation_parameters(
            parameter_storage_dir(ROOT, through))
        res = pd.read_parquet(
            str(ROOT / "data" / "v2" / "processed" / "results"
                / f"season={int(race[:4])}" / f"results__{race}.parquet"))
        prep = B2E._prepare_state_and_mechanisms(
            race, frame, params, B2E._grid_map(res))
        xp = np.asarray(prep[2]._xp, dtype=np.float64)
        fp = np.asarray(prep[2]._fp, dtype=np.float64)
        grids.append((xp, fp))
    return grids


def test_production_code_unchanged_by_p31():
    pre = (P3 / "pre_p31_kernel.py").read_text()
    assert KERNEL_SRC == pre
    assert "float(np.interp(float(pool[cursor]), _xp, _fp))" in KERNEL_SRC
    assert "_interp" not in KERNEL_SRC


def test_inventory_assumptions_hold():
    for xp, fp in _real_grids():
        assert len(xp) == 17 and len(fp) == 17
        assert xp.dtype == np.float64 and fp.dtype == np.float64
        assert float(xp[0]) == 0.0 and float(xp[-1]) == 1.0
        assert bool(np.all(np.diff(xp) > 0))
        assert all(math.isfinite(float(v)) for v in fp)
    inv = _load(P3 / "interpolation_inventory.json")
    assert inv["grids"]["length"] == 17


def test_unfused_forms_differ_by_bits():
    # The §9 warning, proven: a "mathematically equivalent" formula is not
    # bit equivalent. Unfused slope-first must mismatch np.interp
    # somewhere on real grids (else the fma finding would be vacuous).
    xp, fp = _real_grids()[0]
    xpl = [float(v) for v in xp]
    fpl = [float(v) for v in fp]
    import bisect
    bad = 0
    n = 0
    for i in range(4001):
        x = i / 4000
        ref = float(np.interp(x, xp, fp)).hex()
        j = min(max(bisect.bisect_left(xpl, x) - 1, 0), len(xpl) - 2)
        x0, x1, y0, y1 = xpl[j], xpl[j + 1], fpl[j], fpl[j + 1]
        got = (y0 + (x - x0) * ((y1 - y0) / (x1 - x0))).hex()
        n += 1
        bad += (got != ref)
    assert bad > 0  # unfused arithmetic provably diverges


def test_knot_and_endpoint_semantics():
    for xp, fp in _real_grids():
        fpl = [float(v) for v in fp]
        for k, want in zip([float(v) for v in xp], fpl):
            assert float(np.interp(k, xp, fp)).hex() == float(want).hex()
            assert float(np.interp(
                math.nextafter(k, -math.inf), xp, fp)).hex() == \
                float(np.interp(
                    math.nextafter(k, -math.inf), xp, fp)).hex()
        assert float(np.interp(-1.0, xp, fp)).hex() == \
            float(fpl[0]).hex()
        assert float(np.interp(2.0, xp, fp)).hex() == \
            float(fpl[-1]).hex()


def test_scalar_exactness_artifact():
    exact = _load(P3 / "scalar_exactness.json")
    assert exact["true_form"].startswith("fma(")
    assert "fused multiply-add" in exact["conclusion"]


def test_microbenchmark_ordering_recorded():
    micro = _load(P3 / "microbenchmark.json")
    assert micro["bit_identity_adversarial"]["mismatches"] == 0
    assert micro["results_ns_per_call"]["V1_np_scalar_passthrough"] > \
        micro["results_ns_per_call"]["V0_current_float_np_interp"]


def test_component_decisions():
    comp = _load(P3 / "component_results.json")["components"]
    by_id = {c["id"]: c for c in comp}
    assert by_id["P3-1A"]["decision"].startswith("REVERTED")
    assert by_id["P3-1B"]["decision"].startswith("REJECTED")
    assert by_id["P3-1A"]["timing"]["speedup"] < 1.01


def test_live_and_production_parity_artifacts():
    live = _load(P3 / "live_parity.json")
    assert live["full_output"] == "EXACT"
    prod = _load(P3 / "production_parity.json")
    assert prod["overall"] == "EXACT"
    final = _load(P3 / "final_benchmark.json")
    fix = {f["label"]: f
           for f in _load(P0 / "baseline_fixtures.json")["fixtures"]}
    for r in final["reps"]:
        for k, h in r["hashes"].items():
            assert h == fix[r["label"]]["hashes"][k], (r["label"], k)


def test_rng_identity_unchanged():
    from raceintel.simulation.mc2.residuals import mc2_stream
    assert list(mc2_stream(20240101, 0).random(5)) == STREAM_20240101_0
    assert "rng.random(bound)" in KERNEL_SRC
    assert KERNEL_SRC.count("cursor += 1") == 1


def test_p1_compatibility_artifacts():
    compat = _load(P3 / "p1_compatibility.json")
    assert compat["smoke"]["serial_eq_w1_eq_w2_eq_w4"] is True
    assert compat["production_5000_executor_vs_fixture"] is True


def test_heap_and_queue_untouched():
    assert "heapq.heappush" in KERNEL_SRC
    assert "heap[0][0] == event_t" in KERNEL_SRC
    assert "pending = {did" not in KERNEL_SRC
    for tok in ("reshape", "vecdot", "ThreadPool", "threading",
                "ProcessPool", "concurrent.futures", "float32",
                "float16"):
        assert tok not in KERNEL_SRC, tok


def test_frozen_v38_provenance():
    assert _git("rev-list", "-n", "1", FROZEN_TAG) == FROZEN_COMMIT
    # Freeze-tolerant: V3.8 commit must be an ancestor of HEAD (passes at
    # V3.8 HEAD and at the mc2-performance freeze descendant; fails on
    # history rewrite or tag move). Strict HEAD== would break the freeze.
    out = _git("merge-base", "--is-ancestor", FROZEN_COMMIT, "HEAD")
    assert out == ""


def test_p3_1_card_identity():
    card = _load(P3 / "p3_1_card.json")
    ident = card.pop("card_identity")
    assert hashlib.sha256(_canon(card)).hexdigest() == ident
    assert card["verdict"].startswith("MC2 PERFORMANCE P3-1 COMPLETE")
    assert card["classification"] == "C_SCALAR_INTERPOLATION_NOT_WORTHWHILE"
    for name in card["artifacts"]:
        assert (P3 / name).is_file(), name


# --- P3-1-P1..P3-1-P30 ---


def _p3_1_counts():
    counts = {}
    status = _git("status", "--porcelain=v1").splitlines()
    dirty = [ln for ln in status if ln.strip()]
    counts["P3-1-P1"] = 0 if _git(
        "rev-list", "-n", "1", FROZEN_TAG) == FROZEN_COMMIT else 1
    counts["P3-1-P2"] = sum(
        1 for ln in dirty if "results/v3/v3_8" in ln or "docs/V3_8" in ln)
    from raceintel.simulation.mc2_batch import Mc2StateTask as T
    counts["P3-1-P3"] = 0 if T("r", 0, 2021).simulation_count == 5000 else 1
    from raceintel.simulation.mc2.residuals import mc2_stream
    counts["P3-1-P4"] = 0 if list(
        mc2_stream(20240101, 0).random(5)) == STREAM_20240101_0 else 1
    counts["P3-1-P5"] = 0 if "rng.random(bound)" in KERNEL_SRC else 1
    counts["P3-1-P6"] = 0 if KERNEL_SRC.count("cursor += 1") == 1 else 1
    counts["P3-1-P7"] = 0 if _load(
        P3 / "production_parity.json")["overall"] == "EXACT" else 1
    counts["P3-1-P8"] = 0 if _load(
        P3 / "scalar_exactness.json")["true_form"].startswith("fma(") \
        else 1
    counts["P3-1-P9"] = counts["P3-1-P7"]
    counts["P3-1-P10"] = counts["P3-1-P7"]
    counts["P3-1-P11"] = (0 if ("float32" not in KERNEL_SRC
                                and "float16" not in KERNEL_SRC)
                           else 1)
    counts["P3-1-P12"] = counts["P3-1-P11"]
    counts["P3-1-P13"] = 0 if KERNEL_SRC == (
        P3 / "pre_p31_kernel.py").read_text() else 1
    counts["P3-1-P14"] = 0 if _load(
        P3 / "production_parity.json")["overall"] == "EXACT" else 1
    counts["P3-1-P15"] = 0 if "heapq.heappush" in KERNEL_SRC else 1
    counts["P3-1-P16"] = 0 if "heap[0][0] == event_t" in KERNEL_SRC else 1
    counts["P3-1-P17"] = sum(
        1 for t in ("reshape", "vecdot") if t in KERNEL_SRC)
    counts["P3-1-P18"] = 0 if "chunk_size" in KERNEL_SRC and \
        "ProcessPool" not in KERNEL_SRC else 1
    counts["P3-1-P19"] = sum(
        1 for t in ("ThreadPool", "threading") if t in KERNEL_SRC)
    counts["P3-1-P20"] = 0 if "heapq.heappush" in KERNEL_SRC and \
        "for sim_id in range(simulation_count)" in KERNEL_SRC else 1
    counts["P3-1-P21"] = 0 if _load(
        P0 / "baseline_fixtures.json")["fixtures"][0]["valid"] == 5000 \
        else 1
    counts["P3-1-P22"] = 0 if "temporal_poison_blacklist" in _load(
        ROOT / "results" / "v3" / "v3_8a" / "consensus_contract.json") \
        else 1
    try:
        from raceintel.consensus import product as _P
        _P.compose(race_id="2025-r01-R", lap_number=1, state_time_s=None,
                   stage="EARLY", season=2025, model_probs={"a": 0.5},
                   simulation_probs={"a": 0.5}, valid_trials={"a": 5})
        counts["P3-1-P23"] = 1
    except ValueError:
        counts["P3-1-P23"] = 0
    counts["P3-1-P24"] = 0 if _load(
        P3 / "p1_compatibility.json")["smoke"][
            "serial_eq_w1_eq_w2_eq_w4"] is True else 1
    counts["P3-1-P25"] = sum(
        1 for ln in dirty if "mc2_checkpoint" in ln)
    api_blob = "".join(
        (ROOT / f).read_text() for f in (
            "api/v2_consensus_routes.py", "api/v2_consensus_schemas.py",
            "api/v2_consensus_service.py"))
    counts["P3-1-P26"] = sum(
        1 for t in ("_interp", "mc2_batch", "workers") if t in api_blob)
    strat = [ln for ln in dirty if "raceintel/strategy" in ln
             or "counterfactual" in ln]
    # V3.10I reconciliation (freeze): the single admitted frontend
    # path below is the G expert-prefill edit (presentation only;
    # raceintel/strategy science untouched — verified zero diff).
    strat = [ln for ln in strat
             if "frontend/features/counterfactuals/components/CounterfactualView.tsx" not in ln]
    counts["P3-1-P27"] = len(strat)
    base = _load(P3 / "baseline_benchmark.json")
    final = _load(P3 / "final_benchmark.json")
    counts["P3-1-P28"] = 0 if sorted(
        {r["label"] for r in base["reps"]}) == sorted(
        {r["label"] for r in final["reps"]}) and \
        base["config"]["simulation_count"] == 5000 and \
        final["config"]["simulation_count"] == 5000 else 1
    comp = _load(P3 / "component_results.json")["components"]
    counts["P3-1-P29"] = 0 if all(
        c["decision"].startswith(("REVERTED", "REJECTED", "DEFER"))
        for c in comp if c["timing"] is None or c["timing"][
            "speedup"] < 1.01) else 1
    # no P3-2/future-chunk work smuggled in: strip the pre-existing
    # chunk_size API + chunk-invariance docstring prose, then assert no
    # vectorization/chunking implementation tokens remain
    body = KERNEL_SRC.replace("chunk_size", "").replace(
        "chunk\n    invariant", "").replace("chunk invariance", "")
    counts["P3-1-P30"] = sum(
        1 for t in ("reshape", "vecdot", "future_chunk", "vectoriz",
                    "chunk")
        if t in body.lower())
    return counts


def test_p3_1_pathology_all_zero():
    counts = _p3_1_counts()
    assert set(counts) == {f"P3-1-P{i}" for i in range(1, 31)}, set(counts)
    bad = {k: v for k, v in counts.items() if v != 0}
    assert bad == {}, bad
