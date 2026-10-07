"""V3.2E controlled temporal backtest tests (Parts AV, E, I, T, U, S).

Source-safe: pure computation on synthetic inputs, static firewall scans,
frozen-policy unit checks. Corpus-dependent nodes (population identity,
fold artifacts, determinism record — requiring ignored data/v2/processed
and uncommitted results/v3/v3_2e) are pinned in
``scripts/ci_corpus_dependent.txt``.
"""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from raceintel.simulation import validation as V7  # noqa: E402

OUT = ROOT / "results" / "v3" / "v3_2e"


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Source-safe: metric correctness (R7 definitions on synthetic inputs).
# ---------------------------------------------------------------------------

def test_winner_log_loss_correctness_and_epsilon_policy():
    probs = {"a": 0.5, "b": 0.3, "c": 0.2}
    assert V7.winner_log_loss(probs, "a") == pytest.approx(-math.log(0.5))
    # Zero simulated frequency: predeclared epsilon clip, never -inf.
    zero = {"a": 0.0, "b": 0.6, "c": 0.4}
    assert V7.winner_log_loss(zero, "a") == pytest.approx(
        -math.log(V7.R7_WINNER_LOG_EPSILON))
    assert V7.R7_WINNER_LOG_EPSILON == 1e-6
    assert V7.R7_POSITION_LOG_EPSILON == 1e-6


def test_brier_and_topk_correctness():
    probs = {"a": 0.5, "b": 0.3, "c": 0.2}
    assert V7.brier_score(probs, "a") == pytest.approx(
        ((0.5 - 1) ** 2 + 0.3 ** 2 + 0.2 ** 2) / 3)
    assert V7.top_k_winner_accuracy(probs, "a", k=1) is True
    assert V7.top_k_winner_accuracy(probs, "c", k=1) is False
    assert V7.top_k_winner_accuracy(probs, "c", k=3) is True


def test_position_scores_correctness():
    dist = {1: 0.5, 2: 0.3, 3: 0.2}
    assert V7.ranked_probability_score(dist, 1) == pytest.approx(
        ((0.5 - 1) ** 2 + (0.8 - 1) ** 2) / 2)
    assert V7.position_log_score(dist, 2) == pytest.approx(-math.log(0.3))
    assert V7.expected_finish_mae(
        {"a": 1.5, "b": 3.0}, {"a": 1, "b": 5}, ["a", "b"]) == pytest.approx(
            (0.5 + 2.0) / 2)


# ---------------------------------------------------------------------------
# Source-safe: race-level aggregation + bootstrap determinism.
# ---------------------------------------------------------------------------

def test_race_macro_and_bootstrap_determinism():
    from run_v3_2e_backtest import paired_bootstrap, race_macro  # noqa

    def _arm(wll):
        return {"winner_logloss": wll, "winner_brier": 0.1,
                "podium_brier": 0.1, "exp_mae": 5.0, "rps": 0.1,
                "top_prob": 0.4, "top1": True, "top3": True,
                "valid": 100, "invalid": 0}

    rows = [
        {"race_id": "r1", "season": 2020, "stage": "EARLY",
         "arms": {"A_R3_BASELINE": _arm(1.0),
                  "B_DRIVER_ANCHOR": _arm(0.9),
                  "C_DRIVER_ANCHOR_PLUS_DYNAMICS": _arm(0.8),
                  "D_CONDITIONED_VARIANCE": _arm(0.7),
                  "E_AR1_RESIDUAL": _arm(0.5)}},
        {"race_id": "r1", "season": 2020, "stage": "EARLY",
         "arms": {"A_R3_BASELINE": _arm(3.0),
                  "B_DRIVER_ANCHOR": _arm(2.9),
                  "C_DRIVER_ANCHOR_PLUS_DYNAMICS": _arm(2.8),
                  "D_CONDITIONED_VARIANCE": _arm(2.7),
                  "E_AR1_RESIDUAL": _arm(2.5)}},
    ]
    races = race_macro(rows)
    assert races["r1"]["arms"]["A_R3_BASELINE"]["winner_logloss"] == \
        pytest.approx(2.0)
    diffs = [races["r1"]["arms"]["A_R3_BASELINE"]["winner_logloss"]
             - races["r1"]["arms"]["E_AR1_RESIDUAL"]["winner_logloss"]]
    first = paired_bootstrap(diffs)
    second = paired_bootstrap(diffs)
    assert first == second  # deterministic seed policy
    assert first["ci95_low"] <= first["mean"] <= first["ci95_high"]


