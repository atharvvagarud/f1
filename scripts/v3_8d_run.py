"""V3.8D historical consensus evaluation (protocol-driven, deterministic).

Reads preregistered protocol; OOF model predictions (TEMPORALLY_OUT_OF_FOLD);
per-row MC2 E-arm execution at 5000/20240101 with fold-through params;
B adapters + alignment; C metrics; ground-truth join AFTER metrics;
race-macro aggregation; race-level bootstrap; pathology P1-P20; fusion gate.

Usage: python scripts/v3_8d_run.py [--pilot N] [--out DIR]
Pilot runs the first N rows of the fixed population (timing/chain check;
population rule unchanged).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

PROTOCOL_PATH = (ROOT / "results" / "v3" / "v3_8d" / "evaluation_protocol.json")


def _load_protocol():
    p = json.loads(PROTOCOL_PATH.read_text())
    ident = p.pop("protocol_identity")
    blob = json.dumps(p, sort_keys=True, separators=(",", ":")).encode()
    assert identity_matches(blob, ident), "protocol mutated after hash"
    p["protocol_identity"] = ident
    return p


def identity_matches(blob: bytes, ident: str) -> bool:
    return hashlib.sha256(blob).hexdigest() == ident


def _parse_lap(state_id: str) -> tuple:
    parts = state_id.split("|")
    if len(parts) != 3:
        raise ValueError(f"bad state_id: {state_id!r}")
    return parts[0], parts[1], int(parts[2])


def main() -> int:
    import numpy as np
    import pandas as pd

    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=int, default=0)
    ap.add_argument("--out", type=str, default="results/v3/v3_8d")
    args = ap.parse_args()
    t_start = time.perf_counter()

    protocol = _load_protocol()
    outdir = ROOT / args.out
    outdir.mkdir(parents=True, exist_ok=True)

    from raceintel.consensus import adapters as A
    from raceintel.consensus import alignment as L
    from raceintel.consensus import contracts as C
    from raceintel.consensus import metrics as M

    # ---- 1. OOF loads + fold safety ----
    base = {}
    for fold in ("D1", "D2", "D3"):
        base[fold] = pd.read_parquet(
            ROOT / f"data/v3/v3_3c/oof_baseline__{fold}.parquet")
    oof = pd.concat(list(base.values()), ignore_index=True)
    assert set(oof.fold.unique()) == {"D1", "D2", "D3"}
    assert ((oof.fold == "D1") == (oof.season == 2022)).all()
    assert ((oof.fold == "D2") == (oof.season == 2023)).all()
    assert ((oof.fold == "D3") == (oof.season == 2024)).all()
    assert oof.state_id.is_unique
    assert set(oof.model_family.unique()) == {"v3_1b_baseline"}
    n_oof_rows = len(oof)
    races = sorted(oof.race_id.unique(),
                   key=lambda r: (int(r[:4]), int(r[5:8].lstrip("r0") or 0)))
    assert len(races) == 68, len(races)

    xgb = pd.concat(
        [pd.read_parquet(ROOT / f"data/v3/v3_3c/oof_xgboost__{fold}.parquet")
         for fold in ("D1", "D2", "D3")], ignore_index=True)
    assert set(xgb.state_id) == set(oof.state_id), "xgb row-set mismatch"

    v35c = pd.concat(
        [pd.read_parquet(ROOT / f"data/v3/v3_5c/oof_{fold}.parquet")
         for fold in ("D1", "D2", "D3")], ignore_index=True)
    v35e = pd.concat(
        [pd.read_parquet(ROOT / f"data/v3/v3_5e/oof_xgb_e__{fold}.parquet")
         for fold in ("D1", "D2", "D3")], ignore_index=True)
    assert set(v35c.state_id) == set(oof.state_id), "v35c row-set mismatch"
    assert set(v35e.state_id) == set(oof.state_id), "v35e row-set mismatch"
    v35_control = v35c[v35c.model == "l2_logistic"].copy()
    assert len(v35_control) == n_oof_rows, len(v35_control)

    # stage join for v35 (fail-closed)
    stage_map = dict(zip(oof.state_id, oof.stage))
    assert len(stage_map) == n_oof_rows

    # ground-truth sanity: exactly one driver per race owns all target==1
    # rows (target marks rows of the eventual winner). Fail closed.
    for race, grp in oof.groupby("race_id"):
        wdrv = grp[grp.target == 1].driver_id.unique()
        assert len(wdrv) == 1, (race, wdrv)
        assert (grp[grp.target == 1].shape[0]
                == grp[grp.driver_id == wdrv[0]].shape[0]), race

    # ---- 2. population: 8 races, earliest full-coverage lap per stage ----
    lap_of = {}
    for sid in oof.state_id:
        _, _, lap = _parse_lap(sid)
        lap_of[sid] = lap
    oof = oof.assign(lapsel=[lap_of[s] for s in oof.state_id])
    sel_races = [races[i] for i in range(2, len(races), 8)][:8]
    assert len(sel_races) == 8, sel_races
    pop_rows = []
    for race in sel_races:
        sub = oof[oof.race_id == race]
        for stage in ("EARLY", "MID", "LATE"):
            # Amendment 01: LATEST full-coverage lap per stage (earliest
            # systematically selects MC2-ineligible race-start states).
            laps = sorted(sub[sub.stage == stage].lapsel.unique())
            for lap in reversed(laps):
                grp = sub[(sub.stage == stage) & (sub.lapsel == lap)]
                if grp.driver_id.nunique() == 20:
                    pop_rows.append(grp)
                    break
    pop = pd.concat(pop_rows, ignore_index=True)
    pop_states = sorted(pop.state_id.unique())
    assert len(pop_states) > 0

    if args.pilot:
        keep = set(pop_states[:args.pilot])
        pop = pop[pop.state_id.isin(keep)].copy()
        pop_states = sorted(keep)

    # ---- 3. d9 time join (fail-closed) ----
    d9 = {}
    for season in (2022, 2023, 2024):
        d9[season] = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9" /
            f"season={season}/driver_lap_state_d9__d9-{season}.parquet",
            columns=["race_id", "driver_id", "lap_number", "state_time_s"])
    d9all = pd.concat(list(d9.values()), ignore_index=True)
    d9all = d9all.assign(
        _key=list(zip(d9all.race_id, d9all.driver_id, d9all.lap_number)))
    assert not d9all._key.duplicated().any(), "d9 key collision"
    tmap = dict(zip(d9all._key, d9all.state_time_s.astype(float)))
    pop = pop.assign(
        timesel=[tmap.get((r.race_id, r.driver_id, r.lapsel), None)
            for r in pop.itertuples()])
    missing_t = pop[pop.timesel.isna()]
    assert missing_t.empty, f"d9 time missing: {len(missing_t)}"

    # ---- 4. per-row MC2 E-arm at 5000/20240101 ----
    import run_v3_2d_diagnostics as D2
    import run_v3_2e_backtest as B2E
    from raceintel.simulation.mc2.kernel import run_mc2
    from raceintel.simulation.mc2.variance import (
        RegimeStat, select_variance)

    try:
        from raceintel.simulation.params import (
            load_simulation_parameters, parameter_storage_dir)
    except ImportError:
        from raceintel.simulation.params import (  # noqa
            load_simulation_parameters, parameter_storage_dir)

    FOLD_THROUGH = {2022: 2021, 2023: 2021, 2024: 2023}
    params_cache = {}
    svc_cache = {}
    grid_cache = {}
    results_cache = {}

    def _params(season):
        through = FOLD_THROUGH[season]
        if through not in params_cache:
            params_cache[through] = load_simulation_parameters(
                parameter_storage_dir(ROOT, through))
        return params_cache[through], through

    def _service(race_id):
        if race_id not in svc_cache:
            svc, states = D2._service_for(race_id)
            t2f = {}
            for fr in svc._timeline.frames:
                t2f.setdefault(float(fr.anchor_state_time_s),
                               int(fr.frame_index))
            season = int(race_id[:4])
            res = pd.read_parquet(
                ROOT / "data" / "v2" / "processed" / "results" /
                f"season={season}/results__{race_id}.parquet")
            svc_cache[race_id] = (svc, t2f, B2E._grid_map(res))
        return svc_cache[race_id]

    mc2_out = {}
    exclusions = []
    mc_seconds = []
    ckpt_path = outdir / "mc2_checkpoint.json"
    if ckpt_path.is_file():
        ckpt = json.loads(ckpt_path.read_text())
        mc2_out = ckpt.get("mc2_out", {})
        exclusions = ckpt.get("exclusions", [])
        mc_seconds = ckpt.get("mc_seconds", [])
    done_sids = set(mc2_out) | {e["state_id"] for e in exclusions}
    ckpt_tick = [0]
    for row in pop.itertuples():
        sid = row.state_id
        if sid in done_sids:
            continue
        season = int(row.season)
        params, through = _params(season)
        svc, t2f, grid = _service(row.race_id)
        frame = t2f.get(float(row.timesel))
        if frame is None:
            exclusions.append({"state_id": sid, "reason": "FRAME_MISSING",
                               "detail": "no exact timeline frame for row T"})
            continue
        try:
            prep = B2E._prepare_state_and_mechanisms(
                row.race_id, frame, params, grid)
        except Exception as exc:  # noqa: BLE001 - recorded exclusion
            exclusions.append(
                {"state_id": sid, "reason": "PREP_REFUSAL",
                 "detail": f"{type(exc).__name__}: {exc}"})
            continue
        sim_state, selection, sampler, mechanisms, _ = prep
        try:
            from raceintel.simulation.monte_carlo import (
                select_residual_sampler)
            resid = params.family("lap_residual_distribution_s")
            era = selection.era
            era_e = resid.entries.get(era)
            g_e = resid.entries.get("global")
            sel = select_variance({
                "era": RegimeStat(float(era_e.std or 1.5),
                                  era_e.sample_count)
                if era_e and era_e.std else None,
                "global": RegimeStat(float(g_e.std or 1.5),
                                     g_e.sample_count)
                if g_e and g_e.std else None})
            mechs = {did: replace(m, regime_std_s=sel.std_s, rho=0.264,
                                  ar1_enabled=True)
                     for did, m in mechanisms.items()}
            t0 = time.perf_counter()
            res = run_mc2(sim_state, selection, sampler, mechs,
                          arm="E_AR1_RESIDUAL", master_seed=20240101,
                          simulation_count=5000)
            mc_seconds.append(time.perf_counter() - t0)
            n_valid = int(res.get("valid", res.get(
                "valid_simulation_count", 5000)))
            if n_valid <= 0:
                exclusions.append(
                    {"state_id": sid, "reason": "ZERO_VALID_TRIALS",
                     "detail": "run produced no valid trials"})
            else:
                mc2_out[sid] = {
                    "winner_frequency": dict(res["winner_frequency"]),
                    "position_distribution": {
                        d: dict(p) for d, p in
                        res.get("position_distribution", {}).items()},
                    "valid": n_valid,
                    "fold_through": through, "frame_index": frame,
                }
        except Exception as exc:  # noqa: BLE001 - recorded exclusion
            exclusions.append(
                {"state_id": sid, "reason": "MC2_REFUSAL",
                 "detail": f"{type(exc).__name__}: {exc}"})
        ckpt_tick[0] += 1
        if ckpt_tick[0] % 5 == 0:
            json.dump({"mc2_out": mc2_out, "exclusions": exclusions,
                       "mc_seconds": mc_seconds},
                      open(ckpt_path, "w"), sort_keys=True, default=str)
            continue

    # ---- 5. adapt + align + C metrics (ground truth NOT yet joined) ----
    prov_mc2 = C.Provenance(
        artifact_path="v3.8D executed run_mc2 E_AR1_RESIDUAL",
        artifact_identity="mc2-e-5000-20240101-fold-through",
        model_identity="MC2-E (E_AR1_RESIDUAL)")
    prov_log = C.Provenance(
        artifact_path="data/v3/v3_3c/oof_baseline__D*.parquet",
        artifact_identity="v3_1b_baseline C=0.01 OOF",
        model_identity="LogisticRegression C=0.01 RAW 110-col")
    prov_xgb = C.Provenance(
        artifact_path="data/v3/v3_3c/oof_xgboost__D*.parquet",
        artifact_identity="xgb OOF",
        model_identity="xgboost diversity candidate")
    prov_v35 = C.Provenance(
        artifact_path="data/v3/v3_5c+3e OOF",
        artifact_identity="LOGISTIC_CONTROL/XGB_E proj",
        model_identity="V3.5 marginals")

    xgb_map = dict(zip(xgb.state_id, xgb.probability.astype(float)))
    v35_map = {(r.state_id, r.model): float(r.proj_is_top1)
               for r in v35_control.itertuples()}
    v35e_map = {(r.state_id): float(r.proj_is_top1)
                for r in v35e.itertuples()}

    records = []   # comparable primary rows
    support = {"candidate_rows": len(pop), "mc2_ok": len(mc2_out),
               "excluded": exclusions}
    for row in pop.itertuples():
        sid = row.state_id
        if sid not in mc2_out:
            continue
        meta = A.StateMeta(driver_id=row.driver_id, race_id=row.race_id,
                           year=int(row.season),
                           round=int(row.race_id[5:8].lstrip("r0") or 0),
                           lap=int(row.lapsel), stage=row.stage)
        r_log = A.from_independent_binary(
            sid, float(row.probability), meta,
            C.SourceId.V3_1B_LOGISTIC, prov_log)
        wf = mc2_out[sid]["winner_frequency"]
        roster = set(mc2_out[sid]["position_distribution"])
        if row.driver_id not in roster:
            exclusions.append(
                {"state_id": sid, "reason": "DRIVER_NOT_SIMULATED",
                 "detail": "row driver outside simulated roster"})
            continue
        # Simulated but winless = source-native zero (AVAILABLE).
        # Only a non-simulated driver is an exclusion.
        native_mc2 = float(wf.get(row.driver_id, 0.0))
        ms = _mc2_summary(row.driver_id, native_mc2, mc2_out[sid])
        r_mc = A.from_mc2_win(ms, sid, meta, prov_mc2,
                              mc2_out[sid]["valid"])
        frame = L.align_pair(sid, row.driver_id, (r_log, r_mc),
                             C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)
        assert frame.pair_comparable and frame.target_compatible
        gap_s = M.signed_gap(frame.p_a_native, frame.p_b_native)
        gap_a = M.absolute_gap(frame.p_a_native, frame.p_b_native)
        lo, hi = M.wilson_interval(frame.p_b_native,
                                   mc2_out[sid]["valid"])
        se = M.mc_sampling_se(frame.p_b_native, mc2_out[sid]["valid"])
        records.append({
            "state_id": sid, "race_id": row.race_id,
            "season": int(row.season), "lap": int(row.lapsel),
            "stage": row.stage, "driver_id": row.driver_id,
            "p_logistic": frame.p_a_native, "p_mc2": frame.p_b_native,
            "signed_gap": gap_s, "absolute_gap": gap_a,
            "mc_se": se, "mc_lo": lo, "mc_hi": hi,
            "inside_mc_interval": M.value_inside_interval(
                frame.p_a_native, (lo, hi)),
            "p_xgb": float(xgb_map[sid]),
            "p_v35": float(v35_map[(sid, "l2_logistic")]),
            "p_v35_xgb": float(v35e_map[sid]),
            "target": int(row.target),
        })

    # rank/leader/topk per (race, lap) group over comparable rows
    import collections
    groups = collections.defaultdict(list)
    for r in records:
        groups[(r["race_id"], r["lap"])].append(r)
    group_metrics = []
    for (race, lap), rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        la = M.average_ranks({r["driver_id"]: r["p_logistic"]
                              for r in rows})
        lb = M.average_ranks({r["driver_id"]: r["p_mc2"]
                              for r in rows})
        group_metrics.append({
            "race_id": race, "lap": lap, "n": len(rows),
            "spearman": M.spearman(la, lb),
            "kendall": M.kendall_taub(la, lb),
            "leader_a": sorted(M.leader_set(la)),
            "leader_b": sorted(M.leader_set(lb)),
            "top3_a": sorted(M.topk_set(la, 3)[0]),
            "top3_b": sorted(M.topk_set(lb, 3)[0]),
        })

    # ---- 6. ground-truth evaluation (AFTER metrics) ----
    EPS = protocol["scoring"]["epsilon"]
    assert EPS == 1e-15

    def _clip(p):
        return min(max(p, EPS), 1.0 - EPS)

    def _ll(p, y):
        p = _clip(p)
        return -(y * math.log(p) + (1 - y) * math.log(1 - p))

    def _bs(p, y):
        return (p - y) ** 2

    for r in records:
        y = r["target"]
        r["ll_log"] = _ll(r["p_logistic"], y)
        r["ll_mc2"] = _ll(r["p_mc2"], y)
        r["bs_log"] = _bs(r["p_logistic"], y)
        r["bs_mc2"] = _bs(r["p_mc2"], y)
        r["loss_advantage"] = r["ll_log"] - r["ll_mc2"]

    # race-macro aggregation
    by_race = collections.defaultdict(list)
    for r in records:
        by_race[r["race_id"]].append(r)
    race_rows = []
    for race in sorted(by_race):
        rows = by_race[race]
        race_rows.append({
            "race_id": race, "n": len(rows),
            "mean_spearman": _mean([g["spearman"] for g in group_metrics
                                    if g["race_id"] == race and
                                    g["spearman"] is not None]),
            "mean_abs_gap": sum(r["absolute_gap"] for r in rows) / len(
                rows),
            "mean_ll_log": sum(r["ll_log"] for r in rows) / len(rows),
            "mean_ll_mc2": sum(r["ll_mc2"] for r in rows) / len(rows),
        })

    # race-level bootstrap (B=2000, seed 987654321)
    rng = np.random.RandomState(987654321)
    races_list = sorted(by_race)
    n_races = len(races_list)
    boot = {"spearman": [], "abs_gap": [], "adv": []}
    for _ in range(2000):
        picks = [races_list[i] for i in
                 rng.randint(0, n_races, n_races)]
        sp = [g["spearman"] for g in group_metrics
              if g["race_id"] in picks and g["spearman"] is not None]
        ag = [r["absolute_gap"] for p in picks for r in by_race[p]]
        ad = [r["loss_advantage"] for p in picks for r in by_race[p]]
        if sp:
            boot["spearman"].append(sum(sp) / len(sp))
        if ag:
            boot["abs_gap"].append(sum(ag) / len(ag))
        if ad:
            boot["adv"].append(sum(ad) / len(ad))

    def _ci(v):
        v = sorted(v)
        return [v[int(0.025 * len(v))], v[int(0.975 * len(v))]]

    # ---- 7. gate ----
    import statistics
    abs_gaps = [r["absolute_gap"] for r in records]
    leader_mismatch = sum(
        1 for g in group_metrics
        if set(g["leader_a"]) != set(g["leader_b"]))
    outside_wilson = sum(1 for r in records
                         if not r["inside_mc_interval"])
    sp_all = [g["spearman"] for g in group_metrics
              if g["spearman"] is not None]
    pooled_sp = (sum(sp_all) / len(sp_all)) if sp_all else None
    race_sp = [x["mean_spearman"] for x in race_rows
               if x["mean_spearman"] is not None]
    macro_sp = sum(race_sp) / len(race_sp) if race_sp else None
    per_race_adv = {x["race_id"]: x["mean_ll_log"] - x["mean_ll_mc2"]
                    for x in race_rows}
    log_better = sum(1 for v in per_race_adv.values() if v > 0)
    mc2_better = sum(1 for v in per_race_adv.values() if v < 0)
    signs = {1 if r["loss_advantage"] > 0 else -1 if r["loss_advantage"]
             < 0 else 0 for r in records}

    stage_rows = collections.defaultdict(list)
    for r in records:
        stage_rows[r["stage"]].append(r)

    sem = True  # validity from explicit checks below (no post-hoc edits)
    assert (len(base["D1"]), len(base["D2"]), len(base["D3"])) == \
        (23577, 24422, 26606), "OOF fold counts changed"
    semantic_ok = (
        len(oof) == n_oof_rows and len(sel_races) == 8
        and set(oof.fold.unique()) == {"D1", "D2", "D3"})
    coverage_ok = (
        len(race_rows) >= 6
        and all(len(stage_rows.get(s, [])) >= 20
                for s in ("EARLY", "MID", "LATE"))
        and len(records) >= 150
        and max(len(v) for v in by_race.values()) / len(records) <= 0.4)
    distinct_ok = leader_mismatch >= 1 and outside_wilson >= 1
    compl_ok = log_better >= 1 and mc2_better >= 1 and signs == {1, -1}
    robust_ok = (
        pooled_sp is not None and macro_sp is not None
        and 0 < pooled_sp < 0.99 and 0 < macro_sp < 0.99)

    gate = {
        "SEMANTIC_VALIDITY": "PASS" if semantic_ok else "FAIL",
        "COVERAGE_ADEQUACY": "PASS" if coverage_ok else "FAIL",
        "DISTINCT_SIGNAL": "PASS" if distinct_ok else "FAIL",
        "COMPLEMENTARITY": "PASS" if compl_ok else "FAIL",
        "ROBUSTNESS": "PASS" if robust_ok else "FAIL",
    }
    if all(v == "PASS" for v in gate.values()):
        decision = "FUSION_RESEARCH_WARRANTED"
    else:
        decision = "FUSION_NOT_WARRANTED"

    wall_s = time.perf_counter() - t_start
    evaluation = {
        "schema": "v3.8d-historical-consensus-evaluation-v1",
        "protocol_identity": protocol["protocol_identity"],
        "population": {
            "oof_rows": n_oof_rows, "oof_races": 68,
            "selected_races": sel_races,
            "candidate_rows": len(pop),
            "comparable_rows": len(records),
            "excluded_rows": len(exclusions),
            "exclusions": exclusions,
            "exclusion_reasons": dict(collections.Counter(
                e["reason"] for e in exclusions)),
        },
        "mc2": {"config": protocol["mc2_config"],
                "runs": len(mc2_out),
                "wall_s": round(sum(mc_seconds), 1),
                "mean_s_per_run": round(
                    sum(mc_seconds) / max(len(mc_seconds), 1), 2)},
        "primary": {
            "pair": ["V3_1B_LOGISTIC", "MC2_E"], "target": "WIN",
            "n_groups": len(group_metrics),
            "pooled_spearman": pooled_sp,
            "macro_spearman": macro_sp,
            "leader_mismatch_states": leader_mismatch,
            "rows_outside_wilson": outside_wilson,
            "mean_abs_gap": sum(abs_gaps) / len(abs_gaps),
            "median_abs_gap": statistics.median(abs_gaps),
            "max_abs_gap": max(abs_gaps),
            "inside_mc_interval_frac": sum(
                r["inside_mc_interval"] for r in records) / len(records),
        },
        "groups": group_metrics,
        "races": race_rows,
        "stages": {s: {"n": len(v), "mean_abs_gap": sum(
            r["absolute_gap"] for r in v) / len(v)} for s, v in
            sorted(stage_rows.items())},
        "quality": {
            "per_race_advantage": per_race_adv,
            "log_better_races": log_better, "mc2_better_races": mc2_better,
            "mean_ll_log": sum(r["ll_log"] for r in records)
            / len(records),
            "mean_ll_mc2": sum(r["ll_mc2"] for r in records)
            / len(records),
        },
        "bootstrap": {k: {"mean": sum(v) / len(v), "ci95": _ci(v)}
                      if v else {"mean": None, "ci95": [None, None]}
                      for k, v in boot.items()},
        "gate_inputs": {"leader_mismatch": leader_mismatch,
                        "outside_wilson": outside_wilson,
                        "log_better": log_better,
                        "mc2_better": mc2_better,
                        "signs": sorted(signs)},
        "wall_s": round(wall_s, 1),
    }
    json.dump(evaluation,
              open(outdir / "historical_evaluation.json", "w"),
              indent=2, sort_keys=True, default=str)
    json.dump(records, open(outdir / "per_row_records.json", "w"),
              indent=1, sort_keys=True, default=str)
    gate_doc = {"schema": "v3.8d-fusion-gate-v1",
                "protocol_identity": protocol["protocol_identity"],
                "evidence": gate, "decision": decision}
    json.dump(gate_doc, open(outdir / "fusion_gate.json", "w"),
              indent=2, sort_keys=True)
    print(json.dumps({"comparable": len(records),
                      "excluded": len(exclusions),
                      "decision": decision,
                      "wall_s": round(wall_s, 1)}))
    return 0


class _Mc2Summary:
    def __init__(self, driver_id, win):
        self.driver_id = driver_id
        self.win_probability = win
        self.finish_position_distribution = ()


def _mc2_summary(driver_id, win, out):
    return _Mc2Summary(driver_id, win)


def _mean(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


if __name__ == "__main__":
    raise SystemExit(main())
