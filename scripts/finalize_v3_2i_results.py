#!/usr/bin/env python3
"""V3.2I finalization (Parts H-K, R-T, V-X inputs + decision).

Writes OpenF1/Jolpica/external feasibility, scorecard, completeness,
licensing, architecture/provenance plans, race-detail projection, and
the V3.2I decision from frozen evidence files. No runtime changes.
Deterministic (evidence-derived + documented constants only).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_2i"


def w(name: str, obj: dict) -> None:
    json.dump(obj, open(OUT / name, "w"), indent=2, sort_keys=True)


def main() -> int:
    proj = json.load(open(OUT / "projected_coverage.json", encoding="utf-8"))
    sem = json.load(open(OUT / "status_semantics.json", encoding="utf-8"))
    avail = json.load(open(OUT / "source_availability.json",
                           encoding="utf-8"))["local_timingdata_streams"]

    w("openf1_feasibility.json", {
        "schema_version": "v3.2i-openf1-v1",
        "historical_since": "2023 (vendor FAQ, verified 2026-10-06)",
        "endpoints": 18,
        "retirement_transition_endpoint": "NONE (position, laps, "
            "intervals, pits, race_control, session_result surveyed; "
            "position stream ends at retirement = absence, not signal; "
            "session_result.dnf mirrors final classification, e.g. "
            "Norris Austria 2024 dnf=false despite on-track retirement)",
        "probe": "live API 2026-10-06: Austria 2024 NOR position ends "
                 "14:21:36 pos 20; session_result dnf=false; "
                 "race_control has flags, no per-driver retirement",
        "access": "free, no key, 3 req/s + 30 req/min; CC BY-NC-SA 4.0; "
                  "unofficial community project",
        "verdict": "VALIDATION_ONLY (2023+ cross-check); NOT_VIABLE as "
                   "causal 2018-2024 source (no 2018-2022; no retirement "
                   "transition semantics)"})

    w("jolpica_feasibility.json", {
        "schema_version": "v3.2i-jolpica-v1",
        "result_grain": "final classification only (positionText, "
                        "status e.g. Finished/Collision, laps; "
                        "verified live 2026-10-06 on 2024 round 24)",
        "timestamp_or_lap_scoped": False,
        "verdict": "EVALUATION_ONLY; REJECTED as runtime causal source "
                   "(result-only labels are exactly the future-derived "
                   "class V3.2G forbids)"})

    w("external_sources.json", {
        "schema_version": "v3.2i-external-v1",
        "f1_static_jsonstream": {
            "pattern": "livetiming.formula1.com/static/{Y}/{date}_{GP}/"
                       "{date}_Race/TimingData.jsonStream",
            "auth": "none (public S3 static hosting; same host FastF1 "
                    "itself fetches)",
            "probe": "HEAD 2021-12-12 stream -> HTTP 200, 5.5 MB; one "
                     "full GET parsed: 2021 schema identical "
                     "(Retired/Stopped/InPit bools, 3 Retired:true for "
                     "#7/#63/#11)",
            "seasons_obtainable": "2018-2024 at minimum (2018+2024 "
                                   "cached locally; 2021 probe-fetched; "
                                   "pattern is season-uniform)",
            "verdict": "VIABLE completion path for 2019-2023 (mechanical "
                       "fetch in V3.2J, not bulk-downloaded here)"},
        "other_candidates": "none needed: official static host covers "
                            "2018-2024; no fan-page scraping, no "
                            "Wikipedia-as-data, no fabricated providers"})

    tp = sum(p["recall_tp"] for p in sem["per_race"])
    fp = sum(p["false_positive"] for p in sem["per_race"])
    fn = sum(p["missed_fn"] for p in sem["per_race"])
    w("source_scorecard.json", {
        "schema_version": "v3.2i-scorecard-v1",
        "sources": [
            {"source": "LOCAL TimingData.Retired jsonStream "
                       "(2018+2024, 45 races)",
             "coverage_2018_2024": "PARTIAL (2/7 seasons local)",
             "per_driver": True, "timestamped": True,
             "explicit_retirement": True, "stopped_distinct": True,
             "causal_at_T": "YES with state-at-T rule (1 known transient "
                            "window in 45 races; 0 checkpoint impact)",
             "reproducible": True, "licensing_access": "local cache of "
                "official public static feed (F1 terms apply; derived "
                "timestamps committable, raw blobs too large)",
             "verdict": "PARTIALLY_VIABLE"},
            {"source": "F1 static jsonStream fetch for 2019-2023",
             "coverage_2018_2024": "FULL (pattern probe-verified)",
             "per_driver": True, "timestamped": True,
             "explicit_retirement": "EXPECTED (2021 schema identical; "
                "per-race validation required in V3.2J)",
             "stopped_distinct": "EXPECTED", "causal_at_T": "EXPECTED",
             "reproducible": True, "licensing_access": "same public "
                "static host, no auth",
             "verdict": "VIABLE (completion path; fetch deferred to V3.2J)"},
            {"source": "OpenF1", "coverage_2018_2024": "2023+ only",
             "per_driver": True, "timestamped": "positions yes, "
                "retirement no", "explicit_retirement": False,
             "stopped_distinct": False, "causal_at_T": False,
             "reproducible": True, "licensing_access": "CC BY-NC-SA 4.0, "
                "free no-key",
             "verdict": "VALIDATION_ONLY"},
            {"source": "Jolpica/Ergast", "coverage_2018_2024": "FULL "
             "(result grain)", "per_driver": True,
             "timestamped": False, "explicit_retirement": "result-only",
             "stopped_distinct": False, "causal_at_T": False,
             "reproducible": True, "licensing_access": "open API",
             "verdict": "EVALUATION_ONLY (NOT_VIABLE runtime)"},
            {"source": "position Null / STOPPED / pit-duration / final "
                       "DNF heuristics",
             "coverage_2018_2024": "n/a", "per_driver": False,
             "timestamped": False, "explicit_retirement": False,
             "stopped_distinct": False, "causal_at_T": False,
             "reproducible": False, "licensing_access": "n/a",
             "verdict": "NOT_VIABLE (V3.2G rejections stand)"}],
        "feed_vs_official_accounting": {
            "official_dnfs": 127, "feed_retired_drivers": tp + fp,
            "recall_tp": tp, "race_level_fp": fp, "missed_fn": fn,
            "note": "race-level fp overstates hazard: 6/7 are "
                    "post-race or >90%-classified genuine retirements "
                    "(causally safe: first-true after all race "
                    "checkpoints); 1 genuine transient (RIC BEL 2018, "
                    "4.5-min window, 0 checkpoints impacted)"}})

    # Part R detail: projected race coverage distribution
    import pandas as pd
    cur_cov: dict = {}
    raw = json.load(open(ROOT / "results" / "v3" / "v3_2f" /
                         "coverage_opportunity_raw.json", encoding="utf-8"))
    for c in raw["checkpoints"]:
        r = cur_cov.setdefault(c["race_id"], [0, 0])
        r[1] += 1
        if c["primary"] == "SIMULATION_CAPABLE":
            r[0] += 1
    gain: dict = {}
    for m in proj["resolved_members"]:
        pass
    # STALE-only gain members are a subset; recompute per-race clean gain
    # from resolved list intersected with STALE-only flag via raw lookup
    by_key = {(c["race_id"], c["frame_index"]): c for c in raw["checkpoints"]}
    race_gain: dict = {}
    OTHER = {"UNSUPPORTED_TRACK_STATE", "WET_CONDITIONS",
             "MISSING_DRIVER_OBSERVATION", "MISSING_TYRE_STATE",
             "TERMINAL_STATE"}
    for m in proj["resolved_members"]:
        c = by_key[(m[0], m[1])]
        if not (set(c["all_blockers"]) - {"STALE_ROSTER_OBSERVATION"}):
            race_gain[m[0]] = race_gain.get(m[0], 0) + 1
    rows = []
    for rid, (s, n) in sorted(cur_cov.items()):
        g = race_gain.get(rid, 0)
        rows.append({"race_id": rid, "before": [s, n],
                     "projected_gain": g,
                     "projected_fraction": round((s + g) / n, 4)})
    fr = sorted((s + race_gain.get(r, 0)) / n for r, (s, n) in cur_cov.items())
    def qq(v, x):
        return v[int(x * (len(v) - 1))] if v else None
    n_races = len(cur_cov)
    nz_before = sum(1 for s, n in cur_cov.values() if s > 0)
    nz_after = sum(1 for r, (s, n) in cur_cov.items()
                   if s + race_gain.get(r, 0) > 0)
    w("projected_race_coverage.json", {
        "schema_version": "v3.2i-projected-race-v1",
        "current": {"races_ge_1": 103, "zero_support": 46,
                    "median_race_coverage": 0.0938},
        "projected": {
            "races_ge_1": nz_after, "zero_support": n_races - nz_after,
            "median_race_coverage": round(qq(fr, 0.5), 4),
            "ge_50": sum(1 for r, (s, n) in cur_cov.items()
                         if (s + race_gain.get(r, 0)) / n >= 0.5),
            "ge_75": sum(1 for r, (s, n) in cur_cov.items()
                         if (s + race_gain.get(r, 0)) / n >= 0.75),
            "ge_95": sum(1 for r, (s, n) in cur_cov.items()
                         if (s + race_gain.get(r, 0)) / n >= 0.95),
            "full": sum(1 for r, (s, n) in cur_cov.items()
                        if s + race_gain.get(r, 0) == n)},
        "note": "upper bound: cached 2018+2024 races only; 2019-2023 "
                "project zero until streams fetched",
        "nz_before_check": nz_before,
        "races": rows})

    w("source_completeness.json", {
        "schema_version": "v3.2i-completeness-v1",
        "local_streams": "45/149 races (2018: 21/21; 2024: 24/24; "
                         "2019-2023: 0)",
        "feed_recall_vs_official_dnf": {
            "tp": tp, "fn": fn,
            "miss_classes": "non-starters (lap-0, no stream events "
                            "possible), pit/garage retirements without "
                            "track flag, abandoned-without-Retired "
                            "(Baku 2018: 7/7 missed despite Stopped)"},
        "unknown_vs_active": "absence of Retired NEVER implies active; "
                             "unknown is the default (V3.2G preserved)",
        "verdict": "explicit retirement signal exists but is not "
                   "universal: partial recall is intrinsic, not a bug"})

    w("licensing_reproducibility.json", {
        "schema_version": "v3.2i-licensing-v1",
        "f1_static_feed": "public static hosting, no auth observed; "
            "underlying data is F1 proprietary (terms undocumented here; "
            "no legal claims made)",
        "raw_commit": "full jsonStream blobs are GB-scale: NOT committed; "
                      "derived per-driver Retired transition tables "
                      "(race, driver, t, value + source content hash) are "
                      "KB-scale and committable",
        "rebuild": "reproducible: URL pattern + adapter version + "
                   "content hash pinned in provenance plan; uncertainty "
                   "flagged where vendor terms are silent",
        "openf1": "CC BY-NC-SA 4.0, free no-key tier, rate limits "
                  "documented; validation-only use",
        "jolpica": "open API; evaluation-only use"})

    w("architecture_plan.json", {
        "schema_version": "v3.2i-architecture-v1",
        "status": "DESIGN ONLY (no implementation in V3.2I)",
        "pipeline": ["official static jsonStream (pinned URL + content hash)",
                     "immutable source adapter (v3.2j-status-adapter-v1)",
                     "chronological reconstruction (state-at-T, flips respected)",
                     "causal driver-status timeline artifact",
                     "V3.2C presence (exclusion input only; never inclusion)",
                     "eligibility (unchanged taxonomy)",
                     "unchanged MC2-E"],
        "invariants": ["no external logic inside stochastic kernel",
                       "absence never implies active",
                       "transient guard: state-at-T, not first-true",
                       "post-race events excluded by T comparison",
                       "parity corpus must stay bit-exact"]})

    w("provenance_plan.json", {
        "schema_version": "v3.2i-provenance-v1",
        "status": "DESIGN ONLY",
        "artifact_identity": ["source identity (f1-static-timingdata)",
                              "race/session identity",
                              "source content hash (sha256 of stream bytes)",
                              "adapter version",
                              "status-contract version",
                              "generation configuration (rules hash)"]})

    decision = "LOCAL_RAW_STATUS_SOURCE_PARTIALLY_VIABLE"
    w("decision.json", {
        "schema_version": "v3.2i-decision-v1",
        "decision": decision,
        "projected_coverage": f"{proj['projected']['eligible']}/9644 "
                              f"({proj['projected_fraction'] * 100:.2f}%)",
        "reason": "TimingData.Retired is an explicit, timestamped, "
                  "causal per-driver retirement signal (winners never "
                  "flagged; flips measured and handled by state-at-T; "
                  "0 checkpoint impact from the one genuine transient), "
                  "but local holdings cover only 2018+2024 and feed "
                  "recall vs official DNF is ~39% (misses are intrinsic: "
                  "non-starters, garage retirements, abandoned-without-"
                  "flag). 2019-2023 completion is probe-verified "
                  "obtainable from the same public static host. No "
                  "heuristic re-attempted; runtime untouched.",
        "next_stage": "V3.2J DECISION: fetch 2019-2023 streams, validate "
                      "per-race, then integrate as exclusion-only presence "
                      "input; re-test parity; recompute coverage"})
    print(f"decision={decision} projected={proj['projected']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