# ---------------------------------------------------------------------------
# Source-safe: verdict logic branches (synthetic aggregates, no outcomes).
# ---------------------------------------------------------------------------

def _margins():
    return {"brier_ci_low": -0.005, "podium_brier_ci_low": -0.005,
            "mae_ci_low_laps": -0.05, "invalid_rate_max": 0.01,
            "invalid_rate_vs_A_pp": 0.005,
            "fold_degradation_ci_high": -0.05, "fold_neutral_point": -0.01}


def _boot(mean, low, high):
    return {"mean": mean, "ci95_low": low, "ci95_high": high}


def _inv(e_rate=0.0, a_rate=0.0):
    return {"E_AR1_RESIDUAL": {"invalid_rate": e_rate},
            "A_R3_BASELINE": {"invalid_rate": a_rate}}


def _folds(*vals):
    return dict(zip(("D1", "D2", "D3"), vals))


def test_verdict_logic_keep_e():
    from analyze_v3_2e_results import propose_verdict  # noqa

    b = {"winner_logloss": _boot(0.7, 0.2, 1.2),
         "winner_brier": _boot(0.007, 0.003, 0.011),
         "podium_brier": _boot(0.006, -0.001, 0.012),
         "exp_mae": _boot(0.2, 0.12, 0.28)}
    proposed, _, simpler = propose_verdict(
        b, _inv(), _folds(0.5, 0.1, 2.7), True, _margins())
    assert proposed == "KEEP_MC2_E" and simpler is None


def test_verdict_logic_retain_r3():
    from analyze_v3_2e_results import propose_verdict  # noqa

    b = {"winner_logloss": _boot(-0.1, -0.5, 0.3),
         "winner_brier": _boot(-0.01, -0.02, 0.0),
         "podium_brier": _boot(-0.01, -0.02, 0.0),
         "exp_mae": _boot(-0.2, -0.4, 0.0)}
    proposed, _, _ = propose_verdict(
        b, _inv(), _folds(-0.1, -0.2, 0.0), True, _margins())
    assert proposed == "RETAIN_R3"


def test_verdict_logic_simpler_arm():
    from analyze_v3_2e_results import propose_verdict  # noqa

    b = {"winner_logloss": _boot(-0.1, -0.5, 0.3),
         "winner_brier": _boot(0.0, -0.001, 0.002),
         "podium_brier": _boot(0.0, -0.001, 0.002),
         "exp_mae": _boot(0.0, -0.01, 0.02),
         "simpler_B_DRIVER_ANCHOR": {
             "winner_logloss": _boot(0.5, 0.1, 0.9),
             "winner_brier": _boot(0.005, 0.001, 0.009),
             "podium_brier": _boot(0.004, 0.0, 0.008),
             "exp_mae": _boot(0.15, 0.05, 0.25)}}
    proposed, _, simpler = propose_verdict(
        b, _inv(), _folds(0.0, 0.0, 0.0), True, _margins())
    assert proposed == "KEEP_SIMPLER_ARM_B"
    assert simpler == {"arm": "B_DRIVER_ANCHOR"}


def test_verdict_logic_invalid_blocks_keep():
    from analyze_v3_2e_results import propose_verdict  # noqa

    b = {"winner_logloss": _boot(0.7, 0.2, 1.2),
         "winner_brier": _boot(0.007, 0.003, 0.011),
         "podium_brier": _boot(0.006, -0.001, 0.012),
         "exp_mae": _boot(0.2, 0.12, 0.28)}
    proposed, _, _ = propose_verdict(
        b, _inv(e_rate=0.05), _folds(0.5, 0.1, 2.7), True, _margins())
    assert proposed == "RETAIN_R3"


# ---------------------------------------------------------------------------
# Source-safe: temporal constants + evaluation-script firewall (static).
# ---------------------------------------------------------------------------

