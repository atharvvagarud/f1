"""V3.2D deterministic diagnostics generator (development-only, no 2025).

Order is the preregistration gate: the script writes
``results/v3/v3_2d/preregistration.json`` FIRST, verifies its hash, and
only then runs comparative diagnostics. Any hash mismatch aborts before
scoring (Part G).

Temporal policy: fold evaluating Y uses R3 parameters through Y-1 and
MC2 quantities estimated strictly before Y. 2025 is never read.

Bounded development sample (NOT the V3.2E backtest): 5 parity-corpus
checkpoints (one per eval season 2020-2024, deterministic pick) x paired
arms A(R3 frozen) vs B-E (MC2 kernel). Purpose: detect broken mechanisms
only.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "v3" / "v3_2d"
OUT.mkdir(parents=True, exist_ok=True)

SEED = 20240101  # R7 master seed
N_RUNS_DEV = 200
CONVERGENCE_COUNTS = (100, 200, 500, 1000)

DRY_COMPOUNDS = ("SOFT", "MEDIUM", "HARD")


def _hash(obj: dict) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 1. Preregistration (written + verified BEFORE any comparative scoring).
# ---------------------------------------------------------------------------

def build_preregistration() -> dict:
    from raceintel.simulation.mc2.anchor import (
        ANCHOR_PRIMARY_WINDOW,
        ANCHOR_SHRINKAGE_K,
        ANCHOR_WINDOW_CANDIDATES,
    )
    from raceintel.simulation.mc2.contract import (
        CANDIDATE_ARMS,
        MC2_RESEARCH_VERSION,
        TEMPORAL_FOLDS,
        contract_identity,
    )
    from raceintel.simulation.mc2.dynamics import (
        DYNAMICS_DECAY_CANDIDATES,
        DYNAMICS_DRIFT_BOUND_S,
        DYNAMICS_HORIZON_LAPS,
        DYNAMICS_PRIMARY_DECAY,
    )
    from raceintel.simulation.mc2.kernel import kernel_identity
    from raceintel.simulation.mc2.traffic import (
        TRAFFIC_GATE_VERDICT,
        evaluate_gate,
    )
    from raceintel.simulation.mc2.variance import (
        VARIANCE_CEILING_S,
        VARIANCE_FLOOR_S,
        VARIANCE_HIERARCHY,
        VARIANCE_MIN_N,
    )
    prereg = {
        "schema_version": "v3.2d-prereg-v1",
        "research_version": MC2_RESEARCH_VERSION,
        "contract_identity": contract_identity(),
        "kernel_identity": kernel_identity(),
        "arms": list(CANDIDATE_ARMS),
        "ablation_order": ["A_R3_BASELINE", "B_DRIVER_ANCHOR",
                           "C_DRIVER_ANCHOR_PLUS_DYNAMICS",
                           "D_CONDITIONED_VARIANCE", "E_AR1_RESIDUAL"],
        "common_population": {
            "source": "results/v3/v3_2c_coverage.json",
            "eligible_checkpoints": 2305,
            "total_checkpoints": 9644,
            "state_contract": "mc2-field-v1",
            "presence_adapter": "v3.2c-presence-v1",
            "development_sample": "5 parity-corpus checkpoints, one per "
                                  "eval season 2020-2024 (deterministic)",
        },
        "temporal_folds": [
            {"fold": f["fold"], "train_through": f["train_through"],
             "evaluate": list(f["evaluate"])} for f in TEMPORAL_FOLDS
        ],
        "parameter_training_policy": "fold evaluating Y uses artifacts "
                                     "through Y-1 only; 2025 never read",
        "metrics": ["winner_total_variation_vs_A",
                    "expected_finish_mae_vs_A",
                    "invalid_rate", "coverage_parity",
                    "residual_variance_ratio", "runs_per_sec"],
        "acceptance_interpretation": "development diagnostics only; no "
                                     "KEEP/REJECT verdict in V3.2D (V3.2E)",
        "random_seeds": {"master_seed": SEED, "mc2_domain": "mc2-ar1",
                         "r3_streams": "unperturbed"},
        "simulation_counts": {"development": N_RUNS_DEV,
                              "convergence": list(CONVERGENCE_COUNTS)},
        "anchor": {"windows": list(ANCHOR_WINDOW_CANDIDATES),
                   "primary": ANCHOR_PRIMARY_WINDOW,
                   "shrinkage_k": ANCHOR_SHRINKAGE_K},
        "dynamics": {"decay_candidates": list(DYNAMICS_DECAY_CANDIDATES),
                     "primary_decay": DYNAMICS_PRIMARY_DECAY,
                     "drift_bound_s": DYNAMICS_DRIFT_BOUND_S,
                     "horizon_laps": DYNAMICS_HORIZON_LAPS},
        "variance": {"hierarchy": list(VARIANCE_HIERARCHY),
                     "min_n": dict(VARIANCE_MIN_N),
                     "floor_s": VARIANCE_FLOOR_S,
                     "ceiling_s": VARIANCE_CEILING_S},
        "ar1": {"reference_rho": 0.264, "bound": 0.8,
                "admission": "0.05 < rho_fold < 0.8, else arm E disabled"},
        "traffic_gate": {"verdict": TRAFFIC_GATE_VERDICT,
                         "reason": evaluate_gate().reason},
        "failure_policy": "numerical trajectory failures count as invalid; "
                          "never silently dropped or refilled",
    }
    prereg["prereg_hash"] = _hash({k: v for k, v in prereg.items()
                                   if k != "prereg_hash"})
    return prereg


def write_preregistration() -> dict:
    prereg = build_preregistration()
    (OUT / "preregistration.json").write_text(
        json.dumps(prereg, indent=1, sort_keys=True) + "\n",
        encoding="utf-8")
    return prereg


def verify_preregistration(expected_hash: str) -> dict:
    prereg = json.loads((OUT / "preregistration.json").read_text())
    actual = _hash({k: v for k, v in prereg.items() if k != "prereg_hash"})
    if actual != expected_hash or prereg.get("prereg_hash") != expected_hash:
        raise SystemExit("preregistration identity mismatch: aborting "
                         "before comparative scoring")
    return prereg


# ---------------------------------------------------------------------------
# 2. Causal history helpers (all inputs <= T; past-only by construction).
# ---------------------------------------------------------------------------

def _clean_history(df, t_s: float):
    """Past-only clean laps at T (R3-B spirit: accurate, kept, no pit,
    all_clear, lap>1, dry compound+age known, dry weather)."""
    hist = df[df["state_time_s"] <= t_s]
    mask = (
        (hist["is_accurate"].astype(str) == "True")
        & (hist["deleted"].astype(str) == "False")
        & hist["pit_in_s"].isna()
        & hist["pit_out_s"].isna()
        & (hist["track_state"] == "all_clear")
        & (hist["lap_number"] > 1)
        & hist["compound"].isin(list(DRY_COMPOUNDS))
        & hist["tyre_life"].notna()
        & (hist["wx_rainfall"] != True)  # noqa: E712
        & hist["lap_time_s"].notna()
    )
    return hist[mask].sort_values(["driver_id", "state_time_s"])


def _median(vals):
    s = sorted(vals)
    n = len(s)
    return float(s[n // 2]) if n % 2 else float((s[n // 2 - 1] + s[n // 2]) / 2)


def _slope_endpoint(devs: list, laps: list, horizon: int, width: int):
    """Endpoint-delta slope semantics (deviation-domain implementation of
    the frozen dyn_pace_slope contract: median(now) - median(anchor))."""
    if len(devs) < width + 1:
        return None
    n_lap = laps[-1]
    anchor_idx = [i for i, lp in enumerate(laps) if lp <= n_lap - horizon]
    if len(anchor_idx) < width:
        return None
    now = _median(devs[-width:])
    anc = _median([devs[i] for i in anchor_idx[-width:]])
    denom = max(1, n_lap - laps[anchor_idx[-width]])
    return (now - anc) / denom


# ---------------------------------------------------------------------------
# 3. Service / checkpoint loading (parity-corpus sample, eval seasons only).
# ---------------------------------------------------------------------------

_SERVICE_CACHE: dict = {}


def _service_for(race_id: str):
    if race_id in _SERVICE_CACHE:
        return _SERVICE_CACHE[race_id]
    import pandas as pd

    from raceintel.race_state.race_state_reconstruction import (
        RaceStateReconstructor,
    )
    from raceintel.replay import replay as RP
    from raceintel.replay.replay_reconstruction import ReplayReconstructor

    season = int(race_id[:4])
    base = ROOT / "data" / "v2" / "processed"
    states = pd.read_parquet(
        base / f"driver_lap_state_d9/season={season}/"
        f"driver_lap_state_d9__d9-{season}.parquet")
    states = states[states["race_id"] == race_id].copy()
    results = pd.read_parquet(
        base / f"results/season={season}/results__{race_id}.parquet")
    meta = {}
    rp = base / f"races/season={season}/races__{race_id}.parquet"
    if rp.exists():
        for row in pd.read_parquet(rp).itertuples():
            meta[str(row.race_id)] = {
                "scheduled_laps": (None if pd.isna(row.total_laps_scheduled)
                                   else int(row.total_laps_scheduled))}
    timeline = RP.build_replay_timeline(states)
    svc = ReplayReconstructor(
        timeline, RaceStateReconstructor(states, results,
                                         race_meta=meta or None))
    _SERVICE_CACHE[race_id] = (svc, states)
    return svc, states


def pick_checkpoints():
    corpus = json.loads(
        (ROOT / "results" / "v3" / "v3_2c_parity_corpus.json").read_text())
    by_season: dict[str, list] = {}
    for e in corpus["entries"]:
        if e["race_id"][:4] in ("2020", "2021", "2022", "2023", "2024"):
            by_season.setdefault(e["race_id"][:4], []).append(e)
    picks = []
    for season in ("2020", "2021", "2022", "2023", "2024"):
        # Deterministic: prefer MID (mechanisms engage on real history),
        # fallback EARLY. Prereg pins "one per eval season"; stage choice
        # is structural, never outcome-tuned.
        cands = sorted(by_season[season],
                       key=lambda e: (e["race_id"], e["frame_index"]))
        mid = [e for e in cands if e.get("stage") == "MID"]
        picks.append(mid[0] if mid else cands[0])
    return picks


# ---------------------------------------------------------------------------
# 4. MC2 parameter artifacts per fold (temporal-safe estimation).
# ---------------------------------------------------------------------------

def fold_through(season: int) -> int:
    s = int(season)
    if s in (2020, 2021):
        return 2019
    if s in (2022, 2023):
        return 2021
    if s == 2024:
        return 2023
    raise ValueError(f"season {season} outside V3.2D development folds")


def build_fold_parameters(folds_seasons=(2019, 2021, 2023)) -> dict:
    from raceintel.simulation.mc2.anchor import ANCHOR_SHRINKAGE_K
    from raceintel.simulation.mc2.dynamics import (
        DYNAMICS_DRIFT_BOUND_S,
        DYNAMICS_HORIZON_LAPS,
        DYNAMICS_PRIMARY_DECAY,
    )
    from raceintel.simulation.mc2.parameters import make_artifact
    from raceintel.simulation.mc2.residuals import RHO_REFERENCE
    from raceintel.simulation.mc2.variance import (
        VARIANCE_CEILING_S,
        VARIANCE_FLOOR_S,
        VARIANCE_HIERARCHY,
        VARIANCE_MIN_N,
    )
    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )

    artifacts = {}
    for through in folds_seasons:
        params = load_simulation_parameters(parameter_storage_dir(ROOT, through))
        resid = params.family("lap_residual_distribution_s")
        var_values = {}
        for key in ("2018-2021", "2022-2024", "global"):
            entry = resid.entries.get(key)
            if entry is None:
                continue
            if entry.std is not None and entry.std > 0:
                sigma = float(entry.std)
            else:
                qs = list(entry.quantile_values)
                if len(qs) >= 6:
                    sigma = (qs[-2] - qs[1]) / 2.563  # robust IQR-ish
                else:
                    sigma = 1.5
            var_values[key] = {"std_s": sigma, "n": entry.sample_count,
                               "support": [entry.observed_min,
                                           entry.observed_max]}
        artifacts[f"through-{through}"] = {
            "anchor": make_artifact(
                parameter_family="driver_anchor",
                train_through_season=through,
                conditioning=["driver|circuit", "constructor|season",
                              "circuit|era", "global"],
                min_n={"driver_window": 1, "shrinkage_k": ANCHOR_SHRINKAGE_K},
                fallback={"thin": "shrink toward 0",
                          "none": "offset 0.0 (R3 expectation)"},
                estimator_config={"windows": [3, 5, 8], "primary": 5,
                                  "median": True, "clip_s": 3.0},
                values={"shrinkage_k": ANCHOR_SHRINKAGE_K,
                        "primary_window": 5}),
            "dynamics": make_artifact(
                parameter_family="pace_dynamics",
                train_through_season=through,
                conditioning=["driver past-only endpoint delta"],
                min_n={"slope_points": 2},
                fallback={"missing_slope": "zero drift contribution"},
                estimator_config={"decay": DYNAMICS_PRIMARY_DECAY,
                                  "bound_s": DYNAMICS_DRIFT_BOUND_S,
                                  "horizon_laps": DYNAMICS_HORIZON_LAPS,
                                  "admitted": ["dyn_pace_slope_l3",
                                               "dyn_pace_slope_l10"]},
                values={"decay": DYNAMICS_PRIMARY_DECAY,
                        "drift_bound_s": DYNAMICS_DRIFT_BOUND_S}),
            "variance": make_artifact(
                parameter_family="residual_variance",
                train_through_season=through,
                conditioning=list(VARIANCE_HIERARCHY),
                min_n=dict(VARIANCE_MIN_N),
                fallback={"circuit|era": "fall back to era (V3.2D: "
                                         "per-circuit support inadequate)",
                          "all_missing": "documented R3 1.5 s scale"},
                estimator_config={"source": "R3 residual family std",
                                  "floor_s": VARIANCE_FLOOR_S,
                                  "ceiling_s": VARIANCE_CEILING_S},
                values=var_values),
            "ar1": make_artifact(
                parameter_family="residual_ar1",
                train_through_season=through,
                conditioning=["own-driver previous residual only"],
                min_n={"lag1_pairs": 500},
                fallback={"unstable": "rho=0 (independent draws)",
                          "reference": RHO_REFERENCE},
                estimator_config={"estimator": "causal trailing-median "
                                               "lag-1 pearson",
                                  "bound": 0.8},
                values={"rho_reference": RHO_REFERENCE}),
        }
    return artifacts


# ---------------------------------------------------------------------------
# 5. Bounded causal lag-1 re-estimation per fold (past-only quantities).
# ---------------------------------------------------------------------------

def estimate_lag1(race_ids: list) -> dict:
    import pandas as pd

    prev_all: list[float] = []
    curr_all: list[float] = []
    n_pairs = 0
    for race_id in sorted(race_ids):
        season = int(race_id[:4])
        base = ROOT / "data" / "v2" / "processed"
        df = pd.read_parquet(
            base / f"driver_lap_state_d9/season={season}/"
            f"driver_lap_state_d9__d9-{season}.parquet",
            columns=["race_id", "driver_id", "lap_number", "lap_time_s",
                     "state_time_s", "is_accurate", "deleted", "pit_in_s",
                     "pit_out_s", "track_state", "compound", "tyre_life",
                     "wx_rainfall"])
        df = df[df["race_id"] == race_id]
        clean = _clean_history(df, float(df["state_time_s"].max()))
        for _, g in clean.groupby("driver_id"):
            times = [float(v) for v in g["lap_time_s"].tolist()]
            resids = []
            for i, t in enumerate(times):
                window = times[max(0, i - 5):i]
                if len(window) < 2:
                    resids.append(None)
                else:
                    resids.append(t - _median(window))
            for a, b in zip(resids, resids[1:]):
                if a is not None and b is not None:
                    prev_all.append(a)
                    curr_all.append(b)
                    n_pairs += 1
    if n_pairs < 10:
        return {"rho": None, "n_pairs": n_pairs, "stable": False}
    import statistics

    mp = statistics.fmean(prev_all)
    mc = statistics.fmean(curr_all)
    cov = sum((a - mp) * (b - mc) for a, b in zip(prev_all, curr_all))
    vp = sum((a - mp) ** 2 for a in prev_all)
    vc = sum((b - mc) ** 2 for b in curr_all)
    rho = cov / (vp * vc) ** 0.5 if vp > 0 and vc > 0 else 0.0
    return {"rho": rho, "n_pairs": n_pairs,
            "stable": bool(0.05 < abs(rho) < 0.8)}


def estimation_races(through: int, k: int = 4) -> list:
    """Deterministic bounded estimation sample: every kth race <= through."""
    import pandas as pd

    races = []
    for season in range(2018, through + 1):
        df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "results" / f"season={season}",
            columns=["race_id"]).drop_duplicates()
        races.extend(sorted(df["race_id"].astype(str).tolist()))
    return races[::max(1, len(races) // k)][:k]


# ---------------------------------------------------------------------------
# 6. Paired development comparison on the bounded checkpoint sample.
# ---------------------------------------------------------------------------

def checkpoint_mechanisms(race_id, frame_index, params):
    from raceintel.simulation.adapter import from_race_state
    from raceintel.simulation.engine import (
        expected_lap_time_s,
        select_pace_parameters,
    )
    from raceintel.simulation.mc2.anchor import PastLap, compute_anchor
    from raceintel.simulation.mc2.kernel import DriverMechanism
    from raceintel.simulation.monte_carlo import select_residual_sampler

    svc, states = _service_for(race_id)
    race_state = svc.state_at(frame_index)
    sim_state = from_race_state(race_state)
    selection = select_pace_parameters(sim_state, params)
    sampler = select_residual_sampler(params, selection.era)
    t_s = float(race_state.state_time_s)
    df = states[states["race_id"] == race_id]
    clean = _clean_history(df, t_s)
    # Contemporary progress reference per historical lap: leader laps done
    # at that lap's own time (causal cummax, all inputs <= row time <= T).
    # Using T's reference for past laps would inject the race-progress
    # trend into every deviation as a systematic bias.
    import dataclasses

    timeline = df.sort_values("state_time_s")
    timeline = timeline.assign(
        _ref=timeline["lap_number"].fillna(0).astype(int).cummax())
    ref_by_time = dict(zip(timeline["state_time_s"].astype(float).tolist(),
                           timeline["_ref"].tolist()))
    anchor_age = {d.driver_id: int(d.tyre_age) for d in sim_state.drivers}
    mechanisms: dict[str, DriverMechanism] = {}
    diag = {"n_clean": {}, "fallback": {}, "slope_l3": {}, "slope_l10": {}}
    for d in sim_state.drivers:
        g = clean[clean["driver_id"] == d.driver_id]
        laps, devs = [], []
        base = (selection.base.value
                + selection.offset_for(d.constructor_id).value)
        for row in g.itertuples():
            row_ref = int(ref_by_time.get(float(row.state_time_s),
                                          selection.reference_lap))
            sel = dataclasses.replace(selection, reference_lap=row_ref)
            mu, _, _ = expected_lap_time_s(
                sel, base, int(row.lap_number), float(row.tyre_life),
                anchor_age[d.driver_id])
            laps.append(int(row.lap_number))
            devs.append(float(row.lap_time_s) - mu)
        past = [PastLap(lap_time_s=dev + 0.0, expected_s=0.0,
                        lap_number=lp) for dev, lp in zip(devs[-8:], laps[-8:])]
        # PastLap stores (time, expectation) separately; deviations above
        # are already mu-relative, so expectation is 0 by construction.
        anchor = compute_anchor(past)
        s3 = _slope_endpoint(devs, laps, 3, 3)
        s10 = _slope_endpoint(devs, laps, 10, 5)
        mechanisms[d.driver_id] = DriverMechanism(
            anchor_offset_s=anchor.offset_s, slope_l3=s3, slope_l10=s10)
        diag["n_clean"][d.driver_id] = anchor.n_clean
        diag["fallback"][d.driver_id] = anchor.fallback
        diag["slope_l3"][d.driver_id] = s3
        diag["slope_l10"][d.driver_id] = s10
    return sim_state, selection, sampler, mechanisms, diag


def run_development_comparison(picks: list, fold_params: dict) -> tuple:
    from raceintel.simulation.config import SimulationConfig
    from raceintel.simulation.engine import ExecutionPolicy
    from raceintel.simulation.monte_carlo import MonteCarloEngine
    from raceintel.simulation.config import Assumptions

    results = []
    timings: dict[str, list] = {}
    for pick in picks:
        race_id, frame = pick["race_id"], pick["frame_index"]
        params = fold_params[fold_through(int(race_id[:4]))]
        sim_state, selection, sampler, mechanisms, diag = \
            checkpoint_mechanisms(race_id, frame, params)

        t0 = time.perf_counter()
        arm_a = MonteCarloEngine(chunk_size=512).run(
            sim_state, params,
            SimulationConfig(simulation_count=N_RUNS_DEV,
                             master_seed=SEED, pit_dynamics_enabled=False),
            Assumptions(),
            execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
        timings.setdefault("A_R3_BASELINE", []).append(
            time.perf_counter() - t0)
        a_freq = {s.driver_id: s.win_probability
                  for s in arm_a.driver_summaries}
        a_exp = {s.driver_id: s.expected_finish
                 for s in arm_a.driver_summaries}

        from raceintel.simulation.mc2.kernel import run_mc2
        from raceintel.simulation.mc2.variance import (
            RegimeStat,
            select_variance,
        )

        entry = {"race_id": race_id, "frame_index": frame,
                 "roster": sorted(mechanisms),
                 "arm_a": {"valid": arm_a.valid_simulation_count,
                           "invalid": arm_a.invalid_simulation_count,
                           "winner_frequency": a_freq},
                 "anchor_diag": {
                     "n_clean": diag["n_clean"],
                     "fallback": diag["fallback"]},
                 "arms": {}}
        era = selection.era
        resid = params.family("lap_residual_distribution_s")
        emp_std = None
        for key in (era, "global"):
            e = resid.entries.get(key)
            if e is not None and e.std:
                emp_std = float(e.std)
                break
        for arm in ("B_DRIVER_ANCHOR", "C_DRIVER_ANCHOR_PLUS_DYNAMICS",
                    "D_CONDITIONED_VARIANCE", "E_AR1_RESIDUAL"):
            mechs = {}
            for did, m in mechanisms.items():
                from dataclasses import replace

                std = m.regime_std_s
                rho = 0.0
                ar1 = False
                if arm in ("D_CONDITIONED_VARIANCE", "E_AR1_RESIDUAL"):
                    era_entry = resid.entries.get(era)
                    g_entry = resid.entries.get("global")
                    sel = select_variance({
                        "era": RegimeStat(
                            float(era_entry.std or 1.5),
                            era_entry.sample_count)
                        if era_entry and era_entry.std else None,
                        "global": RegimeStat(
                            float(g_entry.std or 1.5),
                            g_entry.sample_count)
                        if g_entry and g_entry.std else None,
                    })
                    std = sel.std_s
                if arm == "E_AR1_RESIDUAL":
                    rho = 0.264
                    ar1 = True
                mechs[did] = replace(m, regime_std_s=std, rho=rho,
                                     ar1_enabled=ar1)
            t0 = time.perf_counter()
            out = run_mc2(sim_state, selection, sampler, mechs, arm=arm,
                          master_seed=SEED,
                          simulation_count=N_RUNS_DEV,
                          empirical_std_s=emp_std)
            timings.setdefault(arm, []).append(time.perf_counter() - t0)
            roster = entry["roster"]
            tv = 0.5 * sum(abs(out["winner_frequency"].get(d, 0.0)
                               - a_freq.get(d, 0.0)) for d in roster)
            mae = (sum(abs(out["expected_finish"][d] - a_exp.get(d, 0.0))
                       for d in roster) / len(roster)) if a_exp else None
            entry["arms"][arm] = {
                "valid": out["valid"], "invalid": out["invalid"],
                "winner_frequency": out["winner_frequency"],
                "expected_finish": out["expected_finish"],
                "winner_tv_vs_A": tv, "expected_finish_mae_vs_A": mae}
        results.append(entry)
    return results, timings


def main() -> None:
    # Gate: preregister first, verify identity, then score.
    prereg = write_preregistration()
    prereg = verify_preregistration(prereg["prereg_hash"])
    print(f"preregistration {prereg['prereg_hash'][:12]} verified", flush=True)

    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )

    fold_params = {t: load_simulation_parameters(parameter_storage_dir(ROOT, t))
                   for t in (2019, 2021, 2023)}
    artifacts = build_fold_parameters()
    for name, fams in artifacts.items():
        for fam, art in fams.items():
            (OUT / f"mc2_params_{name}_{fam}.json").write_text(
                json.dumps(art, indent=1, sort_keys=True) + "\n")
    print("parameter artifacts written", flush=True)

    # Temporal lag-1 re-estimates (estimation data strictly before Y).
    lag = {"D1": estimate_lag1(estimation_races(2019)),
           "D2": estimate_lag1(estimation_races(2021)),
           "D3": estimate_lag1(estimation_races(2023))}
    ar1_admitted = all(v.get("stable", False) for v in lag.values())
    print(f"lag-1 {lag} admitted={ar1_admitted}", flush=True)

    # Bounded paired development comparison.
    picks = pick_checkpoints()
    ablation, timings = run_development_comparison(picks, fold_params)

    # Parameter diagnostics from the bounded sample + artifact stats.
    n_clean_all, fallbacks = [], {}
    for entry in ablation:
        for did, n in entry["anchor_diag"]["n_clean"].items():
            n_clean_all.append(n)
        for did, fb in entry["anchor_diag"]["fallback"].items():
            fallbacks[fb] = fallbacks.get(fb, 0) + 1
    resid_stats = {}
    for through, params in fold_params.items():
        fam = params.family("lap_residual_distribution_s").to_dict()
        resid_stats[f"through-{through}"] = {
            k: {"n": v["sample_count"], "std": v["std"],
                "min": v["observed_min"], "max": v["observed_max"]}
            for k, v in fam["entries"].items()}
    (OUT / "parameter_diagnostics.json").write_text(json.dumps({
        "schema_version": "v3.2d-param-diag-v1",
        "prereg_hash": prereg["prereg_hash"],
        "anchor": {"n_clean_values": sorted(n_clean_all),
                   "fallback_counts": fallbacks},
        "residual_families": resid_stats,
        "lag1": lag, "ar1_admitted": ar1_admitted,
        "variance_fallback": "circuit|era unsupported in V3.2D "
                             "(100% era fallback by design)",
        "traffic": {"verdict": "NOT_RUN"},
    }, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    (OUT / "ablation_results.json").write_text(json.dumps({
        "schema_version": "v3.2d-ablation-v1",
        "prereg_hash": prereg["prereg_hash"],
        "scope": "development-only bounded sample (5 checkpoints); "
                 "no KEEP/REJECT verdict (V3.2E owns the backtest)",
        "n_runs": N_RUNS_DEV, "master_seed": SEED,
        "checkpoints": ablation,
    }, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    # Convergence on the first checkpoint (selected-arm E).
    first = picks[0]
    params = fold_params[fold_through(int(first["race_id"][:4]))]
    sim_state, selection, sampler, mechanisms, _ = checkpoint_mechanisms(
        first["race_id"], first["frame_index"], params)
    from dataclasses import replace

    from raceintel.simulation.mc2.kernel import run_mc2

    mechs = {did: replace(m, rho=0.264, ar1_enabled=True)
             for did, m in mechanisms.items()}
    resid = params.family("lap_residual_distribution_s")
    emp_std = next((float(resid.entries[k].std)
                    for k in (selection.era, "global")
                    if resid.entries.get(k) and resid.entries[k].std), 1.5)
    conv = []
    ref = None
    for n in CONVERGENCE_COUNTS:
        t0 = time.perf_counter()
        out = run_mc2(sim_state, selection, sampler, mechs,
                      arm="E_AR1_RESIDUAL", master_seed=SEED,
                      simulation_count=n, empirical_std_s=emp_std)
        dt = time.perf_counter() - t0
        conv.append({"n_runs": n, "valid": out["valid"],
                     "invalid": out["invalid"],
                     "winner_frequency": out["winner_frequency"],
                     "seconds": dt})
        ref = out
    base = conv[-1]["winner_frequency"]
    for row in conv:
        row["winner_tv_vs_n1000"] = 0.5 * sum(
            abs(row["winner_frequency"].get(d, 0.0) - base.get(d, 0.0))
            for d in set(row["winner_frequency"]) | set(base))
    (OUT / "convergence.json").write_text(json.dumps({
        "schema_version": "v3.2d-convergence-v1",
        "prereg_hash": prereg["prereg_hash"],
        "checkpoint": first, "arm": "E_AR1_RESIDUAL",
        "counts": conv,
    }, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    # Performance: measured runs/sec per arm + catalogue extrapolation.
    perf_arms = {}
    for arm, dts in timings.items():
        total_runs = N_RUNS_DEV * len(dts)
        total_s = sum(dts)
        perf_arms[arm] = {"checkpoints": len(dts),
                          "seconds_total": total_s,
                          "runs_per_sec": total_runs / total_s if total_s else 0}
    rps_e = perf_arms.get("E_AR1_RESIDUAL", {}).get("runs_per_sec", 0)
    runtime = {}
    if rps_e:
        for n in (1000, 5000, 10000):
            serial_h = 2305 * n / rps_e / 3600
            runtime[f"n{n}"] = {"serial_hours": serial_h,
                                "parallel_8w_hours": serial_h / 8}
    (OUT / "performance.json").write_text(json.dumps({
        "schema_version": "v3.2d-performance-v1",
        "prereg_hash": prereg["prereg_hash"],
        "arms": perf_arms, "eligible_states": 2305,
        "catalogue_estimate": runtime,
    }, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    # Selection for V3.2E (mechanistic justification, development evidence).
    mean_tv = {}
    for arm in ("B_DRIVER_ANCHOR", "C_DRIVER_ANCHOR_PLUS_DYNAMICS",
                "D_CONDITIONED_VARIANCE", "E_AR1_RESIDUAL"):
        tvs = [e["arms"][arm]["winner_tv_vs_A"] for e in ablation]
        mean_tv[arm] = sum(tvs) / len(tvs)
    invalid_e = sum(e["arms"]["E_AR1_RESIDUAL"]["invalid"] for e in ablation)
    if ar1_admitted and invalid_e == 0:
        selected = "ADVANCE_E"
    elif invalid_e == 0:
        selected = "ADVANCE_D"
    else:
        selected = "ADVANCE_NONE"
    (OUT / "selected_candidate.json").write_text(json.dumps({
        "schema_version": "v3.2d-selection-v1",
        "prereg_hash": prereg["prereg_hash"],
        "mean_winner_tv_vs_A": mean_tv,
        "ar1_admitted": ar1_admitted,
        "selected": selected,
        "traffic": "NOT_RUN",
        "justification": "most complete stable mechanism chain; final "
                         "verdict deferred to the V3.2E controlled backtest",
    }, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"selected={selected}", flush=True)


if __name__ == "__main__":
    main()
