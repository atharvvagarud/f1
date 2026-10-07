"""Freeze the V3.2E evaluation plan (no outcome scoring here).

Writes results/v3/v3_2e/preregistration.json with a content hash.
Candidate E's scientific parameters are inherited frozen from V3.2D;
this plan refines evaluation mechanics only.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "v3" / "v3_2e"
OUT.mkdir(parents=True, exist_ok=True)


def _hash(obj: dict) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


PREREG = {
    "schema_version": "v3.2e-prereg-v1",
    "v3_2d_prereg": "dc0ae2dbade08514ed3b7cbf5e4be965edccf40b60d7bcad86c99f245854ee16",
    "candidate": {
        "arm": "E_AR1_RESIDUAL",
        "research_version": "mc2-r1-research",
        "kernel": "mc2-kernel-v1",
        "rng": "mc2-rng-v1",
        "contract": "25b35762c4f175dc04416a06f9b5162e98f4194bf7e3b9b04027caea04837953",
        "params_frozen": True,
    },
    "population": {
        "rule": "V3.2C-eligible under FOLD parameters (through Y-1) in eval seasons with truth available (results parquet present, factual winner in active roster)",
        "eval_seasons": [2020, 2021, 2022, 2023, 2024],
        "stage_rule": "leader fraction thirds (EARLY<1/3, MID<2/3, else LATE)",
        "arms_share_exact": True,
    },
    "temporal_folds": [
        {"fold": "D1", "train_through": 2019, "evaluate": [2020, 2021]},
        {"fold": "D2", "train_through": 2021, "evaluate": [2022, 2023]},
        {"fold": "D3", "train_through": 2023, "evaluate": [2024]},
    ],
    "arms": ["A_R3_BASELINE", "B_DRIVER_ANCHOR",
             "C_DRIVER_ANCHOR_PLUS_DYNAMICS", "D_CONDITIONED_VARIANCE",
             "E_AR1_RESIDUAL"],
    "n_runs": {
        "primary": 1000,
        "escalation": 2000,
        "pilot": "6 checkpoints (EARLY/MID/LATE x 2 seasons, deterministic), arm E seeds S/S+1, mean winner-TV between repeats < 0.05 else escalate whole backtest to 2000; pilot inspects no truth",
        "identical_across_arms": True,
    },
    "seeds": {
        "master_seed": 20240101,
        "design": "paired-by-checkpoint (same states, same n, same master seed); cross-arm CRN not applicable (R3 internal streams vs MC2 mc2-ar1 domain are distinct stochastic processes; R3 engine accepts no external pool and must not be modified)",
        "bootstrap_seed": 42,
    },
    "truth_policy": {
        "winner": "winner_flag",
        "podium": "podium_flag",
        "order": "classified_position non-null intersect roster (DNFs excluded from order metrics; no favourable DNF treatment)",
        "separation": "truth loaded from results parquet only after simulation outputs are frozen per checkpoint; evaluation module imports no simulation state",
    },
    "primary_metric": {
        "name": "race-macro winner log-loss difference (A minus E)",
        "checkpoint": "R7 winner_log_loss with predeclared epsilon 1e-6",
        "race_macro": "mean over evaluated checkpoints in race",
        "overall": "mean over races of race-macro A-minus-E (positive favors E)",
        "uncertainty": "race-level paired bootstrap B=2000 seed 42, 95% percentile CI",
    },
    "secondary_metrics": [
        "winner Brier difference (race-macro, A-minus-E)",
        "podium Brier difference (mean (p-y)^2 over roster, race-macro, A-minus-E)",
        "expected-finish MAE difference (R7, classified drivers, race-macro, A-minus-E)",
        "mean RPS difference (R7 normalized, classified drivers, race-macro, A-minus-E)",
        "winner ECE (R7 bins, descriptive, no independence claims)",
        "top-1 / top-3 winner accuracy difference (diagnostic only)",
    ],
    "non_degradation_margins": {
        "brier_ci_low": -0.005,
        "mae_ci_low_laps": -0.05,
        "podium_brier_ci_low": -0.005,
        "invalid_rate_max": 0.01,
        "invalid_rate_vs_A_pp": 0.005,
        "fold_degradation_ci_high": -0.05,
        "fold_neutral_point": -0.01,
    },
    "decision_logic": {
        "KEEP_MC2_E": "primary CI low > 0 AND all non-degradation margins hold AND coverage exact AND temporal coherence (>=2 folds point>=fold_neutral_point, no fold CI high<fold_degradation)",
        "KEEP_SIMPLER": "E fails but simplest of B/C/D meeting the same bar passes (checked B, then C, then D)",
        "RETAIN_R3": "no arm meets the bar and no BLOCK condition",
        "BLOCK": "population mismatch, R3 regression, temporal violation, firewall failure",
    },
    "run_count_criterion": "TV<=0.005 (V3.2A convention) on verdict arm across EARLY/MID/LATE x seasons at 100/500/1000/5000(/10000); recommend smallest passing n among {1000,5000,10000} else DEFER",
    "forbidden": ["2025 reads", "model training", "serving promotion", "wet/neutralisation/traffic/DNF models", "post-result tuning", "demo cache", "frontend", "commit/tag/push", "V3.2F work"],
}


def main() -> None:
    prereg = dict(PREREG)
    prereg["prereg_hash"] = _hash(
        {k: v for k, v in prereg.items() if k != "prereg_hash"})
    (OUT / "preregistration.json").write_text(
        json.dumps(prereg, indent=1, sort_keys=True) + "\n",
        encoding="utf-8")
    print("V3.2E preregistration", prereg["prereg_hash"])


if __name__ == "__main__":
    main()
