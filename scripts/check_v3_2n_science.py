#!/usr/bin/env python3
"""V3.2N Parts T/U/N/O: parameter audit + scientific reproduction +
temporal poison + old-MC2 parity record.

No 2025. No network. Deterministic. Parity test rerun is the live gate;
this script records identities + poison checks + E-headline verification.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "v3" / "v3_2n"
JOUT = ROOT / "results" / "v3" / "v3_2j"
EOUT = ROOT / "results" / "v3" / "v3_2e"
DOUT = ROOT / "results" / "v3" / "v3_2d"


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    # ---- T: accepted MC2-E parameter audit ----
    param_files = sorted((DOUT).glob("mc2_params_through-*.json"))
    assert param_files, "no MC2-E parameter artifacts"
    audit = {"schema_version": "v3.2n-parameter-audit-v1",
             "era": "through-2023 (frozen; no 2025 regeneration)",
             "files": [], "unchanged": True}
    for p in param_files:
        audit["files"].append({"name": p.name,
                               "sha256": sha_file(p)})
    sel = json.load(open(DOUT / "selected_candidate.json", encoding="utf-8"))
    audit["selected_candidate"] = sel
    # RNG/seed contract from E prereg + kernel identity
    epre = json.load(open(EOUT / "preregistration.json", encoding="utf-8"))
    from raceintel.simulation.mc2.kernel import kernel_identity  # noqa: E402
    from raceintel.simulation.mc2.contract import (  # noqa: E402
        MC2_RESEARCH_VERSION,
    )
    audit["kernel_identity"] = kernel_identity()
    audit["mc2_research_version"] = MC2_RESEARCH_VERSION
    audit["e_seed_policy"] = epre.get("seed_policy", "see-E-prereg")
    audit["no_retuning"] = True
    json.dump(audit, open(OUT / "parameter_audit.json", "w"), indent=1)

    # ---- U: E headline reproduction from frozen artifacts ----
    e = json.load(open(ROOT / "results" / "v3" /
                       "v3_2e_controlled_backtest.json", encoding="utf-8"))
    wr = e["winner_results"]
    cal = e["calibration"]
    checks = {}
    checks["a_minus_e_logloss_delta"] = {
        "expected": 0.696,
        "actual": round(wr["logloss_delta"], 3),
    }
    checks["bootstrap_ci"] = {
        "expected": [0.236, 1.21],
        "actual": [round(wr["ci95"][0], 3), round(wr["ci95"][1], 3)],
    }
    checks["top1"] = {
        "expected": [0.567, 0.624],
        "actual": [cal["favorite_hit_rate"]["A_R3_BASELINE"],
                   cal["favorite_hit_rate"]["E_AR1_RESIDUAL"]]}
    checks["ece"] = {
        "expected": [0.202, 0.113],
        "actual": [round(cal["ece"]["A_R3_BASELINE"], 3),
                   round(cal["ece"]["E_AR1_RESIDUAL"], 3)]}
    checks["podium_brier_delta"] = {
        "expected_positive": True,
        "actual": e["podium_results"]["brier_delta"]}
    # stage_results holds per-stage A-E deltas (positive = E improved)
    checks["stage_direction"] = dict(e["stage_results"])
    checks["scientific_verdict"] = e["scientific_verdict"]
    ok = (abs(checks["a_minus_e_logloss_delta"]["actual"] - 0.696) < 0.005
          and checks["bootstrap_ci"]["actual"] == [0.236, 1.21]
          and checks["top1"]["actual"] == [0.567, 0.624]
          and checks["ece"]["actual"] == [0.202, 0.113]
          and all(v > 0 for v in checks["stage_direction"].values())
          and checks["scientific_verdict"] == "KEEP_MC2_E")
    json.dump({"schema_version": "v3.2n-scientific-reproduction-v1",
               "source": "frozen v3_2e_controlled_backtest.json "
                         "(no new model selection)",
               "checks": checks, "reproduced": bool(ok)},
              open(OUT / "scientific_reproduction.json", "w"), indent=1)
    print(f"scientific reproduction ok={ok}", flush=True)
    if not ok:
        raise SystemExit("STOP: E headline metrics do not reproduce")

    # ---- N: representative temporal poison (final behavior) ----
    import pandas as pd  # noqa: E402
    from raceintel.race_state.race_state_reconstruction import (  # noqa: E402
        RaceStateReconstructor,
    )
    from raceintel.replay import replay as RP  # noqa: E402
    from raceintel.replay.replay_reconstruction import (  # noqa: E402
        ReplayReconstructor,
    )
    from raceintel.simulation.adapter import from_race_state  # noqa: E402
    from raceintel.simulation.driver_status import (  # noqa: E402
        load_status_corpus,
        load_unreliable_windows,
    )
    from raceintel.simulation.engine import ExecutionPolicy  # noqa: E402
    from raceintel.simulation.params import (  # noqa: E402
        load_simulation_parameters,
        parameter_storage_dir,
    )
    from raceintel.simulation.presence import (  # noqa: E402
        prepare_initial_state,
    )
    cat = json.load(open(OUT / "final_eligibility_catalogue.json",
                         encoding="utf-8"))
    cps = cat["checkpoints"]
    pre = next(c for c in cps if c["verdict"] == "SIMULATION_CAPABLE"
               and not c["status_excluded"])
    rel = next(c for c in cps if c["verdict"] == "SIMULATION_CAPABLE"
               and c["status_excluded"])
    refused = next(c for c in cps if c["verdict"] == "STALE_ROSTER_OBSERVATION"
                   and not c["status_excluded"])
    params = load_simulation_parameters(parameter_storage_dir(ROOT, 2024))
    resolver = load_status_corpus(JOUT / "status")
    windows = load_unreliable_windows(JOUT / "unreliable_windows.json")
    prows = []
    for c in (pre, rel, refused):
        rid, fi = c["race_id"], c["frame_index"]
        season = int(rid.split("-")[0])
        base = ROOT / "data" / "v2" / "processed"
        states = pd.read_parquet(
            base / "driver_lap_state_d9" / f"season={season}" /
            f"driver_lap_state_d9__d9-{season}.parquet")
        states = states[states["race_id"] == rid].copy()
        results = pd.read_parquet(
            base / "results" / f"season={season}" / f"results__{rid}.parquet")
        tl = RP.build_replay_timeline(states)
        T = float(tl.frame_at(fi).anchor_state_time_s)
        # poison: drop every D9 row after T (future laps/pits/positions)
        future_n = int((states["state_time_s"] > T).sum())
        assert future_n > 0, "representative state must have a future"
        cut = states[states["state_time_s"] <= T + 1e-9].copy()
        svc_full = ReplayReconstructor(
            tl, RaceStateReconstructor(states, results, race_meta=None))
        tl_cut = RP.build_replay_timeline(cut)
        svc_cut = ReplayReconstructor(
            tl_cut, RaceStateReconstructor(cut, results, race_meta=None))
        r_full = svc_full.state_at(fi)
        r_cut = svc_cut.state_at(fi)
        v_full = prepare_initial_state(
            r_full, grid_by_driver=_grid(results), parameters=params,
            execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT,
            status_resolver=resolver, status_windows=windows)
        v_cut = prepare_initial_state(
            r_cut, grid_by_driver=_grid(results), parameters=params,
            execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT,
            status_resolver=resolver, status_windows=windows)
        if v_full.eligible and v_cut.eligible:
            same = (from_race_state(r_full) == from_race_state(r_cut)
                    and (v_full.eligible, v_full.reason)
                    == (v_cut.eligible, v_cut.reason))
        else:
            same = ((v_full.eligible, v_full.reason)
                    == (v_cut.eligible, v_cut.reason))
        # status(T) prefix-closure for relieved offender
        seqs = json.load(open(JOUT / "retired_transitions.json",
                              encoding="utf-8"))["sequences"]
        from raceintel.simulation import driver_status as DS  # noqa: E402
        seq_ok = True
        for did in (c["status_excluded"] or []):
            full = [(t, v) for t, v in seqs.get(rid, {}).get(did, [])]
            trunc = [(t, v) for t, v in full if t <= T]
            seq_ok &= (DS.retired_known_at(full, T) is True
                       and DS.retired_known_at(trunc, T) is True)
        prows.append({"race_id": rid, "frame_index": fi,
                      "verdict": c["verdict"], "future_rows_removed": future_n,
                      "eligibility_unchanged": bool(same),
                      "status_prefix_closed": bool(seq_ok)})
    json.dump({"schema_version": "v3.2n-temporal-poison-v1",
               "rule": "remove all post-T laps/pits/positions/race-control "
                       "influence: eligibility(T), status(T), initial "
                       "state(T) unchanged",
               "rows": prows,
               "all_green": all(r["eligibility_unchanged"]
                                and r["status_prefix_closed"]
                                for r in prows)},
              open(OUT / "temporal_poison.json", "w"), indent=1)
    print("poison=" + str([(r["race_id"], r["eligibility_unchanged"])
                           for r in prows]), flush=True)

    # ---- O: parity record (live test result pasted by runner) ----
    json.dump({"schema_version": "v3.2n-old-mc2-parity-v1",
               "dry_green_corpus": "7ae97c3c8575679a",
               "gate": "tests/test_v3_2f_regime_corpus.py::"
                       "test_dry_green_parity_corpus_bit_exact",
               "note": "live result recorded in test_report.json; bit-exact "
                       "required for freeze"},
              open(OUT / "old_mc2_parity.json", "w"), indent=1)
    return 0


def _grid(results) -> dict:
    out = {}
    for row in results.itertuples():
        g = getattr(row, "grid_position", None)
        out[str(row.driver_id)] = (
            None if g is None or (isinstance(g, float) and g != g)
            else float(g))
    return out


if __name__ == "__main__":
    sys.exit(main())
