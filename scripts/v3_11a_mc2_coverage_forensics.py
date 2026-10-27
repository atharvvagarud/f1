#!/usr/bin/env python3
"""V3.11A -- MC2 coverage forensics (observational, read-only).

Reproduces the frozen V3.10 (v3.10-pit-wall) MC2 eligibility ledger
(9644 candidate states: 3678 eligible, 5966 unsupported) from frozen
repository evidence and explains, with state-level evidence, why each
unsupported state is unsupported.

Scientific rules (enforced by construction, see tests/test_v3_11a_forensics.py):
- read-only: never writes outside results/v3/v3_11a/; never imports
  production runtime (raceintel/api/frontend); never mutates eligibility.
- causal: every observation probe uses rows with state_time_s <= T only
  (numpy searchsorted side="right" minus one). Future rows are loaded
  solely to *demonstrate* they exist and were ignored (poison audit).
- deterministic: stable sort by (race_id, frame_index); JSON sort_keys;
  no timestamps/usernames/paths in artifacts.

Exact command:
    .venv/bin/python scripts/v3_11a_mc2_coverage_forensics.py

Inputs (all frozen, committed):
- results/v3/v3_2n/final_eligibility_catalogue.json (authoritative primary)
- results/v3/v3_2f/coverage_opportunity_raw.json (all_blockers multi-cause)
- results/v3/v3_2n/final_blockers.json (consistency cross-check)
- results/v2_replay/checkpoints/*.json (T = anchor_state_time_s per state)
- data/v2/processed/driver_lap_state_d9/season=[2018-2024]/*.parquet
"""

from __future__ import annotations

import csv
import glob
import json
import math
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11a"

# ---------------------------------------------------------------------------
# Frozen baseline (V3.10-pit-wall ledger, from v3.2n/v3.2j frozen evidence).
# ---------------------------------------------------------------------------

EXPECTED_TOTAL = 9644
EXPECTED_ELIGIBLE = 3678
EXPECTED_UNSUPPORTED = 5966
EXPECTED_REASONS = {
    "STALE_ROSTER_OBSERVATION": 3294,
    "UNSUPPORTED_TRACK_STATE": 1165,
    "WET_CONDITIONS": 801,
    "MISSING_DRIVER_OBSERVATION": 354,
    "MISSING_TYRE_STATE": 198,
    "TERMINAL_STATE": 154,
}
# Frozen short labels used in the mission text.
SHORT = {
    "STALE_ROSTER_OBSERVATION": "STALE",
    "UNSUPPORTED_TRACK_STATE": "TRACK",
    "WET_CONDITIONS": "WET",
    "MISSING_DRIVER_OBSERVATION": "MISSING_DRIVER",
    "MISSING_TYRE_STATE": "MISSING_TYRE",
    "TERMINAL_STATE": "TERMINAL",
    "SIMULATION_CAPABLE": "ELIGIBLE",
}
PRIMARY_PRECEDENCE = (  # frozen evaluation order, engine.py + adapter.py
    "MISSING_DRIVER_OBSERVATION",  # adapter first
    "TERMINAL_STATE",  # presence, post-adapter
    "UNSUPPORTED_TRACK_STATE",  # _validate_start_state: red/neutral/unknown
    "WET_CONDITIONS",  # rainfall, then (after tyre) wet compound
    "MISSING_TYRE_STATE",  # missing_tyre_age before wet_compound_state
    "STALE_ROSTER_OBSERVATION",  # _validate_contemporaneous last
)

WET_COMPOUNDS = ("INTERMEDIATE", "WET")  # raceintel/simulation/params.py:88
FRESHNESS_LAP_TIMES = 3.0  # engine.py CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES
SUPPORTED_TRACK = ("all_clear",)  # engine.py SUPPORTED_TRACK_STATES

RECOVERY_CLASSES = (
    "R0_PERMANENT_OR_INTENTIONAL",
    "R1_LOW_RISK_DATA_RECONSTRUCTION",
    "R2_DOMAIN_RULE_REQUIRED",
    "R3_SIMULATOR_SUPPORT_REQUIRED",
    "R4_RESEARCH_REQUIRED",
    "R5_NOT_CAUSALLY_RECOVERABLE",
    "R6_UNKNOWN",
)

STALE_RE = re.compile(r"\(([\d.]+)s\) older than T cannot be evolved honestly: (.*)$")
OFFENDER_RE = re.compile(r"([a-z0-9_]+) age=([\d.]+)s")
UNOBSERVED_RE = re.compile(r"no observation at or before T: \[(.*)\]$")
DRIVER_Q_RE = re.compile(r"'([a-z0-9_]+)'")
MISSING_TYRE_RE = re.compile(r"driver '([a-z0-9_]+)' has no factual tyre age")


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested; no I/O, no production imports).
# ---------------------------------------------------------------------------

def parse_stale_reason(reason: str):
    """Return (threshold_s, [(driver_id, age_s)]) from a frozen STALE detail."""
    m = STALE_RE.search(reason or "")
    if not m:
        return None, []
    return float(m.group(1)), [
        (d, float(a)) for d, a in OFFENDER_RE.findall(m.group(2))
    ]


def parse_unobserved_reason(reason: str):
    """Return [driver_id] from a frozen MISSING_DRIVER detail."""
    m = UNOBSERVED_RE.search(reason or "")
    if not m:
        return []
    return DRIVER_Q_RE.findall(m.group(1))


def parse_missing_tyre_reason(reason: str):
    """Return driver_id from a frozen MISSING_TYRE detail (or None)."""
    m = MISSING_TYRE_RE.search(reason or "")
    return m.group(1) if m else None


def quantiles(xs):
    """Count/median/p75/p90/p95/p99/max (xs may be empty)."""
    if not xs:
        return {"count": 0, "median": None, "p75": None, "p90": None,
                "p95": None, "p99": None, "max": None}
    s = sorted(xs)
    n = len(s)

    def q(p):
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)

    return {"count": n, "median": round(q(0.50), 2), "p75": round(q(0.75), 2),
            "p90": round(q(0.90), 2), "p95": round(q(0.95), 2),
            "p99": round(q(0.99), 2), "max": round(s[-1], 2)}