def test_eval_seasons_exclude_2025():
    from run_v3_2e_backtest import EVAL_SEASONS, FOLD_THROUGH  # noqa

    assert 2025 not in EVAL_SEASONS
    assert max(FOLD_THROUGH) <= 2024 and max(FOLD_THROUGH.values()) <= 2023
    assert set(FOLD_THROUGH) == set(EVAL_SEASONS)


def test_evaluation_scripts_have_no_model_coupling():
    banned = ("model_lab", "v2.prediction", "predict_proba", "sklearn",
              "frontend", "INDEPENDENT_BINARY")
    for name in ("run_v3_2e_backtest.py", "analyze_v3_2e_results.py",
                 "verify_v3_2e_verdict.py", "freeze_v3_2e_prereg.py"):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        imported = set()
        import re

        for match in re.finditer(r"^\s*(?:import|from)\s+([\w.]+)", text,
                                 re.MULTILINE):
            imported.add(match.group(1))
        blob = "\n".join(sorted(imported))
        for token in banned:
            assert token not in blob, f"{name} imports {token!r}"


# ---------------------------------------------------------------------------
# Corpus-dependent (pinned): population, folds, artifacts, determinism.
# ---------------------------------------------------------------------------

def test_population_identity_and_arm_equality():
    pop = _load("population.json")
    assert pop["evaluated_checkpoints"] == 1636
    assert len(pop["races"]) == 75
    assert pop["excluded_checkpoints"] == 1
    seasons = {e["season"] for e in pop["evaluated"]}
    assert seasons == {2020, 2021, 2022, 2023, 2024}
    assert "2025" not in json.dumps(pop["evaluated"])
    fold = _load("fold_results.json")
    assert fold["population_hash"] == pop["population_hash"]
    assert fold["n_runs"] == 1000 and fold["master_seed"] == 20240101
    for entry in fold["checkpoints"]:
        for arm in ("A_R3_BASELINE", "B_DRIVER_ANCHOR",
                    "C_DRIVER_ANCHOR_PLUS_DYNAMICS",
                    "D_CONDITIONED_VARIANCE", "E_AR1_RESIDUAL"):
            assert arm in entry
            assert (entry[arm]["valid"] + entry[arm]["invalid"]
                    == fold["n_runs"])


def test_temporal_fold_parameters_exact():
    pop = _load("population.json")
    expected = {2020: 2019, 2021: 2019, 2022: 2021, 2023: 2021, 2024: 2023}
    for e in pop["evaluated"]:
        assert e["fold_through"] == expected[e["season"]]
        assert e["fold_through"] < e["season"]
    from raceintel.simulation.params import parameter_storage_dir  # noqa

    for through in (2019, 2021, 2023):
        manifest = parameter_storage_dir(ROOT, through) / "manifest.json"
        assert manifest.exists(), through


def test_ablation_and_bootstrap_identity():
    pop = _load("population.json")
    ab = _load("ablations.json")
    assert ab["population_hash"] == pop["population_hash"]
    assert set(ab["ablations"]) == {"anchor_A_vs_B", "dynamics_B_vs_C",
                                    "variance_C_vs_D", "ar1_D_vs_E"}
    bs = _load("bootstrap.json")
    assert bs["population_hash"] == pop["population_hash"]
    assert set(bs["metrics"]) == {"winner_logloss", "winner_brier",
                                  "podium_brier", "exp_mae", "rps"}
    for m, v in bs["metrics"].items():
        assert v["n_races"] == 75
        assert v["ci95_low"] <= v["mean"] <= v["ci95_high"]


def test_determinism_record_green():
    det = _load("determinism.json")
    pop = _load("population.json")
    assert det["population_hash"] == pop["population_hash"]
    assert det["all_match"] is True
    assert len(det["checks"]) == 3


def test_r3_behavioral_sanity_and_verdict_recorded():
    inv = _load("invalid_runs.json")
    assert inv["arms"]["A_R3_BASELINE"]["invalid"] == 0
    assert inv["arms"]["A_R3_BASELINE"]["valid"] == 1636 * 1000
    verdict = _load("scientific_verdict.json")
    assert verdict["proposed"] in ("KEEP_MC2_E", "KEEP_SIMPLER_ARM_B",
                                   "KEEP_SIMPLER_ARM_C",
                                   "KEEP_SIMPLER_ARM_D", "RETAIN_R3")
