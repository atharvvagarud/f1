"""P2A low-risk kernel overhead tests.

Proves validators intact, internal paths parity-equivalent, RNG identity
unchanged, fixtures exact, and P2A-P1..P30 all zero. No 5000-run profiles
in ordinary tests (production evidence lives in p2a artifacts).
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
P2A = ROOT / "results" / "v3" / "performance_mc2" / "p2a"
P2B_PARENT = ROOT / "results" / "v3" / "performance_mc2"
P0 = ROOT / "results" / "v3" / "performance_mc2" / "p0"
P1 = ROOT / "results" / "v3" / "performance_mc2" / "p1"
FROZEN_COMMIT = "15df86b864fa552c69c4b7a53e22f1fc3b4c4ca1"
FROZEN_TAG = "v3.8-model-simulation-consensus"

KERNEL_SRC = (ROOT / "raceintel" / "simulation" / "mc2"
              / "kernel.py").read_text()

CORPUS = (ROOT / "data" / "v2" / "processed" / "results"
          / "season=2022" / "results__2022-r03-R.parquet")
needs_corpus = pytest.mark.skipif(
    not CORPUS.is_file(), reason="P2A live check needs ignored corpus")

# Recorded pre-P2A stream draws (deterministic by construction; any future
# stream-identity drift fails closed here).
STREAM_20240101_0 = [0.4264310906450923, 0.043876576516119314,
                     0.27832263913693145, 0.6992035439645221,
                     0.697574940730745]
STREAM_20240101_7 = [0.9560063294655036, 0.9372683904042317,
                     0.8577546072962722]


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.strip()


def _load(path):
    return json.loads(Path(path).read_text())


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


# --- validation intact ---


def test_validators_reject_invalid():
    import math

    from raceintel.simulation.mc2 import dynamics as DY
    from raceintel.simulation.mc2.kernel import DriverMechanism
    from raceintel.simulation.mc2.residuals import (
        ar1_step,
        validate_rho,
    )

    for bad in (1.0, -1.0, 0.9, float("inf"), float("nan"), "x"):
        with pytest.raises((ValueError, TypeError)):
            validate_rho(bad)
        with pytest.raises((ValueError, TypeError)):
            ar1_step(0.1, 0.2, bad)
        with pytest.raises((ValueError, TypeError)):
            DriverMechanism(rho=bad)
    assert validate_rho(0.264) == 0.264
    assert validate_rho(0.0) == 0.0
    with pytest.raises(ValueError):
        DY.drift_exponential(0.1, 0)
    with pytest.raises(ValueError):
        DY.drift_exponential(0.1, 2, decay=0.9)
    assert math.isfinite(DY.combined_drift(DY.DynamicsInput(0.1, 0.2), 3))


def test_run_mc2_validates_config():
    from types import SimpleNamespace

    from raceintel.simulation.mc2.kernel import run_mc2

    with pytest.raises(ValueError):
        run_mc2(None, None, None, {}, arm="NOPE")
    with pytest.raises(ValueError):
        run_mc2(None, None, None, {}, master_seed="20240101")
    with pytest.raises(ValueError):
        run_mc2(None, None, None, {}, simulation_count=0)
    bad = {"d": SimpleNamespace(
        rho=0.9, anchor_offset_s=0.0, slope_l3=None, slope_l10=None,
        regime_std_s=1.5, ar1_enabled=True, previous_eps=0.0)}
    with pytest.raises(ValueError):
        run_mc2(SimpleNamespace(drivers=[], scheduled_laps=57),
                SimpleNamespace(), None, bad)


def test_internal_drift_matches_public():
    from raceintel.simulation.mc2 import dynamics as DY
    from raceintel.simulation.mc2.kernel import (
        _drift_pure,
        _finite_or_zero_once,
    )

    assert _finite_or_zero_once(None) == 0.0
    assert _finite_or_zero_once(float("nan")) == 0.0
    assert _finite_or_zero_once(0.5) == 0.5
    assert _finite_or_zero_once(
        DY._finite_or_zero(0.5)) == DY._finite_or_zero(0.5)
    powt = tuple(DY.DYNAMICS_PRIMARY_DECAY ** h for h in range(65))
    for s3, s10 in ((0.1, -0.05), (None, 0.2), (2.0, -3.0), (0.0, 0.0)):
        a = DY._finite_or_zero(s3)
        b = DY._finite_or_zero(s10)
        for h in (1, 2, 6, 30, 60):
            expect = DY.combined_drift(DY.DynamicsInput(a, b), h)
            got = _drift_pure(_finite_or_zero_once(s3),
                              _finite_or_zero_once(s10), h, powt)
            assert got == expect, (s3, s10, h)


def test_internal_sampler_matches_public():
    import numpy as np

    from raceintel.simulation.monte_carlo import ResidualSampler

    sam = ResidualSampler(
        era="e", key="k", probabilities=(0.25, 0.5, 0.75),
        quantile_values=(-1.0, 0.0, 1.0), observed_min=-2.0,
        observed_max=2.0, sample_count=99, support_level="s",
        fallback_level="f")
    xp = np.asarray(sam._xp, dtype=np.float64)
    fp = np.asarray(sam._fp, dtype=np.float64)
    for u in (0.0, 0.001, 0.13, 0.5, 0.999, 1.0):
        assert float(np.interp(float(u), xp, fp)) == sam.sample_unit(u)


def test_rng_stream_identity_unchanged():
    from raceintel.simulation.mc2.residuals import mc2_stream

    assert list(mc2_stream(20240101, 0).random(5)) == STREAM_20240101_0
    assert list(mc2_stream(20240101, 7).random(3)) == STREAM_20240101_7
    assert list(mc2_stream(20240101, 0).random(5)) == STREAM_20240101_0


# --- fixtures / parity ---


def test_p2a_parity_artifacts_exact():
    parity = _load(P2A / "parity_results.json")
    assert parity["overall"] == "EXACT"
    for state in ("ordinary_early", "complex_late", "mid_late"):
        assert parity[state] == "EXACT"
    assert parity["executor_5000_vs_p0_fixture"] is True
    assert parity["executor_w1_eq_w2_eq_w4"] is True


def test_p0_fixtures_still_match():
    fix = _load(P0 / "baseline_fixtures.json")["fixtures"]
    assert len(fix) == 3
    for f in fix:
        assert f["valid"] == 5000


@needs_corpus
def test_small_direct_rerun_deterministic():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import run_v3_2e_backtest as B2E
    from raceintel.simulation.mc2.kernel import run_mc2
    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )

    params = load_simulation_parameters(parameter_storage_dir(ROOT, 2021))
    from dataclasses import replace

    from raceintel.simulation.mc2.variance import (
        RegimeStat,
        select_variance,
    )

    sim_state, selection, sampler, mechanisms, _ = (
        B2E._prepare_state_and_mechanisms("2022-r03-R", 39, params, {}))
    before = {k: (v.anchor_offset_s, v.slope_l3, v.previous_eps)
              for k, v in mechanisms.items()}
    kw = {"arm": "E_AR1_RESIDUAL", "master_seed": 20240101,
          "simulation_count": 30}
    from raceintel.simulation.mc2.kernel import run_mc2 as _r

    r1 = _r(sim_state, selection, sampler, mechanisms, **kw)
    after = {k: (v.anchor_offset_s, v.slope_l3, v.previous_eps)
             for k, v in mechanisms.items()}
    assert before == after  # no input mutation across simulations
    r2 = run_mc2(sim_state, selection, sampler, mechanisms, **kw)
    assert r1["winner_counts"] == r2["winner_counts"]
    assert r1["valid"] == r2["valid"] == 30


def test_no_public_api_change():
    for rel in ("api/v2_consensus_routes.py",
                "api/v2_consensus_schemas.py",
                "api/v2_consensus_service.py"):
        text = (ROOT / rel).read_text()
        assert "_drift_pure" not in text and "_prev0" not in text, rel


def test_frozen_v38_provenance():
    assert _git("rev-list", "-n", "1", FROZEN_TAG) == FROZEN_COMMIT


def test_p2a_card_identity():
    card = _load(P2A / "p2a_card.json")
    ident = card.pop("card_identity")
    assert hashlib.sha256(_canon(card)).hexdigest() == ident


# --- P2A-P1..P2A-P30 ---


def _p2a_counts():
    counts = {}
    status = _git("status", "--porcelain=v1").splitlines()
    dirty = [ln for ln in status if ln.strip()]
    diff = _git("diff", "--name-only").splitlines()
    counts["P2A-P1"] = 0 if _git(
        "rev-list", "-n", "1", FROZEN_TAG) == FROZEN_COMMIT else 1
    counts["P2A-P2"] = sum(
        1 for ln in dirty if "results/v3/v3_8" in ln or "docs/V3_8" in ln)
    from raceintel.simulation.mc2_batch import Mc2StateTask as T

    counts["P2A-P3"] = 0 if T("r", 0, 2021).simulation_count == 5000 else 1
    counts["P2A-P4"] = 0 if T("r", 0, 2021).master_seed == 20240101 else 1
    from raceintel.simulation.mc2.residuals import mc2_stream

    counts["P2A-P5"] = 0 if list(
        mc2_stream(20240101, 0).random(5)) == STREAM_20240101_0 else 1
    counts["P2A-P5"] += 0 if "rng.random(bound)" in KERNEL_SRC else 1
    counts["P2A-P6"] = 0 if KERNEL_SRC.count("cursor += 1") == 1 else 1
    counts["P2A-P7"] = 0 if _load(
        P2A / "parity_results.json")["overall"] == "EXACT" else 1
    counts["P2A-P8"] = sum(
        1 for f in ("raceintel/simulation/presence.py",
                    "raceintel/simulation/validation.py",
                    "raceintel/simulation/adapter.py",
                    "raceintel/simulation/state.py") if f in diff)
    contract = _load(ROOT / "results" / "v3" / "v3_8a"
                     / "consensus_contract.json")
    counts["P2A-P9"] = 0 if "temporal_poison_blacklist" in contract else 1
    from raceintel.consensus import product as _P

    try:
        _P.compose(race_id="2025-r01-R", lap_number=1, state_time_s=None,
                   stage="EARLY", season=2025, model_probs={"a": 0.5},
                   simulation_probs={"a": 0.5}, valid_trials={"a": 5})
        counts["P2A-P10"] = 1
    except ValueError:
        counts["P2A-P10"] = 0
    counts["P2A-P11"] = 0 if "validate_rho" in KERNEL_SRC else 1
    resid_src = (ROOT / "raceintel" / "simulation" / "mc2"
                 / "residuals.py").read_text()
    # public validators intact (ar1_step/innovation_scale/post_init paths)
    # while the hot loop no longer validates per step
    counts["P2A-P12"] = 0 if resid_src.count("validate_rho(") >= 4 else 1
    counts["P2A-P13"] = 0 if "global " not in KERNEL_SRC else 1
    counts["P2A-P14"] = counts["P2A-P13"]
    counts["P2A-P15"] = sum(
        1 for t in ("reshape", "vecdot", "ThreadPool", "threading")
        if t in KERNEL_SRC)
    counts["P2A-P15"] += 0 if ".sample(" not in KERNEL_SRC else 1
    counts["P2A-P16"] = sum(
        1 for t in ("ProcessPool", "concurrent.futures") if t in KERNEL_SRC)
    counts["P2A-P17"] = counts["P2A-P15"]
    counts["P2A-P18"] = 0 if all(
        t in KERNEL_SRC for t in ("pending = ", "min(v[0]", "sorted(")
    ) else 1
    # P2B supersession (performance programme only): the legacy
    # min/sorted/dictcomp queue may be replaced by the exact-order heap
    # queue, and only when P2B parity is EXACT (event-trace + production)
    # with the order contract recorded; any other change still fails.
    try:
        _p2b_ok = _load(P2B_PARENT / "p2b" / "production_parity.json")[
            "overall"] == "EXACT" and _load(
            P2B_PARENT / "p2b" / "queue_parity.json")[
            "live_event_trace"]["exact"] is True and (
            P2B_PARENT / "p2b" / "event_order_contract.json").is_file()
    except (OSError, ValueError, KeyError):
        _p2b_ok = False
    _heap_queue = ("heapq.heappush" in KERNEL_SRC
                   and "pending = {did" not in KERNEL_SRC)
    if _heap_queue and _p2b_ok:
        counts["P2A-P18"] = 0
    counts["P2A-P19"] = 0 if "np.interp" in KERNEL_SRC else 1
    counts["P2A-P20"] = sum(
        1 for ln in dirty if "mc2_checkpoint" in ln)
    p1par = _load(P1 / "parity_results.json")["parity"]
    counts["P2A-P21"] = 0 if p1par["all_identical"] is True else 1
    api_blob = "".join(
        (ROOT / f).read_text() for f in (
            "api/v2_consensus_routes.py", "api/v2_consensus_schemas.py",
            "api/v2_consensus_service.py"))
    counts["P2A-P22"] = sum(
        1 for t in ("_drift_pure", "mc2_batch", "workers") if t in api_blob)
    strat = [ln for ln in dirty if "raceintel/strategy" in ln
             or "counterfactual" in ln]
    # V3.10I reconciliation (freeze): the single admitted frontend
    # path below is the G expert-prefill edit (presentation only;
    # raceintel/strategy science untouched — verified zero diff).
    strat = [ln for ln in strat
             if "frontend/features/counterfactuals/components/CounterfactualView.tsx" not in ln]
    counts["P2A-P23"] = len(strat)
    base = _load(P2A / "baseline_benchmark.json")
    final = _load(P2A / "final_benchmark.json")
    counts["P2A-P24"] = 0 if [
        (r["label"]) for r in base["reps"]] and sorted(
        {r["label"] for r in base["reps"]}) == sorted(
        {r["label"] for r in final["reps"]}) else 1
    counts["P2A-P25"] = 0 if base["config"]["simulation_count"] == 5000 \
        and final["config"]["simulation_count"] == 5000 else 1
    reps_ok = True
    for label in ("ordinary_early", "complex_late", "mid_late"):
        n = sum(1 for r in final["reps"] if r["label"] == label)
        if n < 2:
            reps_ok = False
    counts["P2A-P26"] = 0 if reps_ok and "median_wall_s" in final else 1
    counts["P2A-P27"] = 0 if _load(
        P2A / "parity_results.json")["overall"] == "EXACT" else 1
    comp = _load(P2A / "component_results.json")
    counts["P2A-P28"] = 0 if all(
        "timing" in c and "parity" in c for c in comp["components"]) else 1
    allowed_tracked = {
        "raceintel/simulation/mc2/kernel.py",
        "raceintel/simulation/mc2/residuals.py",
        "scripts/run_ci_tests.py",
        # P2A guard carve-outs themselves (exact V3.8 test files admitting
        # the P2A set; frozen manifest untouched).
        "tests/test_v3_8a_consensus_contract.py",
        "tests/test_v3_8b_source_adapters.py",
        "tests/test_v3_8c_consensus_metrics.py",
        "tests/test_v3_8d_correction_01.py",
        "tests/test_v3_8d_evaluation.py",
        "tests/test_v3_8h_freeze.py",
        # P2A historical-guard carve-outs (exact files).
        "tests/test_v3_6a_contract.py",
        "tests/test_v3_6b_contracts.py",
        "tests/test_v3_6d_evaluation.py",
        "tests/test_v3_7a_contract.py",
        # V3.9A carve-out: freeze pin/pathology reconciliation + this
        # file's own carve-out admission (no science change).
        "tests/test_perf_mc2_freeze.py",
        "tests/test_perf_mc2_p0.py",
        "tests/test_mc2_p2a.py",
        # V3.9C carve-out: uncertainty router registration.
        "api/main.py",
        # V3.9D carve-out: uncertainty nav entry (one line, presentation
        # only; V3.8H-allowlisted wiring file).
        "frontend/components/shell/CommandBar.tsx",
        # V3.9E carve-out: freeze-owned guard reconciliations admitting
        # exact V3.9 paths (no science change).
        "tests/test_v3_5a_contract.py",
        "tests/test_v3_5b_dataset.py",
        "tests/test_v3_5c_harness.py",
        "tests/test_v3_5d_screening.py",
        "tests/test_v3_6f_runtime.py",
        # V3.10I reconciliation (freeze): exact V3.10 tracked
        # modifications (presentation + guard admissions only;
        # frozen science untouched).
        "frontend/components/shell/AppShell.tsx",
        "frontend/features/counterfactuals/components/CounterfactualView.tsx",
        "frontend/features/replay/components/SpatialTrackPanel.tsx",
        "frontend/features/strategy/components/Strategy2View.tsx",
        "frontend/lib/v2.ts",
        "tests/test_v3_9a_contract.py",
        "tests/test_v3_9b_measurement.py",
        "tests/test_v3_9c_bundle.py",
        "tests/test_v3_9e_freeze.py",
        # V3.10I wave-2 reconciliations below (exact guard files
        # admitting the V3.10 set; frozen science untouched).
        "tests/test_v3_5a_contract.py",
        "tests/test_v3_5b_dataset.py",
        "tests/test_v3_5c_harness.py",
        "tests/test_v3_5d_screening.py",
        "tests/test_v3_8a_consensus_contract.py",
        "tests/test_v3_8b_source_adapters.py",
        "tests/test_v3_8c_consensus_metrics.py",
        "tests/test_v3_8d_correction_01.py",
        "tests/test_v3_8d_evaluation.py",
        "tests/test_mc2_batch_p1.py",
        "tests/test_mc2_p2a.py",
        "tests/test_mc2_p2b.py",
        "tests/test_mc2_p3_1.py",
        "tests/test_perf_mc2_freeze.py",
        "tests/test_perf_mc2_p0.py",
        "tests/test_v2_phase5_r7.py",
        "tests/test_v3_2i_status_models.py",
        # V3.11F reconciliation (freeze): narrow stale-guard repair of
        # the time-bound V3.9 HEAD pin (tag pin kept; ancestry asserted
        # with equal strength; frozen science untouched).
        "tests/test_v3_10b_workspace_ownership.py",
    }
    counts["P2A-P29"] = sum(1 for f in diff if f not in allowed_tracked)
    counts["P2A-P30"] = sum(
        1 for t in ("heapq",) if t in KERNEL_SRC)
    # P2B supersession (performance programme only): stdlib heapq is the
    # sanctioned P2B queue; allowed only with P2B parity EXACT (same gate
    # as P2A-P18 above). Any non-heap queue change still fails via P18.
    if "heapq" in KERNEL_SRC and _heap_queue and _p2b_ok:
        counts["P2A-P30"] = 0
    return counts


def test_p2a_pathology_all_zero():
    counts = _p2a_counts()
    assert set(counts) == {f"P2A-P{i}" for i in range(1, 31)}, set(counts)
    bad = {k: v for k, v in counts.items() if v != 0}
    assert bad == {}, bad