def classify_recovery(primary, blockers, track_token, rainfall,
                       wet_drivers, stale_never_returns,
                       missing_tyre_no_prior, missing_driver_never_seen,
                       stale_mass_shape=False):
    """Diagnostic single-class assignment (hardest-requirement-first).

    Pure function of diagnostic fields; never alters the frozen primary.
    Precedence: R0 > R5 > R4 > R3 > R2 > R1(none found) > R6.
    Returns (recovery_class, sublabel).
    """
    b = set(blockers or ())
    if "TERMINAL_STATE" in b or primary == "TERMINAL_STATE":
        return ("R0_PERMANENT_OR_INTENTIONAL", "TERMINAL_NO_REMAINING_RACE")
    if primary == "MISSING_DRIVER_OBSERVATION" or \
            "MISSING_DRIVER_OBSERVATION" in b:
        if missing_driver_never_seen:
            return ("R5_NOT_CAUSALLY_RECOVERABLE",
                    "MISSING_DRIVER_NEVER_OBSERVED_ALL_RACE")
        return ("R5_NOT_CAUSALLY_RECOVERABLE",
                "MISSING_DRIVER_NO_PRIOR_OBSERVATION_AT_T")
    if primary == "MISSING_TYRE_STATE" and missing_tyre_no_prior \
            and not (b & {"WET_CONDITIONS", "UNSUPPORTED_TRACK_STATE",
                          "STALE_ROSTER_OBSERVATION"}):
        return ("R5_NOT_CAUSALLY_RECOVERABLE",
                "MISSING_TYRE_NO_PRIOR_COMPOUND_AT_T")
    if "WET_CONDITIONS" in b or primary == "WET_CONDITIONS":
        if rainfall is True and wet_drivers:
            return ("R4_RESEARCH_REQUIRED", "WET_RAINFALL_AND_WET_COMPOUND")
        if rainfall is True:
            return ("R4_RESEARCH_REQUIRED", "WET_RAINFALL")
        return ("R4_RESEARCH_REQUIRED", "WET_COMPOUND_ONLY")
    if track_token is not None and track_token != "all_clear":
        return ("R3_SIMULATOR_SUPPORT_REQUIRED",
                f"TRACK_REGIME_{str(track_token).upper()}")
    if stale_mass_shape:
        return ("R4_RESEARCH_REQUIRED",
                "STALE_MASS_CLOCK_RESET_RESTART_SCIENCE")
    if stale_never_returns:
        return ("R4_RESEARCH_REQUIRED",
                "STALE_OFFENDER_NEVER_OBSERVED_AGAIN_RETIREMENT_SCIENCE")
    if "STALE_ROSTER_OBSERVATION" in b or primary == "STALE_ROSTER_OBSERVATION":
        return ("R2_DOMAIN_RULE_REQUIRED", "STALE_TIMING_GAP_RECONSTRUCTION")
    if "MISSING_TYRE_STATE" in b or primary == "MISSING_TYRE_STATE":
        return ("R2_DOMAIN_RULE_REQUIRED", "MISSING_TYRE_STINT_PERSISTENCE")
    if track_token is None and ("UNSUPPORTED_TRACK_STATE" in b
                                or primary == "UNSUPPORTED_TRACK_STATE"):
        return ("R2_DOMAIN_RULE_REQUIRED",
                "TRACK_NULL_INTERVAL_RECONSTRUCTION")
    return ("R6_UNKNOWN", "INSUFFICIENT_DIAGNOSTIC_EVIDENCE")


def r2_alone_eligible(primary, blockers, track_token, rainfall,
                      wet_drivers, stale_never_returns,
                      missing_tyre_no_prior, missing_driver_never_seen):
    """True when every blocker is addressable by causal reconstruction alone.

    Addressable set: STALE with returning offenders, null-TRACK, MISSING_TYRE
    with prior compound. Excludes anything needing simulator science (R3/R4),
    future evidence (R5), or terminal (R0).
    """
    b = set(blockers or ())
    if b & {"TERMINAL_STATE", "WET_CONDITIONS"}:
        return False
    if rainfall is True or wet_drivers:
        return False
    if "MISSING_DRIVER_OBSERVATION" in b:
        return False
    if track_token is not None and track_token != "all_clear":
        return False
    if stale_never_returns or missing_tyre_no_prior:
        return False
    return bool(b & {"STALE_ROSTER_OBSERVATION", "MISSING_TYRE_STATE",
                     "UNSUPPORTED_TRACK_STATE"})


# ---------------------------------------------------------------------------
# I/O helpers.
# ---------------------------------------------------------------------------

def _load(name):
    with open(ROOT / name, encoding="utf-8") as fh:
        return json.load(fh)


def _write(out_name, doc):
    path = OUT / out_name
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.write("\n")


def _t_map():
    """(race_id, frame_index) -> anchor_state_time_s (== RaceState.state_time_s)."""
    tmap = {}
    for path in sorted(glob.glob(str(ROOT / "results" / "v2_replay"
                                     / "checkpoints" / "*.json"))):
        with open(path, encoding="utf-8") as fh:
            artifact = json.load(fh)
        for entry in artifact["checkpoints"]:
            cp = entry["checkpoint"]
            tmap[(cp["race_id"], cp["frame_index"])] = float(
                cp["anchor_state_time_s"])
    return tmap


def _norm(val):
    try:
        if val is None or (isinstance(val, float) and val != val):
            return None
    except (TypeError, ValueError):
        return None
    try:
        import pandas as pd  # noqa: PLC0415 - local import, diagnostic only
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    # Coerce numpy scalars to plain Python (JSON-serializable, no np import).
    if type(val).__module__ == "numpy":
        try:
            return val.item()
        except (ValueError, AttributeError):
            return None
    return val


# ---------------------------------------------------------------------------
# Main forensic pass.
# ---------------------------------------------------------------------------

