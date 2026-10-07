#!/usr/bin/env python3
"""V3.2H results roll-up (Parts AG-AL + AQ-AT + AY inputs).

Verifies the H prereg hash, then writes: regime_identities.json,
oracle_firewall.json, coverage_after.json, coverage_attribution.json,
blockers_after.json, dry_green_parity.json, regression_corpora.json,
weather_transition.json (extracted), performance.json,
precompute_cost.json.

No simulator source/artifact modified. Deterministic (no
timestamps/usernames/absolute paths). Coverage is recomputed from the
frozen V3.2F opportunity raw + H admission decisions (all REJECT ->
no newly supported checkpoints; verified by recount, not assumed).
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

OUT = ROOT / "results" / "v3" / "v3_2h"
RAW = ROOT / "results" / "v3" / "v3_2f" / "coverage_opportunity_raw.json"
FROZEN_BEFORE = {"eligible": 2305, "total": 9644}


def _hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   allow_nan=False, default=str).encode()).hexdigest()


def check_prereg() -> str:
    sys.path.insert(0, str(ROOT / "scripts"))
    from freeze_v3_2h_prereg import build, content_hash
    h = content_hash(build())
    saved = json.load(open(OUT / "preregistration.json", encoding="utf-8"))
    assert saved.get("prereg_hash") == h, "prereg hash mismatch"
    return h


def decisions() -> dict:
    out = {}
    for name in ("vsc", "wet", "sc", "yellow", "red"):
        d = json.load(open(OUT / f"{name}_decision.json", encoding="utf-8"))
        out[name.upper()] = d["decision"]
    ve = json.load(open(OUT / "vsc_ending_decision.json", encoding="utf-8"))
    out["VSC_ENDING"] = ve["decision"]
    return out


def main() -> int:
    prereg_hash = check_prereg()
    dec = decisions()
    admitted = [k for k, v in dec.items() if v.startswith("ADMIT_")]
    assert admitted == [], f"unexpected admission: {admitted}"

    raw = json.load(open(RAW, encoding="utf-8"))
    cps = raw["checkpoints"]
    n_total = len(cps)
    n_capable = sum(1 for c in cps if c["primary"] == "SIMULATION_CAPABLE")
    assert n_total == FROZEN_BEFORE["total"], n_total
    assert n_capable == FROZEN_BEFORE["eligible"], n_capable

    # primary + all-blocker recount (must match V3.2G frozen taxonomy)
    prim: dict = {}
    allb: dict = {}
    for c in cps:
        prim[c["primary"]] = prim.get(c["primary"], 0) + 1
        for b in c["all_blockers"]:
            allb[b] = allb.get(b, 0) + 1

    after = {"schema_version": "v3.2h-coverage-after-v1",
             "prereg_hash": prereg_hash, "eligible": n_capable,
             "total": n_total, "coverage": round(n_capable / n_total, 4),
             "before": dict(FROZEN_BEFORE),
             "change": 0}
    json.dump(after, open(OUT / "coverage_after.json", "w"),
              indent=2, sort_keys=True)

    attribution = {
        "schema_version": "v3.2h-coverage-attribution-v1",
        "prereg_hash": prereg_hash, "newly_supported": 0,
        "by_regime": {k: 0 for k in
                       ("VSC", "VSC_ENDING", "WET", "SC", "YELLOW", "RED")},
        "unexplained_growth": 0,
        "note": "no regime admitted; every recovered-checkpoint count "
                "is 0 by gate-scored decision, verified by recount",
    }
    json.dump(attribution, open(OUT / "coverage_attribution.json", "w"),
              indent=2, sort_keys=True)

    blockers = {"schema_version": "v3.2h-blockers-after-v1",
                "prereg_hash": prereg_hash, "primary": prim,
                "all_blocker_sets": allb}
    json.dump(blockers, open(OUT / "blockers_after.json", "w"),
              indent=2, sort_keys=True)

    f2 = json.load(open(ROOT / "results" / "v3" / "v3_2f_regime_coverage.json",
                        encoding="utf-8"))
    parity = {"schema_version": "v3.2h-dry-green-parity-v1",
              "prereg_hash": prereg_hash,
              "corpus_hash": f2["dry_green_parity"]["corpus_hash"],
              "members": 50, "status": "PARITY_OK_BIT_EXACT",
              "verified": "freeze_v3_2f_parity_corpus.py verify (H entry "
                          "gate); rerun as H final gate before freeze",
              "runtime_touched": False}
    json.dump(parity, open(OUT / "dry_green_parity.json", "w"),
              indent=2, sort_keys=True)

    reg = {"schema_version": "v3.2h-regression-corpora-v1",
           "prereg_hash": prereg_hash, "admitted_regimes": [],
           "corpora": {},
           "note": "no admitted regime -> no new regression corpus; "
                   "the permanent gates remain the V3.2F 50-checkpoint "
                   "dry-green parity corpus (7ae97c3c...)"}
    json.dump(reg, open(OUT / "regression_corpora.json", "w"),
              indent=2, sort_keys=True)

    wet = json.load(open(OUT / "wet_parameters.json", encoding="utf-8"))
    json.dump({"schema_version": "v3.2h-weather-transition-v1",
               "prereg_hash": prereg_hash,
               "lap_transition_counts": wet["weather_transition"]["counts"],
               "status": "COUNTS_ONLY_NO_ADMITTED_MODEL"},
              open(OUT / "weather_transition.json", "w"),
              indent=2, sort_keys=True)

    ident = {"schema_version": "v3.2h-regime-identities-v1",
             "prereg_hash": prereg_hash,
             "accepted_mc2": {"research": "mc2-r1-research",
                              "kernel": "mc2-kernel-v1",
                              "rng": "mc2-rng-v1",
                              "field": "mc2-field-v1",
                              "presence": "v3.2c-presence-v1"},
             "regime_support": "v3.2f-regime-support-v1 (unchanged; all "
                               "non-green regimes deferred/refused)",
             "parameter_identities": {
                 "vsc-duration-survival-v1": _hash(
                     json.load(open(OUT / "vsc_parameters.json"))["folds"]),
                 "vsc-pace-v1": "folded into vsc_parameters.json",
                 "wet-pace-v1": _hash(
                     json.load(open(OUT / "wet_parameters.json"))["folds"]),
                 "weather-transition-v1": "counts-only (no model)",
                 "sc-duration-v1": _hash(
                     json.load(open(OUT / "sc_parameters.json"))["folds"]),
                 "sc-compression-v1": "NOT_BUILT (rejected)",
                 "sc-restart-v1": "NOT_BUILT (rejected)"},
             "rng_domains": ["mc2-vsc-duration", "mc2-sc-duration",
                             "mc2-weather-transition"],
             "rng_status": "RESERVED_UNCONSUMED (no admitted stochastic "
                           "regime; dry-green streams unperturbed)"}
    json.dump(ident, open(OUT / "regime_identities.json", "w"),
              indent=2, sort_keys=True)

    fw = {"schema_version": "v3.2h-oracle-firewall-v1",
          "prereg_hash": prereg_hash,
          "runtime_reads_added": [],
          "poisoned_channels": ["TrackStatus@>T", "race-control@>T",
                                "weather@>T", "rainfall@>T",
                                "compounds@>T", "pits@>T",
                                "lap-timing@>T", "regime-end@>T",
                                "restart@>T"],
          "status": "VACUOUSLY_GREEN: no runtime regime path exists; "
                    "all estimation is offline past-only; dry-green "
                    "simulation path byte-unchanged (parity bit-exact)",
          "static_check": "tests/test_v3_2h_regime_models.py::"
                          "test_no_runtime_regime_reads"}
    json.dump(fw, open(OUT / "oracle_firewall.json", "w"),
              indent=2, sort_keys=True)

    # ---- performance: measure MC2-E throughput on one green checkpoint
    perf = {"schema_version": "v3.2h-performance-v1",
            "prereg_hash": prereg_hash, "regime_cost": "N/A_NO_ADMITTED_REGIME",
            "dry_green": None}
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import run_v3_2e_backtest as E2
        from raceintel.simulation.mc2.kernel import run_mc2
        from raceintel.simulation.mc2.variance import RegimeStat
        from raceintel.simulation.mc2.variance import (
            select_variance as _sel,
        )
        from raceintel.simulation.params import (
            load_simulation_parameters, parameter_storage_dir)
        import pandas as pd
        pc = json.load(open(ROOT / "results" / "v3" / "v3_2f" /
                            "dry_green_parity_corpus.json", encoding="utf-8"))
        race_id, frame = pc["member_keys"][0]
        season = int(race_id[:4])
        params = load_simulation_parameters(
            parameter_storage_dir(ROOT, 2024))
        results = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "results" /
            f"season={season}/results__{race_id}.parquet")
        grid = E2._grid_map(results)
        sim_state, selection, sampler, mechs, _diag = \
            E2._prepare_state_and_mechanisms(race_id, frame, params, grid)
        t0 = time.perf_counter()
        run_mc2(sim_state, selection, sampler, mechs,
                arm="E_AR1_RESIDUAL", master_seed=20240101,
                simulation_count=200)
        dt = time.perf_counter() - t0
        rps = 200 / dt
        perf["dry_green"] = {"runs_per_s": round(rps, 1),
                             "latency_5000_s": round(5000 / rps, 1),
                             "method": "measured: 200 MC2-E arm-E runs, "
                                       "single green checkpoint"}
    except Exception as e:  # noqa: BLE001 - record, never fabricate
        perf["dry_green"] = {"error": f"{type(e).__name__}: {e}",
                             "fallback": "V3.2F inherited 97 runs/s"}
    json.dump(perf, open(OUT / "performance.json", "w"),
              indent=2, sort_keys=True)

    rps = (perf["dry_green"] or {}).get("runs_per_s") or 97.0
    serial_h = (9644 * 5000 / rps) / 3600
    cost = {"schema_version": "v3.2h-precompute-cost-v1",
            "prereg_hash": prereg_hash,
            "catalogue": {"checkpoints": 9644, "runs": 5000,
                          "eligible_checkpoints": n_capable},
            "throughput_runs_per_s": {"measured": rps,
                                      "basis": ("measured this stage"
                                                if (perf["dry_green"] or {}).get("runs_per_s")
                                                else "V3.2F inherited")},
            "full_catalogue_h": {"serial": round(serial_h, 1),
                                 "x4_workers_extrapolated": round(serial_h / 4, 1),
                                 "x8_workers_extrapolated": round(serial_h / 8, 1)},
            "eligible_only_h": {
                "serial": round(serial_h * n_capable / n_total, 1)},
            "scaling_note": "worker columns are linear extrapolations, "
                            "not measured speedups; no perfect-scaling claim"}
    json.dump(cost, open(OUT / "precompute_cost.json", "w"),
              indent=2, sort_keys=True)

    print(f"prereg={prereg_hash} after={n_capable}/{n_total} "
          f"admitted={admitted} rps={(perf['dry_green'] or {}).get('runs_per_s')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
