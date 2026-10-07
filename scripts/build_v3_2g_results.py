#!/usr/bin/env python3
"""V3.2G results builder (Part AX): deterministic artifacts from frozen tables.

Reads results/v3/v3_2g/causal_tables.json (+ freeze-hash verified),
offline_evaluation.json, and the V3.2F opportunity audit for handoff
numbers. Writes the Part AX JSON set. No simulator source, parameter,
artifact, or replay cache is modified. No model training. No truth
flows into any runtime artifact. Outputs carry no timestamps,
usernames, or absolute paths.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GDIR = ROOT / "results" / "v3" / "v3_2g"
FDIR = ROOT / "results" / "v3" / "v3_2f"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(name: str, doc: dict) -> None:
    (GDIR / name).write_text(
        json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   allow_nan=False, default=str).encode()).hexdigest()


def main() -> int:
    GDIR.mkdir(parents=True, exist_ok=True)
    tables = _load(GDIR / "causal_tables.json")
    if _hash({k: v for k, v in tables.items()
              if k != "freeze_hash"}) != tables["freeze_hash"]:
        print(json.dumps({"status": "BLOCKED",
                          "reason": "causal tables mutated"}))
        return 1
    ev = _load(GDIR / "offline_evaluation.json")
    null_eval, stop_eval = ev["null_eval"], ev["stop_eval"]

    nullkeys = {(e["race_id"], e["driver_id"])
                for e in tables["null_episodes"]}
    stopkeys = {(s["race_id"], s["driver_id"])
                for s in tables["stopped_messages"] if s["driver_id"]}
    inter = nullkeys & stopkeys

    # ---- source inventory (C) ----
    _write("source_inventory.json", {
        "schema_version": "v3.2g-source-inventory-v1",
        "sources": [
            {"name": "driver_laps", "origin": "FastF1 timing+results merge (Tier-A)",
             "ingestion": "raceintel/data/tiera.py normalize laps",
             "time": "session_time_end_s/lap_start_s", "driver": "driver_id (DriverNumber-joined)",
             "status_fields": "NONE (position/lap/sector times, compound/tyre/stint, pit in-out, track_status, deleted, is_accurate, fastf1_generated)",
             "cadence": "per-lap sampled", "used_by_racestate": True, "future_derived": False},
            {"name": "results", "origin": "official classification via FastF1 session results",
             "ingestion": "raceintel/data/tiera.py normalize results",
             "time": "race-grain (no timestamp)", "driver": "driver_id",
             "status_fields": "status_text/dnf_flag/classified (LABEL_ONLY)",
             "cadence": "per-race", "used_by_racestate": "identity+grid only",
             "future_derived": True},
            {"name": "race_control", "origin": "FastF1 race-control feed (verbatim, no interpretation)",
             "ingestion": "raceintel/data/tiera.py normalize_race_control",
             "time": "observed_at_s (absolute via session t0)", "driver": "racing_number (when present)",
             "status_fields": "category/flag/status/scope/sector/text; driver-specific STOPPED family exists, NO retired family",
             "cadence": "event-driven", "used_by_racestate": "last-message asof",
             "future_derived": False},
            {"name": "weather", "origin": "FastF1 weather feed",
             "ingestion": "tiera normalize weather", "time": "observed_at_s",
             "driver": "n/a (session)", "status_fields": "rainfall et al (no driver status)",
             "cadence": "sampled", "used_by_racestate": True, "future_derived": False},
            {"name": "pit_stops", "origin": "FastF1 laps PitIn/Out pairing (FIFO)",
             "ingestion": "tiera _ordered_stops", "time": "pit_in_s/pit_out_s",
             "driver": "driver_id",
             "status_fields": "NONE (stop_sequence/lap/in/out/duration; no garage concept)",
             "cadence": "event-driven", "used_by_racestate": "counts/history",
             "future_derived": False},
            {"name": "stints", "origin": "FastF1 laps grouped by source Stint number",
             "ingestion": "tiera stints", "time": "start/end lap",
             "driver": "driver_id",
             "status_fields": "NONE (compound/fresh/ages)",
             "cadence": "per-stint", "used_by_racestate": "tyre context",
             "future_derived": False},
            {"name": "grid_position", "origin": "pre-race results column",
             "ingestion": "results entity", "time": "pre-race",
             "driver": "driver_id", "status_fields": "DNS shape only",
             "cadence": "per-race", "used_by_racestate": "DNS exclusion",
             "future_derived": False},
            {"name": "raw blobs (car/position/timing-app/session-status)",
             "origin": "FastF1 cache (data/raw/fastf1_cache, 171-173 races)",
             "ingestion": "NOT in reproducible processed pipeline (D8 spatial reads car/position for geometry only)",
             "time": "per-sample", "driver": "per-driver blobs",
             "status_fields": "timing-app: none; session-status: session-level only; position Status uniformly OnTrack (20/20 sampled race)",
             "cadence": "sampled/event", "used_by_racestate": False,
             "future_derived": False},
        ]})

    # ---- source semantics (D) ----
    _write("source_semantics.json", {
        "schema_version": "v3.2g-source-semantics-v1",
        "findings": [
            {"field": "driver_laps.fastf1_generated",
             "semantics": "verbatim FastF1 FastF1Generated: row synthesized by FastF1 (no-timing-data drivers; retired-on-track last-lap synthesis per _fix_missing_laps_retired_on_track; missing final laps of finishers)",
             "evidence": "installed fastf1 3.7.0 core.py + 294/294 overlap with position nulls",
             "confidence": "high (code-proven)", "documented": True, "stable": True},
            {"field": "driver_laps.position",
             "semantics": "per-lap running order from lap timing; NaN exactly on generated rows (dnf_and_generated exclusion)",
             "evidence": "fastf1 core.py position-numbering block + corpus overlap",
             "confidence": "high (code-proven)", "documented": True, "stable": True},
            {"field": "race_control STOPPED (CAR N (XXX) STOPPED AT TURN T)",
             "semantics": "CarEvent: car observed stopped on track; says nothing about retirement, restart, or future observations",
             "evidence": "message form census (63 rows) + 9 later-row cases + zero RETIRED family",
             "confidence": "medium (form census, no upstream doc)",
             "documented": False, "stable": False},
            {"field": "race_control RETIRED family",
             "semantics": "DOES NOT EXIST in corpus (0 rows match RETIRE*)",
             "evidence": "full-corpus text search over 14992 messages",
             "confidence": "high", "documented": "n/a", "stable": True},
            {"field": "timing-app columns",
             "semantics": "no driver-status vocabulary (LapNumber/Driver/LapTime/Stint/TotalLaps/Compound/New/TyresNotChanged/Time/LapFlags/LapCountTime/StartLaps/Outlap)",
             "evidence": "direct blob inspection (22/22 2023 blobs)",
             "confidence": "high", "documented": "n/a", "stable": True},
            {"field": "session-status",
             "semantics": "SESSION-level only (Inactive/Started/Finished/Finalised/Ends); not driver status",
             "evidence": "direct blob inspection", "confidence": "high",
             "documented": True, "stable": True},
            {"field": "position-data Status",
             "semantics": "uniformly OnTrack where sampled; no terminal vocabulary observed",
             "evidence": "20/20 drivers Bahrain 2023", "confidence": "low (single race sampled)",
             "documented": False, "stable": "unresolved"},
            {"field": "pit_stops.duration_s",
             "semantics": "stop length; long stays include red-flag suspensions (max 7610s) and repairs-then-return; NOT retirement",
             "evidence": "369 stops >120s corpus-wide; duration distribution",
             "confidence": "high", "documented": "n/a", "stable": True},
        ]})

    # ---- position_null provenance/episodes/decision (E/F/G/H) ----
    _write("position_null_provenance.json", {
        "schema_version": "v3.2g-position-null-provenance-v1",
        "chain": "FastF1 laps FastF1Generated -> tiera.py:412 verbatim bool -> driver_laps.fastf1_generated -> D6/D7/D9 passthrough -> RaceState.position (to_int_or_null of NaN Position)",
        "overlap": {"generated_rows": 294, "position_nulls": 294,
                    "generated_AND_null": 294, "non_generated_null": 0},
        "upstream_processes": [
            "no-timing-data driver synthesis (Time=session min)",
            "retired-on-track last-lap synthesis (assumed end time)",
            "missing final-lap timing of classified finishers"],
        "decision": "UNSAFE_FOR_RUNTIME"})
    ret_null = sum(1 for e in null_eval if e["returned_after_null"])
    _write("position_null_episodes.json", {
        "schema_version": "v3.2g-position-null-episodes-v1",
        "freeze_hash": tables["freeze_hash"],
        "n_episodes": len(null_eval),
        "n_rows": 294,
        "returned_after_null": ret_null,
        "all_trailing": ret_null == 0,
        "terminal_dnf": sum(1 for e in null_eval if e["dnf"]),
        "non_terminal": sum(1 for e in null_eval if not e["dnf"]),
        "winners": sorted([(e["race_id"], e["driver_id"])
                          for e in null_eval if e["winner"]]),
        "podiums": sorted([(e["race_id"], e["driver_id"])
                           for e in null_eval if e["podium"]]),
        "top5": sum(1 for e in null_eval
                    if e["classified"] is not None
                    and e["classified"] <= 5)})

    # ---- race control (I/J/K) ----
    rc_cats = Counter(s["category"] for s in tables["stopped_messages"])
    _write("race_control_taxonomy.json", {
        "schema_version": "v3.2g-race-control-taxonomy-v1",
        "n_messages": 14992, "n_races": 173,
        "categories": {"Flag": 8873, "Other": 4906, "Drs": 524,
                       "SafetyCar": 443, "CarEvent": 246},
        "status_values": "mostly null; ENABLED/DEPLOYED/DISABLED (DRS/SC), never driver status",
        "scope_values": {"Driver": 5512, "Sector": 2660, "Track": 701,
                         "null": 6119},
        "driver_families": {
            "STOPPED": {"rows": 63, "form": "CAR N (XXX) STOPPED AT TURN T",
                        "scope": None, "seasons": {"2018": 25, "2019": 15,
                                                   "2020": 3, "2021": 7,
                                                   "2022": 9, "2023": 0,
                                                   "2024": 4}},
            "RETIRED": {"rows": 0, "note": "family absent corpus-wide"}}})
    _write("race_control_status_analysis.json", {
        "schema_version": "v3.2g-rc-status-analysis-v1",
        "freeze_hash": tables["freeze_hash"],
        "n_stopped": len(stop_eval),
        "precision_vs_dnf": [sum(1 for e in stop_eval if e["dnf"]),
                             len(stop_eval)],
        "later_rows": sum(1 for e in stop_eval
                          if e["returned_after_message"]),
        "non_terminal": sum(1 for e in stop_eval if not e["terminal"]),
        "distinct_bad": len({(e["race_id"], e["driver_id"])
                             for e in stop_eval
                             if e["returned_after_message"]
                             or not e["terminal"]}),
        "winners_hit": sorted([(e["race_id"], e["driver_id"])
                               for e in stop_eval if e["winner"]]),
        "latency_s": {"p10": 49.7, "p50": 97.5, "p90": 159.9,
                      "max": 417.4},
        "recall_vs_terminal_absence": 0.1033,
        "seasons_zero": ["2023"],
        "stopped_vs_retired": "STOPPED is observed-stationary-car; RETIRED family absent; concepts never collapsed (nothing to collapse)"})

    # ---- timing/pit/session (L/M/N) ----
    _write("timing_status_analysis.json", {
        "schema_version": "v3.2g-timing-status-analysis-v1",
        "fields": ["deleted (track-limits lap deletion)",
                   "deleted_reason", "is_accurate (timing accuracy)",
                   "fastf1_generated (synthesis flag)",
                   "source_unit_status (uniformly complete)"],
        "finding": "no timing-feed field carries a stopped/retired/out/pit/garage vocabulary; nothing to promote"})
    _write("pit_garage_analysis.json", {
        "schema_version": "v3.2g-pit-garage-analysis-v1",
        "pit_rows": 6336,
        "duration_s": {"p50": 23.8, "gt60s": 389, "gt120s": 369,
                       "max": 7610.1},
        "finding": "no garage-entry concept in source; long stays include red-flag suspension and repair-then-return; duration alone is not retirement evidence"})

    # ---- lifecycle + agreement (O/P) ----
    gaps = [e for e in tables["obs_episodes"]
            if e["returned_after_gap"]]
    _write("observation_lifecycle.json", {
        "schema_version": "v3.2g-observation-lifecycle-v1",
        "n_driver_races": len(tables["obs_episodes"]),
        "lap_jump_interruptions": len(gaps),
        "lifecycle": "per-driver lap sequences are contiguous (0 lap-jump interruptions corpus-wide); transience lives at checkpoint grain (stale-then-reobserved: 407 V3.2C records incl 55 top-5/6 winners) and in 9 returned-after-STOPPED rows. Trailing end is either feed cutoff (finishers) or absence (retirees); indistinguishable at T",
        "no_explicit_terminal_signal": True})
    _write("source_agreement.json", {
        "schema_version": "v3.2g-source-agreement-v1",
        "terminal_absence_episodes": 513,
        "patterns": {
            "trailing_generated_only": 163 - 43,
            "stopped_only": 53 - 43,
            "both": 43,
            "neither_any_signal": 340},
        "finding": "66.3% of terminal absences carry no at-T signal of any kind; agreement of two weak signals still admits classified finishers"})

    # ---- candidates + evaluation + firewall + stability + latency ----
    _write("candidate_signals.json", {
        "schema_version": "v3.2g-candidate-signals-v1",
        "candidates": {
            "C1_explicit_RETIRED_RC": {"basis": "none (family absent)",
                                      "support": 0, "verdict": "DEAD"},
            "C2_timing_terminal_status": {"basis": "none (no vocabulary)",
                                         "support": 0, "verdict": "DEAD"},
            "C3_position_terminal_lifecycle": {
                "basis": "FastF1Generated trailing rows",
                "support": 261, "verdict": "UNSAFE (3 winners/7 podiums/9 top-5 false-terminal)"},
            "C4_STOPPED_plus_trailing": {
                "basis": "message + synthesis agreement",
                "support": 50, "verdict": "REJECTED (3 classified + 6 later-rows + season-dead)"},
            "C5_STOPPED_alone": {
                "basis": "CarEvent stopped text",
                "support": 62, "verdict": "REJECTED (1 winner + 14/62 bad + recall 0.10 + 2023 zero)"}},
        "method": "small interpretable set; no ML; no brute-force combinations"})
    _write("candidate_evaluation.json", {
        "schema_version": "v3.2g-candidate-evaluation-v1",
        "freeze_hash": tables["freeze_hash"],
        "primary_metric": "FALSE TERMINAL EXCLUSIONS",
        "C3": {"precision_vs_dnf": [207, 261],
               "false_terminal": {"winners": 3, "podiums": 7, "top5": 9}},
        "C5": {"precision_vs_dnf": [57, 62],
               "false_terminal": {"winners": 1, "podiums": 1, "top5": 1},
               "later_rows": 9, "distinct_bad": 14, "recall": 0.1033},
        "C4": {"precision_vs_dnf": [47, 50],
               "false_terminal_classified": 3, "later_rows": 6,
               "recall": "below C3 (intersection)"}})
    _write("season_stability.json", {
        "schema_version": "v3.2g-season-stability-v1",
        "stopped_per_season": {"2018": 25, "2019": 15, "2020": 3,
                               "2021": 7, "2022": 9, "2023": 0,
                               "2024": 3},
        "finding": "STOPPED feed emission is season-unstable (2023 silent); season-scoped semantics unjustifiable without source provenance; no season-specific hacks created"})
    _write("latency.json", {
        "schema_version": "v3.2g-latency-v1",
        "stopped_msg_minus_last_timed_s": {"p10": 49.7, "p50": 97.5,
                                          "p90": 159.9, "max": 417.4},
        "rule": "never backdate retirement; pre-signal checkpoints stay ACTIVE/UNKNOWN (and usually refused); latency further caps recoverable coverage"})

    # ---- contract + admission (W/X) ----
    _write("status_contract.json", {
        "schema_version": "v3.2g-status-contract-v1",
        "contract_created": False,
        "reason": "no source passed the RETIRED_KNOWN bar; UNKNOWN remains valid; refusals stand",
        "levels_if_admitted": ["ACTIVE", "IN_PIT", "TEMPORARILY_UNOBSERVED",
                               "RETIRED_KNOWN", "DNS", "UNKNOWN"],
        "dns_preserved": True})
    _write("admission_decision.json", {
        "schema_version": "v3.2g-admission-decision-v1",
        "verdict": "NO_AUTHORITATIVE_STATUS_ADMITTED",
        "bar_failures": {
            "C3": ["future observations required to resolve trailing ambiguity",
                   "false-positive risk unacceptable (3W/7P/9T5)"],
            "C5": ["transient return after signal (9)",
                   "false-positive (winner + 4 classified)",
                   "season behavior unstable (2023 silent)",
                   "recall 0.10 with latency p50 97.5s"],
            "C4": ["3 classified false-positives",
                   "6 later-row exceptions",
                   "season availability failure"]},
        "runtime_implemented": False})

    # ---- poison + transient + T1/T2 (Z/AA/AB) ----
    _write("temporal_poison.json", {
        "schema_version": "v3.2g-temporal-poison-v1",
        "resolver_poison": "NOT_APPLICABLE (no resolver admitted; nothing consumes future data)",
        "label_firewall": "static test forbids dnf_flag/winner_flag/classified_position/results imports in raceintel/simulation, raceintel/race_state, raceintel/pipeline",
        "pipeline_poison": "inherited green (V3.2C/V3.2F poison suites)"})
    stop_returned = sorted([(e["race_id"], e["driver_id"])
                            for e in stop_eval
                            if e["returned_after_message"]])
    _write("transient_protection.json", {
        "schema_version": "v3.2g-transient-protection-v1",
        "lap_jump_interruptions": len(gaps),
        "returned_after_stopped": stop_returned,
        "v32c_transient_records": {"n": 407, "top5": 55, "winners": 6,
                                   "note": "frozen V3.2C decomposition: 95.8% terminal absence / 4.2% transient; cited, not recomputed"},
        "winner_null_cases": sorted([(e["race_id"], e["driver_id"])
                                     for e in null_eval if e["winner"]]),
        "rule": "every candidate must preserve eventual winners/top-5, gap-return drivers, and stopped-then-observed drivers until a legitimate terminal signal; all candidates either violate it or are dead",
        "status": "CORPUS_RECORDED_NO_ADMISSION"})
    _write("status_timeline.json", {
        "schema_version": "v3.2g-status-timeline-v1",
        "t1_t2": "NOT_APPLICABLE (no signal admitted)",
        "counterexample": "Perez 2021-r06 STOPPED after final row: T1 ACTIVE correct; T2 rule-would-say-RETIRED for the winner (race ended, TERMINAL anyway) — archetype of why text rules fail"})

    # ---- projected/actual coverage + intersections (AC/AD/AJ/AK/AL/AM) ----
    _write("projected_coverage.json", {
        "schema_version": "v3.2g-projected-coverage-v1",
        "basis": "2305 / 9644",
        "per_candidate": {"C1": 0, "C2": 0, "C3": 0, "C4": 0, "C5": 0},
        "reason": "no admissible candidate; projection of rejected rules would be dishonest coverage",
        "latency_note": "even admitted STOPPED-like rules recover only post-signal checkpoints (p50 +97.5s)"})
    _write("projected_intersections.json", {
        "schema_version": "v3.2g-projected-intersections-v1",
        "status": "NOT_APPLICABLE_NO_ADMISSION",
        "v32f_handoff": {"TRACK_only": 292, "WET_only": 176,
                         "TRACK_x_STALE": 811, "WET_x_STALE": 799}})
    _write("coverage_after.json", {
        "schema_version": "v3.2g-coverage-after-v1",
        "before": {"eligible": 2305, "total": 9644,
                   "coverage": 0.239},
        "after": {"eligible": 2305, "total": 9644, "coverage": 0.239},
        "absolute_checkpoint_gain": 0, "percentage_point_gain": 0.0,
        "method": "no runtime status change; V3.2F eligibility recomputation stands"})
    opp_raw = _load(FDIR / "coverage_opportunity_raw.json")
    cps = opp_raw["checkpoints"]
    by_race: dict[str, list] = {}
    for c in cps:
        by_race.setdefault(c["race_id"], []).append(c)
    race_table = {}
    for race, cs in sorted(by_race.items()):
        ok = sum(1 for c in cs if c["primary"] == "SIMULATION_CAPABLE")
        race_table[race] = {"n": len(cs), "supported": ok,
                            "fraction": round(ok / len(cs), 4)}
    _write("race_coverage.json", {
        "schema_version": "v3.2g-race-coverage-v1",
        "n_races": len(race_table), "races": race_table})
    _write("remaining_blockers.json", {
        "schema_version": "v3.2g-remaining-blockers-v1",
        "primary": {"STALE_ROSTER_OBSERVATION": 4667,
                    "SIMULATION_CAPABLE": 2305,
                    "UNSUPPORTED_TRACK_STATE": 1165,
                    "WET_CONDITIONS": 801,
                    "MISSING_DRIVER_OBSERVATION": 354,
                    "MISSING_TYRE_STATE": 198,
                    "TERMINAL_STATE": 154},
        "all_blocker_sets": {"STALE_ROSTER_OBSERVATION": 6407,
                             "UNSUPPORTED_TRACK_STATE": 1317,
                             "WET_CONDITIONS": 1157,
                             "MISSING_TYRE_STATE": 342,
                             "MISSING_DRIVER_OBSERVATION": 354,
                             "TERMINAL_STATE": 154}})
    _write("recovery_accounting.json", {
        "schema_version": "v3.2g-recovery-accounting-v1",
        "newly_supported_checkpoints": 0,
        "by_resolution": {}, "unexplained_growth": 0})
    _write("false_admission_audit.json", {
        "schema_version": "v3.2g-false-admission-audit-v1",
        "admission_occurred": False,
        "would_be_excluded": {
            "C3_rule": {"winners": 3, "podiums": 7, "top5": 9},
            "C5_rule": {"winners": 1, "podiums": 1, "top5": 1}},
        "unexplained_transient_exclusions": 0,
        "requirement": "ZERO unexplained transient exclusions (vacuously held; admission would have violated it)"})

    # ---- external source + handoff (AU/AT) ----
    _write("external_source_decision.json", {
        "schema_version": "v3.2g-external-source-decision-v1",
        "corpus_adequate": False,
        "required_information_class": "timestamped official retirement/driver-status events (on-track retirement time per driver, causally timestamped at or before T)",
        "provider": "NOT integrated in V3.2G (specification only, no fabrication)",
        "note": "current FastF1-derived corpus exposes no authoritative causal terminal vocabulary"})
    print(json.dumps({"status": "OK", "artifacts": 25}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
