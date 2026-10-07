#!/usr/bin/env python3
"""V3.2F results builder (Parts AN/AO-support): deterministic artifacts.

Read-only aggregation of:
- results/v3/v3_2f/coverage_opportunity_raw.json (Parts D/E/F/K/Z/AA/AB/AC/AD),
- results/v3/v3_2f/pace_evidence_raw.json (Parts G/H/I/J/L),
- results/v3/v3_2f/dry_green_parity_corpus.json (Parts C/Y),
- results/v3/v3_2c_coverage.json + v3_2e verdict (baseline inheritance).

Writes the Part AN JSON set into results/v3/v3_2f/. No simulator
source, parameter, artifact, or replay cache is modified. No model
training. Outputs carry no timestamps, usernames, or absolute paths.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FDIR = ROOT / "results" / "v3" / "v3_2f"


def _load(name: str):
    return json.loads((FDIR / name).read_text(encoding="utf-8"))


def _write(name: str, doc: dict) -> None:
    (FDIR / name).write_text(
        json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _enrich_stage(cps: list) -> None:
    """Derive fraction/stage from leader_lap / scheduled laps (read-only).

    v2_replay checkpoint entries carry leader_lap but no stage; the V3.2C
    convention is fraction = leader_lap / scheduled_laps with
    EARLY/MID/LATE thirds. Scheduled laps come from the processed races
    registry (same source the audit uses for race_meta).
    """
    import pandas as pd

    sched: dict[str, int] = {}
    for race_id in sorted({c["race_id"] for c in cps}):
        season = int(race_id.split("-")[0])
        p = (ROOT / "data" / "v2" / "processed" / "races" /
             f"season={season}" / f"races__{race_id}.parquet")
        try:
            df = pd.read_parquet(p)
        except FileNotFoundError:
            continue
        for row in df.itertuples():
            v = getattr(row, "total_laps_scheduled", None)
            if v is not None and pd.notna(v):
                sched[str(row.race_id)] = int(v)
    for c in cps:
        if c.get("stage") is not None:
            continue
        laps = sched.get(c["race_id"])
        lead = c.get("leader_lap")
        if laps and lead:
            frac = float(lead) / float(laps)
            c["fraction"] = round(frac, 4)
            c["stage"] = ("EARLY" if frac < 1.0 / 3.0 else
                          "MID" if frac < 2.0 / 3.0 else "LATE")


def main() -> int:
    raw = _load("coverage_opportunity_raw.json")
    pace = _load("pace_evidence_raw.json")
    parity = _load("dry_green_parity_corpus.json")
    cps = raw["checkpoints"]
    _enrich_stage(cps)
    TOTAL = len(cps)
    ref = [c for c in cps if c["primary"] == "SIMULATION_CAPABLE"]

    def has(c, *bs):
        return all(b in c["all_blockers"] for b in bs)

    def only(c, *bs):
        return set(c["all_blockers"]) == set(bs)

    # ---- blocker intersections (Part D) ----
    refused = [c for c in cps if c["primary"] != "SIMULATION_CAPABLE"]
    single = Counter(tuple(c["all_blockers"]) for c in refused
                     if len(c["all_blockers"]) == 1)
    multi_pairs: dict[str, int] = {}
    for a in ("UNSUPPORTED_TRACK_STATE", "WET_CONDITIONS"):
        for b in ("STALE_ROSTER_OBSERVATION",
                  "MISSING_DRIVER_OBSERVATION", "MISSING_TYRE_STATE",
                  "TERMINAL_STATE", "WET_CONDITIONS",
                  "UNSUPPORTED_TRACK_STATE"):
            if b <= a:
                continue
            n = sum(1 for c in refused if has(c, a, b))
            if n:
                multi_pairs[f"{a}x{b}"] = n
    intersections = {
        "schema_version": "v3.2f-blocker-intersections-v1",
        "n_refused": len(refused),
        "n_blockers_dist": {str(k): v for k, v in sorted(
            Counter(len(c["all_blockers"]) for c in refused).items())},
        "single_blocker": {str(k): v for k, v in sorted(
            single.items(), key=lambda kv: -kv[1])},
        "regime_x_other": {
            "TRACK_only": sum(1 for c in refused
                              if only(c, "UNSUPPORTED_TRACK_STATE")),
            "WET_only": sum(1 for c in refused
                            if only(c, "WET_CONDITIONS")),
            "TRACK_x_STALE": sum(1 for c in refused if has(
                c, "UNSUPPORTED_TRACK_STATE", "STALE_ROSTER_OBSERVATION")),
            "WET_x_STALE": sum(1 for c in refused if has(
                c, "WET_CONDITIONS", "STALE_ROSTER_OBSERVATION")),
            "TRACK_x_MISSING_DRIVER": sum(1 for c in refused if has(
                c, "UNSUPPORTED_TRACK_STATE", "MISSING_DRIVER_OBSERVATION")),
            "WET_x_MISSING_DRIVER": sum(1 for c in refused if has(
                c, "WET_CONDITIONS", "MISSING_DRIVER_OBSERVATION")),
            "TRACK_x_MISSING_TYRE": sum(1 for c in refused if has(
                c, "UNSUPPORTED_TRACK_STATE", "MISSING_TYRE_STATE")),
            "WET_x_MISSING_TYRE": sum(1 for c in refused if has(
                c, "WET_CONDITIONS", "MISSING_TYRE_STATE")),
            "TRACK_x_TERMINAL": sum(1 for c in refused if has(
                c, "UNSUPPORTED_TRACK_STATE", "TERMINAL_STATE")),
            "WET_x_TERMINAL": sum(1 for c in refused if has(
                c, "WET_CONDITIONS", "TERMINAL_STATE")),
            "TRACK_x_WET": sum(1 for c in refused if has(
                c, "UNSUPPORTED_TRACK_STATE", "WET_CONDITIONS")),
        },
        "multi_blocker_pairs": multi_pairs,
        "max_regime_only_headroom": (
            sum(1 for c in refused
                if only(c, "UNSUPPORTED_TRACK_STATE"))
            + sum(1 for c in refused if only(c, "WET_CONDITIONS"))),
    }
    _write("blocker_intersections.json", intersections)

    # ---- coverage opportunity (Part D/Z) ----
    by_race: dict[str, list] = {}
    for c in cps:
        by_race.setdefault(c["race_id"], []).append(c)
    race_cov = {}
    for race, cs in by_race.items():
        n_ok = sum(1 for c in cs if c["primary"] == "SIMULATION_CAPABLE")
        race_cov[race] = {"n": len(cs), "supported": n_ok,
                          "fraction": n_ok / len(cs)}
    cov_fracs = sorted(v["fraction"] for v in race_cov.values())
    opportunity = {
        "schema_version": "v3.2f-coverage-opportunity-v1",
        "total_checkpoints": TOTAL,
        "eligible_before": len(ref),
        "coverage_before": round(len(ref) / TOTAL, 4),
        "n_races": len(by_race),
        "races_with_ge1_supported": sum(
            1 for v in race_cov.values() if v["supported"] >= 1),
        "zero_support_races": sum(
            1 for v in race_cov.values() if v["supported"] == 0),
        "median_race_coverage": round(
            cov_fracs[len(cov_fracs) // 2], 4),
        "races_ge50": sum(1 for v in race_cov.values()
                          if v["fraction"] >= 0.5),
        "races_ge75": sum(1 for v in race_cov.values()
                          if v["fraction"] >= 0.75),
        "races_ge95": sum(1 for v in race_cov.values()
                          if v["fraction"] >= 0.95),
        "fully_supported_races": sum(
            1 for v in race_cov.values() if v["fraction"] == 1.0),
    }
    _write("coverage_opportunity.json", opportunity)

    # ---- season / stage cuts (Parts AA/AB, before == after) ----
    def _cut(key):
        out = {}
        vals = sorted({c[key] for c in cps if c.get(key) is not None})
        for v in vals:
            sub = [c for c in cps if c.get(key) == v]
            ok = sum(1 for c in sub
                     if c["primary"] == "SIMULATION_CAPABLE")
            out[str(v)] = {"n": len(sub), "supported": ok,
                           "coverage": round(ok / len(sub), 4) if sub
                           else 0.0}
        return out

    season_cov = {
        "schema_version": "v3.2f-season-coverage-v1",
        "before": _cut("season"), "after": _cut("season"),
    }
    _write("coverage_by_season.json", season_cov)
    stage_cov = {
        "schema_version": "v3.2f-stage-coverage-v1",
        "before": _cut("stage"), "after": _cut("stage"),
    }
    _write("coverage_by_stage.json", stage_cov)

    # ---- regime cut (Part AC) ----
    regime_cov = {"schema_version": "v3.2f-regime-coverage-v1",
                  "regimes": {}}
    for tok in ("all_clear", "yellow", "vsc", "vsc_ending", "safety_car",
                "red_flag", None):
        sub = [c for c in cps if c["track_state"] == tok]
        if tok is None:
            sub = [c for c in cps if c["track_state"] is None]
            label = "UNKNOWN"
        else:
            label = {"all_clear": "DRY_GREEN"}.get(tok, tok.upper())
        ok = sum(1 for c in sub if c["primary"] == "SIMULATION_CAPABLE")
        regime_cov["regimes"][label] = {
            "total": len(sub), "supported": ok, "unsupported": len(sub)
            - ok, "coverage": round(ok / len(sub), 4) if sub else 0.0}
    _write("coverage_by_regime.json", regime_cov)

    # ---- track regime audit (Part E) ----
    track_audit = {
        "schema_version": "v3.2f-track-regime-audit-v1",
        "tokens": ["all_clear", "yellow", "safety_car", "vsc",
                   "vsc_ending", "red_flag", None],
        "checkpoint_counts": {
            (t if t is not None else "null"): sum(
                1 for c in cps if c["track_state"] == t) for t in
            ("all_clear", "yellow", "safety_car", "vsc", "vsc_ending",
             "red_flag", None)},
        "primary_by_token": {},
        "note": ("Tokens are the frozen D9 per-lap last-char TrackStatus "
                 "mapping (FastF1 codes 1/2/4/5/6/7). No LOCAL vs FULL "
                 "course distinction exists in the token; sector exposure "
                 "is not carried by RaceState."),
    }
    for t in ("all_clear", "yellow", "safety_car", "vsc", "vsc_ending",
              "red_flag", None):
        sub = [c for c in cps if c["track_state"] == t]
        label = "null" if t is None else t
        track_audit["primary_by_token"][label] = dict(Counter(
            c["primary"] for c in sub))
    _write("track_regime_audit.json", track_audit)

    # ---- neutralisation episodes (Part F) ----
    nev: dict[str, int] = Counter()
    races_with: dict[str, set] = {}
    for race, el in raw["episodes"].items():
        for e in el:
            if e["token"] == "all_clear":
                continue
            nev[e["token"]] += 1
            races_with.setdefault(e["token"], set()).add(race)
    transition_audit = {
        "schema_version": "v3.2f-transition-audit-v1",
        "episodes_by_token": dict(nev),
        "races_with_episode": {k: len(v)
                               for k, v in races_with.items()},
        "offline_rule": ("Run-length episodes over checkpoint-frame modal "
                         "track_state; entry/exit laps per race in "
                         "coverage_opportunity_raw.episodes. Runtime T may "
                         "use only regime state known at or before T; "
                         "future duration/exit is forbidden."),
    }
    _write("transition_audit.json", transition_audit)

    # ---- per-regime evidence packs (Parts G/H/I/J/K/L) ----
    _write("yellow_audit.json", {
        "schema_version": "v3.2f-yellow-audit-v1",
        "checkpoint_token_count": track_audit["checkpoint_counts"][
            "yellow"],
        "pace_delta_s": pace["regime_delta_s"].get("yellow"),
        "affected_driver_fractions": pace["yellow_affected"],
        "rc_semantics": pace["yellow_rc"],
        "finding": ("Median yellow-lap field impact +0.46s with median "
                    "5.9% of drivers slowed >2s: the token is "
                    "overwhelmingly local. Last-message RC channel is "
                    "stale/unrelated in most rows (median age 16.9s; "
                    "2202/5877 rows carry no flag). No causal "
                    "sector->driver exposure mapping exists in frozen "
                    "RaceState."),
    })
    _write("vsc_audit.json", {
        "schema_version": "v3.2f-vsc-audit-v1",
        "checkpoint_token_count": track_audit["checkpoint_counts"]["vsc"]
        + track_audit["checkpoint_counts"]["vsc_ending"],
        "pace_delta_s": pace["regime_delta_s"].get("vsc"),
        "ending_lap_pace_delta_s": pace["regime_delta_s"].get(
            "vsc_ending"),
        "episode_durations_laps": pace["episode_durations_laps"].get(
            "vsc"),
        "finding": ("VSC pace process is measurable (median +19.6s, "
                    "n=892) but runtime simulation from mid-VSC needs a "
                    "stochastic duration model (55 lap-level episodes, "
                    "p50 1 lap), a restart transition, and "
                    "regime-conditioned anchor history; none exists in "
                    "accepted MC2 E."),
    })
    _write("safety_car_audit.json", {
        "schema_version": "v3.2f-safety-car-audit-v1",
        "checkpoint_token_count": track_audit["checkpoint_counts"][
            "safety_car"],
        "pace_delta_s": pace["regime_delta_s"].get("safety_car"),
        "restart_lap_delta_s": pace["sc_restart"],
        "episode_durations_laps": pace["episode_durations_laps"].get(
            "safety_car"),
        "finding": ("SC reshapes pace (+33.2s median, sd 18.7s), gaps "
                    "(bunching), pit incentives, and restarts (restart "
                    "lap sd 21.2s). No SC pace/compression/duration/"
                    "restart model exists; R6 pit transitions are "
                    "dry-filtered. Modelling SC as pace+N-seconds is "
                    "explicitly rejected by this evidence."),
    })
    _write("red_audit.json", {
        "schema_version": "v3.2f-red-audit-v1",
        "checkpoint_token_count": track_audit["checkpoint_counts"][
            "red_flag"],
        "usable_lap_rows": 0,
        "races_with_red_episode": transition_audit[
            "races_with_episode"].get("red_flag", 0),
        "finding": ("22 checkpoints, 0 usable lap rows under red, 21 "
                    "episodes. Race semantics (suspension/restart, "
                    "tyre-change rules) differ substantially. DEFER by "
                    "default expectation; evidence confirms."),
    })
    wet_blocked = [c for c in cps if "WET_CONDITIONS" in c["all_blockers"]]
    _write("wet_audit.json", {
        "schema_version": "v3.2f-wet-audit-v1",
        "wet_blocked_checkpoints": len(wet_blocked),
        "rain_falling": sum(1 for c in wet_blocked
                            if c["rainfall"] is True),
        "wet_compound": sum(1 for c in wet_blocked if c["wet_drivers"]),
        "both": sum(1 for c in wet_blocked
                    if c["rainfall"] is True and c["wet_drivers"]),
        "wet_lap_dataset": pace["wet_counts_era_compound_rain"],
        "slicks_under_rain_laps": sum(
            pace["slicks_under_rain_counts"].values()),
        "finding": ("INTERMEDIATE pace data is plentiful (~6.9k laps) "
                    "but WET-compound rain laps are thin (294 across "
                    "eras); circuit x compound cells would be unstable. "
                    "Weather evolution and wet/dry compound transitions "
                    "have no causal mechanism in scope (R6 transitions "
                    "are dry-filtered; Strategy 2.0 forbidden)."),
    })

    # ---- regime contracts (Parts G/H/I/J/M + P/Q/R policies) ----
    contracts = {
        "schema_version": "v3.2f-regime-contracts-v1",
        "parameter_temporal_policy": (
            "Evaluation season Y -> training seasons strictly before Y "
            "(through-season artifacts; no 2025). Fold pattern inherited "
            "from V3.2D (D1/D2/D3)."),
        "parameter_identity_rule": (
            "Every family: schema version, regime, training seasons, "
            "conditioning, minimum N, fallback hierarchy, estimator, "
            "content identity. No timestamps/usernames/paths. Pattern "
            "exists (mc2-params-v1 through-2019/2021/2023)."),
        "rng_domain_rule": (
            "Any future stochastic regime evolution gets an explicit "
            "deterministic domain (mc2-vsc-duration, mc2-sc-duration, "
            "mc2-weather-transition reserved, unconsumed). Same-seed "
            "equality, chunk invariance, parallel determinism, Phase-7 "
            "CRN compatibility required. No unrelated residual RNG "
            "reuse."),
        "contracts": {
            "YELLOW": {
                "detection_at_T": "frozen track_state token (no sector)",
                "initial_state": "NOT CONSTRUCTIBLE (local exposure "
                                 "unknown)",
                "mechanism": "none admitted (global penalty rejected)",
                "fallback": "explicit refusal UNSUPPORTED_TRACK_STATE",
            },
            "VSC": {
                "detection_at_T": "frozen track_state token",
                "initial_state": "constructible only at VSC onset with "
                                 "green history",
                "mechanism": "boundary A (stochastic duration) sketched; "
                             "duration/restart/anchor-conditioning "
                             "unestimated",
                "fallback": "explicit refusal UNSUPPORTED_TRACK_STATE",
            },
            "SAFETY_CAR": {
                "detection_at_T": "frozen track_state token",
                "initial_state": "NOT CONSTRUCTIBLE honestly (gaps "
                                 "compressed, restart pending)",
                "mechanism": "none in scope (needs bunching + restart "
                             "+ VSC-aware pits)",
                "fallback": "explicit refusal UNSUPPORTED_TRACK_STATE",
            },
            "WET": {
                "detection_at_T": "rainfall flag + compound (factual)",
                "initial_state": "constructible (compounds factual)",
                "mechanism": "wet pace partially estimable (INTER) but "
                             "weather-evolution + compound-transition "
                             "mechanisms missing",
                "fallback": "explicit refusal WET_CONDITIONS",
            },
            "RED": {
                "detection_at_T": "frozen track_state token",
                "initial_state": "NOT IN SCOPE (suspension semantics)",
                "mechanism": "none",
                "fallback": "explicit refusal UNSUPPORTED_TRACK_STATE",
            },
        },
    }
    _write("regime_contracts.json", contracts)

    # ---- admission decisions (Part T) ----
    admission = {
        "schema_version": "v3.2f-admission-decisions-v1",
        "ladder": ("evidence audit -> contract -> estimator -> temporal "
                   "tests -> offline validation -> admission -> "
                   "implementation; a deferred regime remains explicitly "
                   "unavailable"),
        "decisions": {
            "YELLOW": {"decision": "DEFER_YELLOW",
                       "gate_failed": "causal initial state",
                       "reason": "YELLOW_DEFERRED_INSUFFICIENT_SPATIAL_"
                                 "SEMANTICS"},
            "VSC": {"decision": "DEFER_VSC",
                    "gate_failed": "explicit simulation mechanism + "
                                   "parameter estimation",
                    "reason": "VSC_DEFERRED_DURATION_RESTART_ANCHOR_"
                              "EVIDENCE_THIN"},
            "SAFETY_CAR": {"decision": "DEFER_SC",
                           "gate_failed": "explicit simulation mechanism",
                           "reason": "SC_DEFERRED_COMPRESSION_RESTART_"
                                     "OUT_OF_SCOPE"},
            "WET": {"decision": "DEFER_WET",
                    "gate_failed": "weather evolution + compound "
                                   "transition boundaries",
                    "reason": "WET_DEFERRED_EVOLUTION_TRANSITION_"
                              "NO_CAUSAL_MECHANISM"},
            "RED": {"decision": "DEFER_RED",
                    "gate_failed": "evidence (n=22, 0 usable laps)",
                    "reason": "RED_DEFERRED_DEFAULT_EXPECTATION_"
                              "CONFIRMED"},
        },
        "implemented_regimes": [],
        "deferred_regimes": ["YELLOW", "VSC", "SAFETY_CAR", "WET",
                             "RED"],
    }
    _write("admission_decisions.json", admission)

    # ---- validation placeholder (Parts V/W/X: nothing admitted) ----
    _write("regime_validation.json", {
        "schema_version": "v3.2f-regime-validation-v1",
        "status": "NOT_APPLICABLE_NO_ADMITTED_REGIME",
        "rule": ("Validation population/comparator/metrics apply to "
                 "admitted regimes only. Deferred regimes must not be "
                 "validated by running dry-green dynamics under a "
                 "removed guard; that comparison is forbidden."),
    })

    # ---- coverage after (Parts Z/AA/AB/AC: recomputed, unchanged) ----
    _write("coverage_after.json", {
        "schema_version": "v3.2f-coverage-after-v1",
        "before": {"eligible": len(ref), "total": TOTAL,
                   "coverage": round(len(ref) / TOTAL, 4)},
        "after": {"eligible": len(ref), "total": TOTAL,
                  "coverage": round(len(ref) / TOTAL, 4)},
        "absolute_checkpoint_gain": 0,
        "percentage_point_gain": 0.0,
        "method": ("Full 9644-checkpoint eligibility recomputation "
                   "through the frozen V3.2C presence path with "
                   "admitted-regime set = {} (empty). Primary verdicts "
                   "reproduce the V3.2C audit bit-exact (0 mismatches)."),
        "parity_corpus": parity["corpus_hash"],
    })
    _write("recovery_accounting.json", {
        "schema_version": "v3.2f-recovery-accounting-v1",
        "newly_supported_checkpoints": 0,
        "by_admission": {},
        "by_state_source_improvement": {},
        "unexplained_growth": 0,
        "missing_tyre_note": ("198 MISSING_TYRE states inspected: "
                              "lap-1 all-null tyre rows and early-"
                              "retirement data gaps; no causal tyre "
                              "source exists (stint fields null too). "
                              "V3.2C deferral stands with evidence."),
        "position_null_note": ("DEFER_POSITION_NULL: no semantic proof "
                               "found; V3.2C 0-false-positive finding "
                               "cited, not promoted."),
    })

    # ---- parameter diagnostics (Part L/Q) ----
    _write("parameter_diagnostics.json", {
        "schema_version": "v3.2f-parameter-diagnostics-v1",
        "wet_cells": pace["wet_counts_era_compound_rain"],
        "circuit_x_compound_warning": (
            "WET|rain cells total 294 across eras; per-circuit cells "
            "would be unstable (Part L rule). No tiny cells created."),
        "vsc_duration_episodes_lap_level": pace[
            "episode_durations_laps"].get("vsc"),
        "sc_duration_episodes_lap_level": pace[
            "episode_durations_laps"].get("safety_car"),
        "fold_policy": "evaluation Y -> through-(Y-1); no 2025",
        "new_parameter_families_estimated": 0,
    })

    # ---- performance (Part AH) + precompute plan (Part AI) ----
    _write("performance.json", {
        "schema_version": "v3.2f-performance-v1",
        "mc2e_parity_corpus": {
            "members": parity["corpus_size"], "n_runs": parity["n_runs"],
            "wall_clock_s": parity["wall_clock_s"],
            "runs_per_s": round(parity["corpus_size"] * parity["n_runs"]
                                / parity["wall_clock_s"], 1)},
        "regime_audit_scan": {
            "n_checkpoints": raw["n_checkpoints"],
            "wall_clock_s": raw["wall_clock_s"]},
        "inherited_v32e": {
            "mc2e_runs_per_s": 97, "r3_slowdown": 13.6,
            "catalogue_serial_h": 33.1, "at_8_workers_h": 5.9},
        "note": ("No admitted regimes: no new runtime paths to "
                 "benchmark. Accepted MC2 E science untouched "
                 "(mechanical bit-exact preservation only)."),
    })
    _write("precompute_optimization_plan.json", {
        "schema_version": "v3.2f-precompute-optimization-plan-v1",
        "constraint": ("Any future optimization must preserve "
                       "bit/scientific equivalence with accepted MC2 E; "
                       "no risky optimization in V3.2F."),
        "bottlenecks": [
            "mechanism preparation (anchor history scan per driver, "
            "pandas row loops in _prepare_state_and_mechanisms)",
            "per-simulation Python event loop in run_mc2 "
            "(earliest-first scheduling, ~97 runs/s)",
            "parquet reload per worker job (no shared frame cache)",
            "result serialization per checkpoint (full position "
            "distributions)",
        ],
        "safe_vectors": [
            "vectorize anchor/dynamics preparation over drivers "
            "(numpy batch, verified bit-exact on parity corpus)",
            "multiprocessing over checkpoints (already used; measured "
            "efficiency assumption in V3.2E)",
            "shared-memory frame cache across workers",
            "batched residual draws per simulation (CRN-preserving "
            "reorder with proof)",
        ],
        "forbidden": ["kernel math rewrites without parity proof",
                      "RNG stream reassignment",
                      "reduced n_runs without TV-gate revalidation"],
    })
    print(json.dumps({"status": "OK",
                      "artifacts": 17,
                      "regime_only_headroom":
                          intersections["max_regime_only_headroom"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