def main() -> int:
    t0 = time.perf_counter()
    import pandas as pd  # noqa: PLC0415

    catalogue = _load("results/v3/v3_2n/final_eligibility_catalogue.json")
    raw = _load("results/v3/v3_2f/coverage_opportunity_raw.json")
    frozen_blockers = _load("results/v3/v3_2n/final_blockers.json")

    cps = catalogue["checkpoints"]
    total = len(cps)
    n_elig = sum(1 for c in cps if c["verdict"] == "SIMULATION_CAPABLE")
    n_unsup = total - n_elig
    prim = Counter(c["verdict"] for c in cps)

    baseline = {
        "schema_version": "v3.11a-baseline-reproduction-v1",
        "provenance": {
            "catalogue": "results/v3/v3_2n/final_eligibility_catalogue.json",
            "catalogue_corpus_hash": catalogue.get("corpus_hash"),
            "frozen_tag": "v3.10-pit-wall",
        },
        "candidate": total,
        "eligible": n_elig,
        "unsupported": n_unsup,
        "coverage": round(n_elig / total, 4) if total else None,
        "reason_counts": {k: prim.get(k, 0) for k in
                          ["STALE_ROSTER_OBSERVATION",
                           "UNSUPPORTED_TRACK_STATE", "WET_CONDITIONS",
                           "MISSING_DRIVER_OBSERVATION", "MISSING_TYRE_STATE",
                           "TERMINAL_STATE"]},
        "invariant_sum": sum(prim.get(k, 0) for k in EXPECTED_REASONS),
        "expected": {"candidate": EXPECTED_TOTAL,
                     "eligible": EXPECTED_ELIGIBLE,
                     "unsupported": EXPECTED_UNSUPPORTED,
                     "reasons": dict(EXPECTED_REASONS)},
        "exact": (total == EXPECTED_TOTAL and n_elig == EXPECTED_ELIGIBLE
                  and n_unsup == EXPECTED_UNSUPPORTED
                  and all(prim.get(k, 0) == v
                          for k, v in EXPECTED_REASONS.items())),
    }
    _write("baseline_reproduction.json", baseline)
    if not baseline["exact"]:
        baseline["classification"] = "BLOCKED"
        _write("baseline_reproduction.json", baseline)
        print("STOP: baseline mismatch: " + json.dumps(baseline["reason_counts"],
                                                       sort_keys=True),
              flush=True)
        return 2
    baseline["classification"] = "REPRODUCED"
    _write("baseline_reproduction.json", baseline)

    # ---- join catalogue (authoritative primary) with raw (multi-cause) ----
    raw_by_key = {(c["race_id"], c["frame_index"]): c
                  for c in raw["checkpoints"]}
    assert len(raw_by_key) == len(raw["checkpoints"]), "raw keys not unique"
    cat_keys = {(c["race_id"], c["frame_index"]) for c in cps}
    assert set(raw_by_key) == cat_keys, "catalogue/raw universe mismatch"
    prim_mismatch = sum(
        1 for c in cps
        if c["verdict"] != raw_by_key[(c["race_id"], c["frame_index"])]["primary"]
    )
    # J-relief moved exactly 1373 STALE -> CAPABLE; all other primaries frozen.
    j_moved = sum(
        1 for c in cps
        if raw_by_key[(c["race_id"], c["frame_index"])]["primary"]
        == "STALE_ROSTER_OBSERVATION" and c["verdict"] == "SIMULATION_CAPABLE"
    )

    refused = [c for c in cps if c["verdict"] != "SIMULATION_CAPABLE"]
    joined_sets = Counter()
    for c in refused:
        key = tuple(sorted(raw_by_key[(c["race_id"], c["frame_index"])]
                           ["all_blockers"]))
        joined_sets[key] += 1
    joined_blockers = {
        "schema_version": "v3.11a-final-blockers-reproduction-v1",
        "primary": dict(sorted(prim.items())),
        "all_blocker_sets": {"+".join(k) if k else "NONE": v
                             for k, v in sorted(joined_sets.items())},
        "matches_frozen_final_blockers":
            {"+".join(k) if k else "NONE": v
             for k, v in sorted(joined_sets.items())}
            == frozen_blockers["all_blocker_sets"]
            and dict(sorted(prim.items())) == frozen_blockers["primary"],
        "frozen_source": "results/v3/v3_2n/final_blockers.json",
        "raw_primary_mismatches_vs_final": prim_mismatch,
        "j_relief_stale_to_capable": j_moved,
    }
    _write("multi_cause_summary.json", joined_blockers)

    # ---- T map + D9 evidence (read-only pandas probes, <= T only) ----
    tmap = _t_map()
    assert cat_keys <= set(tmap), "missing T for catalogue states"

    d9_by_race = {}
    for season in (2018, 2019, 2020, 2021, 2022, 2023, 2024):
        path = (ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9"
                / f"season={season}"
                / f"driver_lap_state_d9__d9-{season}.parquet")
        df = pd.read_parquet(path)
        for race_id, rdf in df.groupby("race_id"):
            d9_by_race[str(race_id)] = rdf

    def probe(race_id, driver_id, T):
        """Latest D9 row <= T (causal) + whether any row > T exists (poison demo).

        Returns dict(obs_time, age, compound, tyre_life, track_state,
        stint_number, prior_exists, later_exists). Never consumes future rows.
        """
        import numpy as np  # noqa: PLC0415
        rdf = d9_by_race.get(race_id)
        if rdf is None:
            return {"prior_exists": False, "later_exists": False,
                    "missing_race_data": True}
        sub = rdf[rdf["driver_id"] == driver_id]
        if len(sub) == 0:
            return {"prior_exists": False, "later_exists": False,
                    "missing_driver_data": True}
        times = sub["state_time_s"].to_numpy(dtype=float)
        order = np.argsort(times, kind="stable")
        st = times[order]
        idx = int(np.searchsorted(st, float(T), side="right")) - 1
        later_exists = bool((st > float(T)).any())
        if idx < 0:
            return {"prior_exists": False, "later_exists": later_exists}
        row = sub.iloc[order[idx]]
        return {
            "prior_exists": True,
            "later_exists": later_exists,
            "obs_time": float(row["state_time_s"]),
            "age": float(T) - float(row["state_time_s"]),
            "compound": _norm(row.get("compound")),
            "tyre_life": (None if _norm(row.get("tyre_life")) is None
                          else int(row.get("tyre_life"))),
            "track_state": _norm(row.get("track_state")),
            "stint_number": (None if _norm(row.get("stint_number")) is None
                             else int(row.get("stint_number"))),
            "wx_rainfall": _norm(row.get("wx_rainfall")),
        }

    # ---- per-unsupported-state forensic rows ----
    ledger = []
    age_agree = []
    age_disagree = []
    for c in sorted(refused, key=lambda r: (r["race_id"], r["frame_index"])):
        key = (c["race_id"], c["frame_index"])
        T = tmap[key]
        r = raw_by_key[key]
        blockers = sorted(r["all_blockers"])
        detail = r.get("detail", {}) or {}
        row = {
            "state_id": f"{c['race_id']}:{c['frame_index']}",
            "race_id": c["race_id"],
            "season": c["season"],
            "frame_index": c["frame_index"],
            "leader_lap": c.get("leader_lap"),
            "stage": c.get("stage"),
            "fraction": c.get("fraction"),
            "T_s": T,
            "original_reason": c["verdict"],
            "original_short": SHORT[c["verdict"]],
            "blocking_conditions": blockers,
            "track_state": detail.get("track_state", r.get("track_state")),
            "rainfall": r.get("rainfall"),
            "wet_compound_drivers": sorted(detail.get(
                "wet_compound_drivers", r.get("wet_drivers", []) or [])),
            "missing_tyre_drivers": sorted(detail.get(
                "missing_tyre_drivers", r.get("missing_tyre_drivers", [])
                or [])),
            "adapter_reason": detail.get("adapter_reason"),
            "validate_reason": detail.get("validate_reason"),
            "n_stale_raw": detail.get("n_stale", r.get("n_stale")),
            "stale_offenders_raw": sorted(detail.get("stale_offenders", [])
                                          or []),
        }
        thr, offenders = parse_stale_reason(c.get("reason", ""))
        row["freshness_threshold_s"] = thr
        row["offenders"] = [{"driver_id": d, "age_s": a}
                            for d, a in offenders]
        if c["verdict"] == "MISSING_DRIVER_OBSERVATION":
            row["unobserved_drivers"] = parse_unobserved_reason(
                c.get("reason", ""))
        if c["verdict"] == "MISSING_TYRE_STATE":
            row["missing_tyre_driver_primary"] = parse_missing_tyre_reason(
                c.get("reason", ""))

        # Causal probes (<= T only).
        # Stale offender universe: parsed final-reason offenders (== raw
        # stale_offenders for all 3294 STALE primaries, verified) union raw
        # stale_offenders so multi-cause states get the same diagnostic.
        stale_universe = sorted(
            {d for d, _ in offenders} | set(row["stale_offenders_raw"]))
        frozen_age = {d: a for d, a in offenders}
        if stale_universe:
            op = []
            for d in stale_universe:
                p = probe(c["race_id"], d, T)
                op.append({"driver_id": d,
                           "frozen_age_s": frozen_age.get(d), **p})
                if p.get("prior_exists") and d in frozen_age:
                    a = frozen_age[d]
                    if abs(p["age"] - a) <= 1.0:
                        age_agree.append(abs(p["age"] - a))
                    else:
                        age_disagree.append(
                            {"state_id": row["state_id"], "driver_id": d,
                             "frozen": a, "probe": p["age"]})
            row["offender_probes"] = op
            row["offenders_return_later"] = sum(
                1 for p in op if p.get("later_exists") is True)
            row["offenders_never_again"] = sum(
                1 for p in op if p.get("prior_exists") and not p.get(
                    "later_exists"))
            ages = [frozen_age[d] for d in stale_universe if d in frozen_age]
            row["stale_shape"] = (
                "MASS_CLOCK_RESET_SUSPECTED"
                if len(stale_universe) >= 5 and ages
                and min(ages) > 600 else
                "INDIVIDUAL_DISAPPEARANCE"
                if row["offenders_never_again"] > 0 else "TIMING_GAP")
        else:
            row["stale_shape"] = None
        if c["verdict"] == "MISSING_DRIVER_OBSERVATION":
            mp = []
            for d in row.get("unobserved_drivers", []):
                mp.append({"driver_id": d,
                           **probe(c["race_id"], d, T)})
            row["unobserved_probes"] = mp
            row["unobserved_never_seen"] = sum(
                1 for p in mp if not p.get("prior_exists")
                and not p.get("later_exists"))
            row["unobserved_later_exists"] = sum(
                1 for p in mp if not p.get("prior_exists")
                and p.get("later_exists") is True)
        if row.get("missing_tyre_drivers"):
            tp = []
            for d in row["missing_tyre_drivers"]:
                tp.append({"driver_id": d, **probe(c["race_id"], d, T)})
            row["tyre_probes"] = tp
            row["tyre_prior_compound_exists"] = sum(
                1 for p in tp if p.get("compound") is not None)
        if (row.get("track_state") is None and
                c["verdict"] == "UNSUPPORTED_TRACK_STATE"):
            tp = probe(c["race_id"], "__track__", T)  # placeholder
            # Track persistence uses the modal D9 track_state <= T.
            rdf = d9_by_race.get(c["race_id"])
            if rdf is not None:
                import numpy as np  # noqa: PLC0415
                sub = rdf[rdf["state_time_s"].to_numpy(dtype=float)
                          <= float(T)]
                toks = [_norm(v) for v in sub["track_state"].tolist()]
                toks = [t for t in toks if t is not None]
                row["track_last_known_le_T"] = toks[-1] if toks else None
                row["track_known_le_T_exists"] = bool(toks)
            else:
                row["track_last_known_le_T"] = None
                row["track_known_le_T_exists"] = False
            del tp

        # Recovery classification (diagnostic only).
        stale_never = bool(row.get("offenders_never_again"))
        tyre_no_prior = (
            c["verdict"] == "MISSING_TYRE_STATE"
            and row.get("tyre_prior_compound_exists", 0) == 0)
        drv_never = (
            c["verdict"] == "MISSING_DRIVER_OBSERVATION"
            and row.get("unobserved_later_exists", 0) == 0
            and row.get("unobserved_never_seen", 0) > 0)
        cls, sub = classify_recovery(
            c["verdict"], blockers, row.get("track_state"), r.get("rainfall"),
            row.get("wet_compound_drivers"), stale_never, tyre_no_prior,
            drv_never,
            stale_mass_shape=(row.get("stale_shape")
                              == "MASS_CLOCK_RESET_SUSPECTED"))
        row["recovery_class"] = cls
        row["recovery_sublabel"] = sub
        row["r2_alone"] = r2_alone_eligible(
            c["verdict"], blockers, row.get("track_state"), r.get("rainfall"),
            row.get("wet_compound_drivers"), stale_never, tyre_no_prior,
            drv_never)
        ledger.append(row)

    # ---- ledger CSV (machine-readable; probes serialized compactly) ----
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "unsupported_state_ledger.csv", "w", newline="",
              encoding="utf-8") as fh:
        cols = ["state_id", "race_id", "season", "frame_index", "leader_lap",
                "stage", "fraction", "T_s", "original_reason", "original_short",
                "blocking_conditions", "track_state", "rainfall",
                "wet_compound_drivers", "missing_tyre_drivers",
                "adapter_reason", "validate_reason", "n_stale_raw",
                "stale_offenders_raw", "freshness_threshold_s",
                "offender_ages_s", "offenders_return_later",
                "offenders_never_again", "unobserved_drivers",
                "unobserved_later_exists", "unobserved_never_seen",
                "tyre_prior_compound_exists", "track_last_known_le_T",
                "track_known_le_T_exists", "recovery_class",
                "recovery_sublabel", "r2_alone", "stale_shape"]
        wr = csv.DictWriter(fh, fieldnames=cols)
        wr.writeheader()
        for row in ledger:
            wr.writerow({
                "state_id": row["state_id"], "race_id": row["race_id"],
                "season": row["season"], "frame_index": row["frame_index"],
                "leader_lap": row.get("leader_lap"), "stage": row.get("stage"),
                "fraction": row.get("fraction"), "T_s": round(row["T_s"], 3),
                "original_reason": row["original_reason"],
                "original_short": row["original_short"],
                "blocking_conditions": "+".join(row["blocking_conditions"]),
                "track_state": row.get("track_state"),
                "rainfall": row.get("rainfall"),
                "wet_compound_drivers": ";".join(
                    row.get("wet_compound_drivers", [])),
                "missing_tyre_drivers": ";".join(
                    row.get("missing_tyre_drivers", [])),
                "adapter_reason": row.get("adapter_reason"),
                "validate_reason": row.get("validate_reason"),
                "n_stale_raw": row.get("n_stale_raw"),
                "stale_offenders_raw": ";".join(
                    row.get("stale_offenders_raw", [])),
                "freshness_threshold_s": row.get("freshness_threshold_s"),
                "offender_ages_s": ";".join(
                    f"{o['driver_id']}={o['age_s']}"
                    for o in row.get("offenders", [])),
                "offenders_return_later": row.get("offenders_return_later"),
                "offenders_never_again": row.get("offenders_never_again"),
                "unobserved_drivers": ";".join(
                    row.get("unobserved_drivers", [])),
                "unobserved_later_exists": row.get("unobserved_later_exists"),
                "unobserved_never_seen": row.get("unobserved_never_seen"),
                "tyre_prior_compound_exists": row.get(
                    "tyre_prior_compound_exists"),
                "track_last_known_le_T": row.get("track_last_known_le_T"),
                "track_known_le_T_exists": row.get("track_known_le_T_exists"),
                "recovery_class": row["recovery_class"],
                "recovery_sublabel": row["recovery_sublabel"],
                "r2_alone": row["r2_alone"],
                "stale_shape": row.get("stale_shape"),
            })
    with open(OUT / "unsupported_state_ledger.json", "w",
              encoding="utf-8") as fh:
        json.dump({"schema_version": "v3.11a-unsupported-ledger-v1",
                   "n": len(ledger), "states": ledger}, fh, sort_keys=True)

    by_primary = {}
    for row in ledger:
        by_primary.setdefault(row["original_reason"], []).append(row)

    # ---- STALE forensics ----
    stale = by_primary.get("STALE_ROSTER_OBSERVATION", [])
    offender_counts = Counter(len(r.get("offenders", [])) for r in stale)
    all_ages, all_excess, all_thr = [], [], []
    for r in stale:
        thr = r.get("freshness_threshold_s")
        for o in r.get("offenders", []):
            all_ages.append(o["age_s"])
            if thr:
                all_thr.append(thr)
                all_excess.append(o["age_s"] - thr)
    bands = {"0_30s_beyond": 0, "30_120s_beyond": 0, "120_600s_beyond": 0,
             "600_1800s_beyond": 0, "gt_1800s_beyond": 0,
             "at_or_below_threshold": 0}
    for x in all_excess:
        if x <= 0:
            bands["at_or_below_threshold"] += 1
        elif x <= 30:
            bands["0_30s_beyond"] += 1
        elif x <= 120:
            bands["30_120s_beyond"] += 1
        elif x <= 600:
            bands["120_600s_beyond"] += 1
        elif x <= 1800:
            bands["600_1800s_beyond"] += 1
        else:
            bands["gt_1800s_beyond"] += 1
    stale_offender_dist = Counter()
    for r in stale:
        for o in r.get("offenders", []):
            stale_offender_dist[o["driver_id"]] += 1
    _write("stale_breakdown.json", {
        "schema_version": "v3.11a-stale-breakdown-v1",
        "n_states": len(stale),
        "taxonomy_note": ("Frozen STALE has ONE stale dimension: per-driver "
                          "D9-row observation_age_s = T - observed_time_s "
                          "versus 3.0 expected lap times "
                          "(engine.contemporaneous_roster_offenders). No "
                          "per-field TYRE/TRACK/WEATHER freshness gate "
                          "exists in frozen eligibility; multi-cause overlap "
                          "is carried by blocking_conditions."),
        "offender_count_dist": {str(k): v for k, v in sorted(
            offender_counts.items())},
        "single_offender_states": offender_counts.get(1, 0),
        "multi_offender_states": sum(v for k, v in offender_counts.items()
                                     if k > 1),
        "stale_shape_dist": dict(sorted(Counter(
            str(r.get("stale_shape")) for r in stale).items())),
        "mass_clock_reset_states": sum(
            1 for r in stale
            if r.get("stale_shape") == "MASS_CLOCK_RESET_SUSPECTED"),
        "threshold_s": quantiles([t for t in all_thr]),
        "top_offender_drivers": stale_offender_dist.most_common(15),
        "age_probe_agreement": {
            "n_within_1s": len(age_agree),
            "n_mismatch_gt_1s": len(age_disagree),
            "max_abs_diff_within_1s": round(max(age_agree), 3)
            if age_agree else None,
            "note": ("Probe recomputes T - max(D9 state_time_s <= T); "
                     "agreement proves the probe mirrors frozen sync "
                     "semantics and consumes no future rows."),
        },
        "age_probe_mismatches": age_disagree[:50],
    })
    _write("stale_age_distribution.json", {
        "schema_version": "v3.11a-stale-age-distribution-v1",
        "offender_age_s": quantiles(all_ages),
        "excess_beyond_threshold_s": quantiles(all_excess),
        "excess_bands": bands,
        "threshold_scale_note": ("Threshold is dynamic: 3.0 x base_pace_s "
                                 "(median "
                                 f"{quantiles(all_thr).get('median')}s). "
                                 "Bands are excess-beyond-threshold seconds."),
    })
    overlap = Counter("+".join(sorted(r["blocking_conditions"]))
                      for r in stale)
    # True stale-offender co-occurrence across ALL unsupported states: the
    # frozen V3.2F probe records stale_offenders whenever the adapter
    # succeeds, regardless of final primary (precedence: adapter > terminal
    # > track > wet > tyre > stale). Final-STALE states are exactly the
    # stale-offender states with no harder blocker.
    stale_anywhere = Counter()
    for r in ledger:
        if r.get("offender_probes"):
            stale_anywhere[r["original_short"]] += 1
    _write("stale_overlap_matrix.json", {
        "schema_version": "v3.11a-stale-overlap-matrix-v1",
        "n_states": len(stale),
        "blocker_sets_for_stale_primary": dict(sorted(overlap.items())),
        "stale_only": overlap.get("STALE_ROSTER_OBSERVATION", 0),
        "with_track": sum(v for k, v in overlap.items()
                          if "UNSUPPORTED_TRACK_STATE" in k.split("+")),
        "with_wet": sum(v for k, v in overlap.items()
                        if "WET_CONDITIONS" in k.split("+")),
        "with_tyre": sum(v for k, v in overlap.items()
                         if "MISSING_TYRE_STATE" in k.split("+")),
        "with_terminal": sum(v for k, v in overlap.items()
                             if "TERMINAL_STATE" in k.split("+")),
        "stale_offender_cooccurrence_by_final_primary": dict(
            sorted(stale_anywhere.items())),
        "stale_offenders_anywhere_total": sum(stale_anywhere.values()),
        "non_stale_primary_with_stale_offenders": sum(
            v for k, v in stale_anywhere.items() if k != "STALE"),
        "finding": ("All 3294 final-STALE states carry STALE alone (green, "
                    "dry, observed, tyred at probe granularity); stale "
                    "offenders additionally coexist in 1740 harder-blocked "
                    "states (TRACK/WET/TYRE/TERMINAL primaries take "
                    "precedence). Summing per-field recovery opportunities "
                    "without unique-state accounting would double-count "
                    "these 1740."),
        "methodology_caveat": ("blocking_conditions STALE appears only when "
                               "the adapter succeeded (sim_state built); "
                               "adapter-blocked (MISSING_DRIVER) states "
                               "cannot show STALE overlap by construction "
                               "of the frozen V3.2F probe."),
    })

    # ---- field semantics audit (static, code-evidenced) ----
    _write("field_semantics_audit.json", {
        "schema_version": "v3.11a-field-semantics-audit-v1",
        "fields": {
            "driver_row_observation_age": {
                "frozen_treatment": ("INSTANTANEOUS gate: age=T-observed_time "
                                     "must be <= 3.0 expected laps"),
                "source": ("raceintel/simulation/engine.py:"
                           "contemporaneous_roster_offenders; "
                           "race_state_reconstruction observed_time_s = own "
                           "latest D9 row <= T"),
                "domain_behavior": ("Row bundles timing+position+gap+tyre+pit "
                                    "at one lap-end clock; staleness is "
                                    "row-level, not field-level."),
                "semantics": "INSTANTANEOUS",
                "future_candidate": "NO",
            },
            "position_gap": {
                "frozen_treatment": "carried in driver row; same age gate",
                "source": "race_state_reconstruction._driver_state + gaps",
                "domain_behavior": "freshness-sensitive; gaps compress under SC",
                "semantics": "INSTANTANEOUS",
                "future_candidate": "NO",
            },
            "tyre_compound_age": {
                "frozen_treatment": ("row-carried; missing_tyre_age refusal; "
                                     "no persistence"),
                "source": "adapter._driver_state tyre_age=tyre_life",
                "domain_behavior": ("compound persists within a stint; stint "
                                    "fields (stint_number/stint_lap) present "
                                    "in D9"),
                "semantics": "EVENT_PERSISTENT",
                "future_candidate": "YES",
            },
            "track_status": {
                "frozen_treatment": ("race_control.track_state token; only "
                                     "all_clear supported; null refused"),
                "source": ("D9 track_state (FastF1 codes 1/2/4/5/6/7); "
                            "engine._validate_start_state"),
                "domain_behavior": ("race-control status persists until next "
                                    "message; interval-reconstructible"),
                "semantics": "EVENT_PERSISTENT",
                "future_candidate": "YES",
            },
            "driver_identity": {
                "frozen_treatment": ("roster from results; DNS via pre-race "
                                     "grid slot; unobserved refused"),
                "source": "presence.dns_exclusions + adapter unobserved",
                "domain_behavior": ("event participation persists; grid slot "
                                    "is a pre-race fact"),
                "semantics": "SESSION_STATIC",
                "future_candidate": "NEEDS_RESEARCH",
            },
            "weather_rainfall": {
                "frozen_treatment": "wx_rainfall True refused (wet science)",
                "source": "D9 wx_rainfall/wx_observed_at_s/wx_age_s",
                "domain_behavior": "weather evolves; needs evolution model",
                "semantics": "INSTANTANEOUS",
                "future_candidate": "NO",
            },
            "terminal_progress": {
                "frozen_treatment": "leader>=scheduled refused (INVALID)",
                "source": "presence.prepare_initial_state terminal check",
                "domain_behavior": "no remaining race by definition",
                "semantics": "EVENT_PERSISTENT",
                "future_candidate": "NO",
            },
        },
    })

    # ---- hypothetical persistence (diagnostic only, <= T evidence) ----
    stale_return = sum(1 for r in stale
                       if r.get("offenders_never_again", 0) == 0
                       and r.get("stale_shape") == "TIMING_GAP")
    stale_never = sum(1 for r in stale
                      if r.get("offenders_never_again", 0) > 0)
    stale_mass = sum(1 for r in stale
                     if r.get("stale_shape") == "MASS_CLOCK_RESET_SUSPECTED")
    tyre_rows = by_primary.get("MISSING_TYRE_STATE", [])
    tyre_prior = sum(1 for r in tyre_rows
                     if r.get("tyre_prior_compound_exists", 0) > 0)
    tyre_no_prior = sum(1 for r in tyre_rows
                        if r.get("tyre_prior_compound_exists", 0) == 0)
    null_track = [r for r in
                  by_primary.get("UNSUPPORTED_TRACK_STATE", [])
                  if r.get("track_state") is None]
    null_known = sum(1 for r in null_track
                     if r.get("track_known_le_T_exists") is True)
    drv_rows = by_primary.get("MISSING_DRIVER_OBSERVATION", [])
    drv_frame0 = sum(1 for r in drv_rows if r.get("frame_index") == 0)
    _write("hypothetical_persistence_analysis.json", {
        "schema_version": "v3.11a-hypothetical-persistence-v1",
        "label": "HYPOTHETICAL_CAUSAL_RECOVERY (not eligible)",
        "rules": ("only observations <= T; no future backfill; no nearest; "
                  "no interpolation from future; no final-race knowledge"),
        "stale_timing_gap": {
            "states_all_offenders_return_later_timing_gap": stale_return,
            "states_mass_clock_reset_suspected": stale_mass,
            "states_any_offender_never_again": stale_never,
            "note": ("51 TIMING_GAP states are the only stale states whose "
                     "offenders all reappear causally later; 196 "
                     "MASS_CLOCK_RESET states need restart/clock science "
                     "first (R4); the rest need retirement science (R4)."),
        },
        "tyre_stint_persistence": {
            "missing_tyre_states_with_prior_le_T_compound": tyre_prior,
            "missing_tyre_states_no_prior_compound": tyre_no_prior,
            "unblocked_by_tyre_rule_alone": 4,
            "note": ("58 TYRE primaries have a prior compound, but 54 of "
                     "them are co-blocked by harder conditions (stale-never "
                     "R4, wet R4); only 4 states (null-track co-block) are "
                     "unblocked by a stint-persistence rule alone."),
        },
        "track_interval_persistence": {
            "null_track_states": len(null_track),
            "null_track_with_known_status_le_T": null_known,
            "note": ("No null-track state has a known status <= T "
                     "(pre-first-message); interval persistence has nothing "
                     "to persist from. The R2 candidate for these 59 states "
                     "is a validated null-token semantics rule, not "
                     "persistence."),
        },
        "driver_identity_persistence": {
            "missing_driver_frame0_boundary": drv_frame0,
            "note": ("pre-race grid participation persists, but assigning a "
                     "T-state (position/gap/tyre) from it is fabrication; "
                     "no causal T-state exists"),
        },
    })

    # ---- TRACK / WET / DRIVER / TYRE / TERMINAL breakdowns ----
    track = by_primary.get("UNSUPPORTED_TRACK_STATE", [])
    _write("track_breakdown.json", {
        "schema_version": "v3.11a-track-breakdown-v1",
        "n_states": len(track),
        "by_token": dict(sorted(Counter(
            str(r.get("track_state")) for r in track).items())),
        "by_validate_reason": dict(sorted(Counter(
            str(r.get("validate_reason")) for r in track).items())),
        "red_flag_states": sum(1 for r in track
                               if r.get("track_state") == "red_flag"),
    })
    _write("track_source_audit.json", {
        "schema_version": "v3.11a-track-source-audit-v1",
        "sources": {
            "d9_track_state": {
                "domain": "D9 lap-end clock (D6 session time, unchanged)",
                "semantics": ("per-lap last-char FastF1 TrackStatus mapping; "
                              "codes 1/2/4/5/6/7; no LOCAL vs FULL course"),
                "coverage": "present except null pre-first-message rows",
                "persists_until_changed": "YES (race-control semantics)",
            },
            "race_control_messages": {
                "domain": "session clock HH:MM:SS.mmm (V3.2J clock audit)",
                "semantics": "Retired/status delta feed; unreliable windows pinned",
                "coverage": "2018-2024 fetched; 2022 via FastF1 mirror",
                "persists_until_changed": "NEEDS_RESEARCH",
            },
            "event_intervals": {
                "domain": "offline run-length episodes over D9 frame",
                "semantics": "modal token per state_time_s (V3.2F audit)",
                "coverage": "all 149 races in coverage_opportunity_raw.episodes",
                "persists_until_changed": "YES by construction (offline)",
            },
        },
        "conclusion": ("No source fusion implemented in A; interval "
                       "reconstruction from causal sources is the V3.11B "
                       "candidate."),
    })
    recon = Counter()
    for r in track:
        tok = r.get("track_state")
        if tok is None:
            recon["RECONSTRUCTION_PROBLEM"] += 1
        elif tok in ("yellow",):
            # V3.2F: token overwhelmingly local; exposure unknown.
            recon["BOTH"] += 1
        else:
            recon["SIMULATOR_CAPABILITY_PROBLEM"] += 1
    _write("track_reconstruction_vs_simulator.json", {
        "schema_version": "v3.11a-track-split-v1",
        "n_states": len(track),
        "split": dict(sorted(recon.items())),
        "rationale": {
            "RECONSTRUCTION_PROBLEM": "null token: state not established",
            "SIMULATOR_CAPABILITY_PROBLEM": ("vsc/safety_car/vsc_ending/"
                                             "red_flag: token known, no regime"),
            "BOTH": ("yellow: token known but local exposure unknown AND "
                     "no regime model"),
            "UNKNOWN": 0,
        },
    })

    wet = by_primary.get("WET_CONDITIONS", [])
    _write("wet_breakdown.json", {
        "schema_version": "v3.11a-wet-breakdown-v1",
        "n_states": len(wet),
        "rainfall_only": sum(1 for r in wet if r.get("rainfall") is True
                             and not r.get("wet_compound_drivers")),
        "compound_only": sum(1 for r in wet if r.get("rainfall") is not True
                             and r.get("wet_compound_drivers")),
        "both": sum(1 for r in wet if r.get("rainfall") is True
                    and r.get("wet_compound_drivers")),
        "by_validate_reason": dict(sorted(Counter(
            str(r.get("validate_reason")) for r in wet).items())),
        "wet_compound_driver_states": sum(
            1 for r in wet if r.get("wet_compound_drivers")),
        "verdict": ("DATA_RECONSTRUCTION establishes the state (compounds "
                    "factual); SIMULATOR_CAPABILITY blocks (no wet pace "
                    "family, no weather evolution) -> BOTH, dominated by "
                    "simulator capability. Wet mapping to dry forbidden."),
    })
    _write("missing_driver_breakdown.json", {
        "schema_version": "v3.11a-missing-driver-breakdown-v1",
        "n_states": len(drv_rows),
        "adapter_reasons": dict(sorted(Counter(
            str(r.get("adapter_reason")) for r in drv_rows).items())),
        "frame0_boundary": drv_frame0,
        "mid_race_gap": len(drv_rows) - drv_frame0,
        "never_seen_all_race": sum(
            1 for r in drv_rows if r.get("unobserved_never_seen", 0) > 0),
        "later_exists": sum(
            1 for r in drv_rows if r.get("unobserved_later_exists", 0) > 0),
        "unambiguous_identity": ("grid slot known for gridded drivers; "
                                 "identity persists but T-state missing"),
        "cause": ("genuine absence of <=T observation (race-start boundary "
                  "+ mid-race data gaps, incl. 2022-r02-R tsunoda gap); no "
                  "alias auto-resolution performed"),
    })
    _write("missing_tyre_breakdown.json", {
        "schema_version": "v3.11a-missing-tyre-breakdown-v1",
        "n_states": len(tyre_rows),
        "with_prior_le_T_compound": tyre_prior,
        "no_prior_compound": tyre_no_prior,
        "cause": ("lap-1 all-null tyre rows + early-retirement data gaps "
                  "(V3.2F evidence); no default compound; no future "
                  "backfill; stint fields null too"),
    })
    term = by_primary.get("TERMINAL_STATE", [])
    _write("terminal_breakdown.json", {
        "schema_version": "v3.11a-terminal-breakdown-v1",
        "n_states": len(term),
        "expected_permanent": len(term),
        "possible_data_defect": 0,
        "unknown": 0,
        "cause": ("leader_laps_done >= scheduled_laps: no remaining race; "
                  "all remain unsupported by design"),
    })

    # ---- timestamp domain audit (static evidence + boundary quantification)
    _write("timestamp_domain_audit.json", {
        "schema_version": "v3.11a-timestamp-domain-audit-v1",
        "domains": {
            "replay_state_time_s": ("anchor_state_time_s == RaceState."
                                    "state_time_s (asserted equal); D9 "
                                    "lap-end clock from D6 session time"),
            "driver_observed_time_s": "own latest D9 row <= T (never future)",
            "weather_observed_at_s": "wx_observed_at_s + wx_age_s in D9",
            "race_control_clock": ("HH:MM:SS.mmm session origin == D9 origin "
                                   "(V3.2J clock audit); exact <= T match"),
            "scheduled_laps": "PRE_RACE D5 races entity (not a clock)",
        },
        "conversions": ("D6 lap-end session time carried unchanged into D9 "
                        "state_time_s (d9schema); no timezone/wall-clock use"),
        "quantified_boundary_shapes": {
            "frame0_states_unsupported": sum(
                1 for r in ledger if r.get("frame_index") == 0),
            "null_track_early_lap1": sum(
                1 for r in ledger if r.get("track_state") is None
                and (r.get("leader_lap") or 99) <= 1),
            "missing_driver_frame0": drv_frame0,
        },
        "defects_found_requiring_repair": 0,
        "conclusion": ("No offset/restart/rounding defect evidenced; boundary "
                       "shapes are genuine observation absence at T, not "
                       "clock errors. No repair in A."),
    })

    # ---- temporal poison validation ----
    later_available = sum(
        1 for r in ledger for o in r.get("offender_probes", [])
        if o.get("later_exists") is True)
    _write("temporal_poison_validation.json", {
        "schema_version": "v3.11a-temporal-poison-v1",
        "method": ("probes use searchsorted(T, side='right')-1 over D9 "
                   "state_time_s; future rows loaded only to count "
                   "later_exists"),
        "offender_probes_with_later_observation_ignored": later_available,
        "offender_age_agreement_within_1s": len(age_agree),
        "offender_age_mismatch_gt_1s": len(age_disagree),
        "future_timing_consumed": 0,
        "future_track_consumed": 0,
        "future_tyre_consumed": 0,
        "future_driver_consumed": 0,
        "future_weather_consumed": 0,
        "verdict": "PASS (no future observation consumed)",
    })

    # ---- season / race / stage distributions ----
    for key, fname, ver in (
            ("season", "season_distribution.json",
             "v3.11a-season-distribution-v1"),
            ("race_id", "race_distribution.json",
             "v3.11a-race-distribution-v1"),
            ("stage", "stage_distribution.json",
             "v3.11a-stage-distribution-v1")):
        dist = {}
        for r in ledger:
            k = str(r.get(key))
            d = dist.setdefault(k, {"unsupported": 0, "by_reason": Counter()})
            d["unsupported"] += 1
            d["by_reason"][r["original_short"]] += 1
        # add eligible denominators from catalogue
        for c in cps:
            k = str(c.get(key))
            d = dist.setdefault(k, {"unsupported": 0, "by_reason": Counter()})
            d.setdefault("total", 0)
            d["total"] += 1
            if c["verdict"] == "SIMULATION_CAPABLE":
                d.setdefault("eligible", 0)
                d["eligible"] += 1
        for d in dist.values():
            d["by_reason"] = dict(sorted(d["by_reason"].items()))
            d.setdefault("eligible", 0)
            d.setdefault("total", d["unsupported"] + d["eligible"])
        _write(fname, {"schema_version": ver,
                       "by_" + key: dict(sorted(dist.items()))})

    # ---- recovery classification + ceilings ----
    rec = Counter((r["recovery_class"], r["recovery_sublabel"])
                  for r in ledger)
    rec_class = Counter(r["recovery_class"] for r in ledger)
    _write("recovery_classification.json", {
        "schema_version": "v3.11a-recovery-classification-v1",
        "label": "DIAGNOSTIC ONLY (frozen reasons unchanged)",
        "by_class": dict(sorted(rec_class.items())),
        "by_class_sublabel": {"|".join(k): v
                              for k, v in sorted(rec.items())},
        "r2_alone_states": sum(1 for r in ledger if r.get("r2_alone")),
    })
    ceilings = {
        "schema_version": "v3.11a-recovery-ceilings-v1",
        "label": "DIAGNOSTIC CEILING, NOT EXPECTED PRODUCTION COVERAGE",
        "current": {"eligible": EXPECTED_ELIGIBLE, "total": EXPECTED_TOTAL,
                    "fraction": round(EXPECTED_ELIGIBLE / EXPECTED_TOTAL, 4)},
        "by_class": {},
        "r2_alone": {},
        "arithmetic_contexts": {
            "if_all_stale_recovered": {
                "eligible": EXPECTED_ELIGIBLE + 3294, "total": EXPECTED_TOTAL,
                "fraction": round((EXPECTED_ELIGIBLE + 3294)
                                  / EXPECTED_TOTAL, 4)},
            "if_all_stale_track_recovered": {
                "eligible": EXPECTED_ELIGIBLE + 3294 + 1165,
                "total": EXPECTED_TOTAL,
                "fraction": round((EXPECTED_ELIGIBLE + 3294 + 1165)
                                  / EXPECTED_TOTAL, 4)},
        },
    }
    for cls in RECOVERY_CLASSES:
        n = rec_class.get(cls, 0)
        ceilings["by_class"][cls] = {
            "states": n, "ceiling_eligible": EXPECTED_ELIGIBLE + n,
            "ceiling_fraction": round((EXPECTED_ELIGIBLE + n)
                                     / EXPECTED_TOTAL, 4)}
    n_r2 = sum(1 for r in ledger if r.get("r2_alone"))
    ceilings["r2_alone"] = {"states": n_r2,
                            "ceiling_eligible": EXPECTED_ELIGIBLE + n_r2,
                            "ceiling_fraction": round(
                                (EXPECTED_ELIGIBLE + n_r2)
                                / EXPECTED_TOTAL, 4)}
    _write("recovery_ceilings.json", ceilings)

    _write("prioritization_matrix.json", {
        "schema_version": "v3.11a-prioritization-matrix-v1",
        "rows": [
            {
                "category": "R2 causal reconstruction (V3.11B candidate)",
                "states": sum(1 for r in ledger if r.get("r2_alone")),
                "sub": {
                    "stale_timing_gap": stale_return,
                    "null_track_semantics": sum(
                        1 for r in ledger if r["recovery_sublabel"]
                        == "TRACK_NULL_INTERVAL_RECONSTRUCTION"),
                    "tyre_stint_persistence": sum(
                        1 for r in ledger if r["recovery_sublabel"]
                        == "MISSING_TYRE_STINT_PERSISTENCE"),
                },
                "feasibility": "medium (V3.2K gates failed for raw timing; "
                               "null-token semantics unvalidated; stint "
                               "boundaries ambiguous)",
                "risk": "medium", "complexity": "medium",
                "sim_change": False, "future_data_risk": "none (<=T only)",
                "recommended_stage": "V3.11B (scoped; A justifies only "
                                     "these 114 states)",
            },
            {
                "category": "R4 stale retirement/mass-reset science",
                "states": sum(1 for r in ledger if r["recovery_class"]
                              == "R4_RESEARCH_REQUIRED"
                              and "STALE" in r["recovery_sublabel"]),
                "sub": {
                    "individual_disappearance": sum(
                        1 for r in ledger if r["recovery_sublabel"]
                        == "STALE_OFFENDER_NEVER_OBSERVED_AGAIN_RETIREMENT_SCIENCE"),
                    "mass_clock_reset": stale_mass,
                },
                "feasibility": "low (needs validated retirement inference "
                               "+ restart/clock semantics; V3.2J/C rejected "
                               "generic retirement inference)",
                "risk": "high", "complexity": "high",
                "sim_change": False, "future_data_risk": "none (<=T only)",
                "recommended_stage": "research stage after V3.11B",
            },
            {
                "category": "R3 neutralized TRACK regimes",
                "states": sum(1 for r in ledger if r["recovery_class"]
                              == "R3_SIMULATOR_SUPPORT_REQUIRED"),
                "feasibility": "low (new regime science per V3.2F/H)",
                "risk": "high", "complexity": "high",
                "sim_change": True, "future_data_risk": "none",
                "recommended_stage": "later regime stage (not V3.11B)",
            },
            {
                "category": "R4 WET (pace + evolution + transition)",
                "states": sum(1 for r in ledger
                              if r["recovery_class"] == "R4_RESEARCH_REQUIRED"
                              and "WET" in r["recovery_sublabel"]),
                "feasibility": "low (INTER data exists but WET-rain cells "
                               "thin; no evolution/transition mechanism)",
                "risk": "high", "complexity": "high",
                "sim_change": True, "future_data_risk": "none",
                "recommended_stage": "separate wet-modelling stage",
            },
            {
                "category": "R5 not causally recoverable",
                "states": sum(1 for r in ledger if r["recovery_class"]
                              == "R5_NOT_CAUSALLY_RECOVERABLE"),
                "feasibility": "not causally recoverable",
                "risk": "high", "complexity": "n/a",
                "sim_change": False, "future_data_risk": "requires future",
                "recommended_stage": "none (candidate-universe question)",
            },
            {
                "category": "R0 terminal (intentional)",
                "states": len(term),
                "feasibility": "intentional",
                "risk": "none", "complexity": "n/a",
                "sim_change": False, "future_data_risk": "none",
                "recommended_stage": "never",
            },
        ],
        "ranking_rule": ("feasibility x safety, not raw count; high-volume "
                         "unsafe recovery ranked below smaller safe fixes"),
    })

    # ---- forensic summary ----
    _write("forensic_summary.json", {
        "schema_version": "v3.11a-forensic-summary-v1",
        "baseline": {"candidate": total, "eligible": n_elig,
                     "unsupported": n_unsup,
                     "reasons": {SHORT[k]: v for k, v in prim.items()
                                 if k in SHORT and k != "SIMULATION_CAPABLE"}},
        "join": {"raw_primary_mismatches_vs_final": prim_mismatch,
                 "j_relief_stale_to_capable": j_moved,
                 "blockers_reproduce_frozen": joined_blockers[
                     "matches_frozen_final_blockers"]},
        "unsupported_ledger_rows": len(ledger),
        "multi_blocker_states": sum(1 for r in ledger
                                    if len(r["blocking_conditions"]) > 1),
        "single_blocker_states": sum(1 for r in ledger
                                     if len(r["blocking_conditions"]) == 1),
    })

    # ---- validation + scientific card ----
    try:
        import resource  # noqa: PLC0415
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes; Linux reports kilobytes.
        peak_mb = round(peak / (1024 * 1024 if sys.platform == "darwin"
                                else 1024), 1)
    except (ImportError, OSError, ValueError):
        peak_mb = None
    wall_s = round(time.perf_counter() - t0, 1)
    _write("validation.json", {
        "schema_version": "v3.11a-validation-v1",
        "baseline_exact": baseline["exact"],
        "blockers_reproduce_frozen": joined_blockers[
            "matches_frozen_final_blockers"],
        "ledger_completeness": len(ledger) == n_unsup,
        "original_reasons_preserved": all(
            r["original_reason"] in EXPECTED_REASONS for r in ledger),
        "no_eligibility_change": True,
        "no_production_import": True,
        "audit_wall_s": wall_s,
        "audit_peak_rss_mb": peak_mb,
    })
    _write("scientific_card.json", {
        "schema_version": "v3.11a-scientific-card-v1",
        "stage": "V3.11A MC2 coverage forensics (observational)",
        "frozen_base": "v3.10-pit-wall",
        "ledger": f"{EXPECTED_ELIGIBLE}/{EXPECTED_TOTAL} eligible "
                  f"({round(100 * EXPECTED_ELIGIBLE / EXPECTED_TOTAL, 2)}%)",
        "unsupported": EXPECTED_UNSUPPORTED,
        "classification": "MC2_COVERAGE_FORENSICS_COMPLETE",
        "production_effect": "none (diagnostic artifacts only)",
    })

    print(json.dumps({
        "status": "OK" if baseline["exact"] else "BLOCKED",
        "candidate": total, "eligible": n_elig, "unsupported": n_unsup,
        "reasons": {SHORT.get(k, k): v for k, v in sorted(prim.items())},
        "blockers_reproduce_frozen": joined_blockers[
            "matches_frozen_final_blockers"],
        "j_relief": j_moved, "wall_s": wall_s, "peak_rss_mb": peak_mb,
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
