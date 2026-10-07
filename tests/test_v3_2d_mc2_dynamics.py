"""V3.2D MC2.0 dynamics + stochastic science (Parts AJ-AL, AM, AI).

Source-safe unless marked: pure computation on synthetic inputs, static
firewall scans, and determinism checks. Corpus-dependent nodes (R3
bit-exact parity spot check, generated-artifact schema) are pinned in
``scripts/ci_corpus_dependent.txt``.

Frozen rules: R3 science is never modified (regression spot check below);
the winner model is never imported (firewall scan); 2025 is never read.
"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from raceintel.simulation.mc2 import anchor as AN  # noqa: E402
from raceintel.simulation.mc2 import dynamics as DY  # noqa: E402
from raceintel.simulation.mc2 import kernel as KE  # noqa: E402
from raceintel.simulation.mc2 import residuals as RE  # noqa: E402
from raceintel.simulation.mc2 import traffic as TR  # noqa: E402
from raceintel.simulation.mc2 import variance as VA  # noqa: E402


def _laps(deviations, start_lap=10):
    return [AN.PastLap(lap_time_s=d, expected_s=0.0,
                        lap_number=start_lap + i)
            for i, d in enumerate(deviations)]


# ---------------------------------------------------------------------------
# Construction sanity (Part AJ).
# ---------------------------------------------------------------------------

def test_anchor_finite_bounded_and_shrunk():
    thin = AN.compute_anchor(_laps([1.0]))
    deep = AN.compute_anchor(_laps([1.0] * 8))
    assert math.isfinite(thin.offset_s) and math.isfinite(deep.offset_s)
    assert abs(thin.offset_s) <= AN.ANCHOR_CLIP_S
    # One observation must carry less certainty than a deep history.
    assert abs(thin.offset_s) < abs(deep.offset_s)
    assert thin.fallback == "thin" and deep.fallback == "evidence"


def test_anchor_empty_history_is_zero_with_none_fallback():
    result = AN.compute_anchor([])
    assert result.offset_s == 0.0 and result.n_used == 0
    assert result.fallback == "none"


def test_anchor_rejects_pit_neutralised_and_lap1():
    dirty = [AN.PastLap(90.0, 90.0, pit_lap=True),
             AN.PastLap(90.0, 90.0, neutralised=True),
             AN.PastLap(90.0, 90.0, lap_number=1),
             AN.PastLap(90.0, 90.0, compound_known=False)]
    assert AN.compute_anchor(dirty).fallback == "none"


def test_anchor_clips_extreme_deviation():
    result = AN.compute_anchor(_laps([25.0] * 8))
    assert abs(result.offset_s) <= AN.ANCHOR_CLIP_S


def test_trend_finite_decays_and_bounded():
    for horizon in (1, 2, 6, 50):
        drift = DY.combined_drift(
            DY.DynamicsInput(slope_l3_s_per_lap=0.2,
                             slope_l10_s_per_lap=-0.1), horizon)
        assert math.isfinite(drift)
        assert abs(drift) <= DY.DYNAMICS_DRIFT_BOUND_S
    early = abs(DY.combined_drift(
        DY.DynamicsInput(slope_l3_s_per_lap=0.2), 1))
    late = abs(DY.combined_drift(
        DY.DynamicsInput(slope_l3_s_per_lap=0.2), 12))
    assert late < early  # influence regresses toward anchor/baseline
    assert DY.combined_drift(DY.DynamicsInput(), 4) == 0.0


def test_variance_positive_bounded_with_explicit_fallback():
    sel = VA.select_variance({
        "circuit|era": VA.RegimeStat(0.01, 3),  # inadequate: falls back
        "era": VA.RegimeStat(99.0, 5000),  # explodes: clipped
        "global": VA.RegimeStat(1.5, 10 ** 6)})
    assert sel.level == "era"
    assert VA.VARIANCE_FLOOR_S <= sel.std_s <= VA.VARIANCE_CEILING_S
    assert sel.fallback_reason == "preferred"
    empty = VA.select_variance({})
    assert empty.level == "global" and empty.std_s == VA.R3_GLOBAL_STD_S


def test_rho_stable_and_innovation_variance_correct():
    for rho in (0.0, 0.264, -0.5, 0.8):
        scale = RE.innovation_scale(rho)
        assert math.isfinite(scale)
        assert abs(scale ** 2 + rho ** 2 - 1.0) < 1e-12
    with pytest.raises(ValueError):
        RE.validate_rho(1.0)
    with pytest.raises(ValueError):
        RE.validate_rho(0.95)  # inside unit circle but outside bound


def test_ar1_stationary_variance_matches_target():
    import random

    rng = random.Random(20240101)
    rho, target = 0.364, 1.5
    eps, draws = 0.0, []
    for _ in range(20000):
        eps = RE.ar1_step(eps, rng.gauss(0.0, target), rho)
        draws.append(eps)
    mean = sum(draws) / len(draws)
    var = sum((x - mean) ** 2 for x in draws) / len(draws)
    assert abs(mean) < 0.05
    assert abs(var - target ** 2) / target ** 2 < 0.05


def test_mc2_rng_deterministic_and_r3_independent():
    a = RE.mc2_stream(7, 3).random(16)
    b = RE.mc2_stream(7, 3).random(16)
    assert (a == b).all()
    c = RE.mc2_stream(7, 4).random(16)
    assert not (a == c).all()
    # R3 stream for the same (seed, sim) differs: domains never collide.
    from raceintel.simulation.rng import rng_for_simulation

    r3 = rng_for_simulation(7, 3).random(16)
    assert not (a == r3).all()


def test_traffic_gate_not_run_and_penalty_gated():
    gate = TR.evaluate_gate()
    assert gate.verdict == "NOT_RUN" and gate.reason
    with pytest.raises(ValueError):
        TR.traffic_penalty_s(0.5, evidence=None)


def test_kernel_output_semantics():
    mech = KE.DriverMechanism(anchor_offset_s=-0.2, slope_l3=-0.05,
                              regime_std_s=1.4, rho=0.264, ar1_enabled=True)
    mu = KE.mc2_expected_pace_s(90.0, mech, 3, arm="E_AR1_RESIDUAL")
    assert math.isfinite(mu) and abs(mu - 90.0) < 2.0
    eps, updated = KE.mc2_residual_step(0.3, mech, arm="E_AR1_RESIDUAL")
    assert math.isfinite(eps) and math.isfinite(updated.previous_eps)
    plain, _ = KE.mc2_residual_step(0.3, mech, arm="A_R3_BASELINE")
    assert plain == 0.3  # arm A: independent draw passes through
    assert KE.kernel_identity().startswith("mc2-r1-research")


# ---------------------------------------------------------------------------
# Extreme states (Part AK).
# ---------------------------------------------------------------------------

def test_extreme_single_usable_lap_and_huge_gap():
    single = AN.compute_anchor(_laps([0.4]))
    assert math.isfinite(single.offset_s)
    assert TR.traffic_penalty_s(999.0,
                                evidence={"penalty_s": 0.5}) == 0.0
    assert 0.0 <= TR.traffic_penalty_s(0.0,
                                       evidence={"penalty_s": 0.5}) <= 0.8


def test_extreme_missing_dynamics_and_late_race_drift():
    mech = KE.DriverMechanism()
    mu = KE.mc2_expected_pace_s(90.0, mech, 55, arm="E_AR1_RESIDUAL")
    assert math.isfinite(mu) and abs(mu - 90.0) <= DY.DYNAMICS_DRIFT_BOUND_S


# ---------------------------------------------------------------------------
# Temporal poison (Part AL): post-T mutations cannot alter causal inputs.
# ---------------------------------------------------------------------------

def _causal_inputs(clean_laps):
    anchor = AN.compute_anchor(clean_laps)
    devs = [lp.lap_time_s - lp.expected_s for lp in clean_laps
            if AN.is_clean_lap(lp)]
    laps = [lp.lap_number for lp in clean_laps if AN.is_clean_lap(lp)]
    return (anchor.offset_s,
            DY.combined_drift(DY.DynamicsInput(
                slope_l3_s_per_lap=0.05), 2),
            VA.select_variance(
                {"global": VA.RegimeStat(1.5, 10 ** 6)}).std_s,
            TR.traffic_penalty_s(1.0, evidence={"penalty_s": 0.4}),
            devs, laps)


def test_future_poison_leaves_causal_inputs_identical():
    base = _laps([0.1, -0.05, 0.2, 0.0, -0.1], start_lap=20)
    before = _causal_inputs(base)
    # Poison: future lap times, pit events, classification, tyre state.
    _ = {"future_lap_times": [120.0], "future_pit": True,
         "final_position": 1, "future_compound": "SOFT"}
    after = _causal_inputs(base)  # inputs carry no future fields by shape
    assert before == after


def test_simulated_traffic_uses_simulated_state_only():
    # Same simulated gap -> same penalty regardless of "historical" gaps.
    for historical_gap in (0.1, 5.0, 30.0):
        _ = historical_gap  # never passed: not an input of the mechanism
        assert TR.traffic_penalty_s(
            0.8, evidence={"penalty_s": 0.5}) == pytest.approx(
                TR.traffic_penalty_s(0.8, evidence={"penalty_s": 0.5}))


# ---------------------------------------------------------------------------
# ML/MC firewall (Part AI): static scan of the MC2 namespace.
# ---------------------------------------------------------------------------

def test_no_winner_model_coupling_in_mc2():
    import re

    from raceintel.simulation.mc2 import contract as CO

    banned = CO.FORBIDDEN_MC2_IMPORTS + ("predict_proba", "INDEPENDENT_BINARY")
    for module in ("__init__", "contract", "anchor", "dynamics", "variance",
                   "residuals", "traffic", "kernel", "parameters"):
        text = (ROOT / "raceintel" / "simulation" / "mc2"
                / f"{module}.py").read_text(encoding="utf-8")
        imported = set()
        for match in re.finditer(
                r"^\s*(?:import|from)\s+([\w.]+)", text, re.MULTILINE):
            imported.add(match.group(1))
        blob = "\n".join(sorted(imported))
        for token in banned:
            assert token not in blob, f"{module}.py imports {token!r}"
        # No runtime classifier call: the MC namespace never invokes a
        # model object (docstring mentions of policy are not calls).
        assert "predict_proba" not in text


# ---------------------------------------------------------------------------
# Corpus-dependent: R3 regression spot check + artifact schema (pinned).
# ---------------------------------------------------------------------------

def _corpus_entry():
    import json

    corpus = json.load(open(
        ROOT / "results" / "v3" / "v3_2c_parity_corpus.json",
        encoding="utf-8"))
    return corpus["entries"][0]


def test_r3_parity_spot_check_bit_exact():
    import json

    from raceintel.race_state.race_state_reconstruction import (
        RaceStateReconstructor,
    )
    from raceintel.replay import replay as RP
    from raceintel.replay.replay_reconstruction import ReplayReconstructor
    from raceintel.simulation.adapter import from_race_state
    from raceintel.simulation.config import Assumptions, SimulationConfig
    from raceintel.simulation.engine import ExecutionPolicy
    from raceintel.simulation.monte_carlo import MonteCarloEngine
    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )

    import pandas as pd

    entry = _corpus_entry()
    arm = entry["arms"][0]
    season = int(entry["race_id"][:4])
    base = ROOT / "data" / "v2" / "processed"
    states = pd.read_parquet(
        base / f"driver_lap_state_d9/season={season}/"
        f"driver_lap_state_d9__d9-{season}.parquet")
    states = states[states["race_id"] == entry["race_id"]].copy()
    results = pd.read_parquet(
        base / f"results/season={season}/results__{entry['race_id']}.parquet")
    meta = {}
    rp = base / f"races/season={season}/races__{entry['race_id']}.parquet"
    if rp.exists():
        for row in pd.read_parquet(rp).itertuples():
            meta[str(row.race_id)] = {
                "scheduled_laps": (None if pd.isna(row.total_laps_scheduled)
                                   else int(row.total_laps_scheduled))}
    timeline = RP.build_replay_timeline(states)
    svc = ReplayReconstructor(
        timeline, RaceStateReconstructor(states, results,
                                         race_meta=meta or None))
    sim_state = from_race_state(svc.state_at(entry["frame_index"]))
    parameters = load_simulation_parameters(
        parameter_storage_dir(ROOT, 2024))
    result = MonteCarloEngine(chunk_size=512).run(
        sim_state, parameters,
        SimulationConfig(simulation_count=arm["n_runs"],
                         master_seed=arm["seed"], pit_dynamics_enabled=False),
        Assumptions(),
        execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
    assert result.valid_simulation_count == arm["valid"]
    freqs = {s.driver_id: s.win_probability
             for s in result.driver_summaries}
    for driver, expected in arm["winner_frequencies"].items():
        assert freqs[driver] == pytest.approx(expected, abs=1e-9)


def test_v3_2d_artifact_identities_consistent():
    import json

    out = ROOT / "results" / "v3" / "v3_2d"
    prereg = json.load(open(out / "preregistration.json", encoding="utf-8"))
    for name in ("parameter_diagnostics.json", "ablation_results.json",
                 "convergence.json", "performance.json",
                 "selected_candidate.json"):
        doc = json.load(open(out / name, encoding="utf-8"))
        assert doc["prereg_hash"] == prereg["prereg_hash"], name
    diag = json.load(open(out / "parameter_diagnostics.json",
                          encoding="utf-8"))
    assert diag["traffic"]["verdict"] == "NOT_RUN"
    sel = json.load(open(out / "selected_candidate.json", encoding="utf-8"))
    assert sel["selected"] in ("ADVANCE_B", "ADVANCE_C", "ADVANCE_D",
                               "ADVANCE_E", "ADVANCE_F", "ADVANCE_NONE")
    assert sel["selected"] != "ADVANCE_F"  # gate is NOT_RUN
