"""D11 — Phase-1 final validation: acceptance gate (read-only + rebuilds).

Runs the D11 validation matrix over the frozen Phase-1 platform and writes a
machine-readable report (``data/v2/reports/data_quality/d11_validation.json``,
gitignored, portable relative paths). It never redesigns stages, never edits
canonical data except through the deterministic rebuild paths (which rewrite
byte-identical outputs), never touches legacy artifacts, and starts nothing
beyond Phase 1.

Usage: ``python -m v2.d11`` (full gate; several minutes) with opt-outs
``--skip-rebuilds --skip-tests --skip-fresh-env --skip-frontend-build``.
Exit code 0 means no unresolved BLOCKER; non-zero findings are recorded in
the report's findings register with severity, evidence and impact.

Validation matrix (id, area, severity on violation):

- ARTIFACT-INVENTORY / CONTRACTS / PK / FK — BLOCKER on violation.
- IDENTITY / TEMPORAL-AVAILABILITY / SEPARATION / ELIGIBILITY — BLOCKER.
- LABELS / MISSINGNESS / ANOMALIES / PARTIAL / WEATHER / RC / PIT-STINT —
  MAJOR on unexplained deviation (anomaly disappearance is itself a finding).
- TELEMETRY / LEGACY / MANIFESTS / RECOVERY / DETERMINISM — BLOCKER.
- STORAGE / GIT / CLI / PERFORMANCE — MAJOR (git/generated-data) else MINOR.
- FRESH-ENV — MAJOR on code failure; documented non-code environment
  limitation is acceptable per the brief.
- REGRESSION — BLOCKER on any red suite.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from v2 import contracts as C
from v2 import d6schema as D6S
from v2 import d7schema as D7S
from v2 import d9schema as D9S
from v2.config import V2Paths
from v2.errors import IngestionError

SEVERITIES = ("BLOCKER", "MAJOR", "MINOR", "INFORMATIONAL")

VALIDATION_MATRIX = [
    {"id": "ARTIFACT-INVENTORY", "area": "artifacts",
     "invariant": "every Phase-1 artifact lives under data/v2 in its "
                  "intended location; no temp/duplicate/unexpected files",
     "method": "filesystem walk + manifest cross-check",
     "expected": "known entity set; 0 tmp files; 0 unexpected files",
     "severity": "BLOCKER"},
    {"id": "CONTRACTS", "area": "schemas",
     "invariant": "every active canonical file conforms to its "
                  "machine-readable contract (columns/order/dtypes); "
                  "telemetry_summary stays inactive",
     "method": "pyarrow schema scan of all files + dtype spot checks",
     "expected": "0 drifted files",
     "severity": "BLOCKER"},
    {"id": "PK", "area": "integrity",
     "invariant": "primary keys present, non-null and unique in every "
                  "canonical table",
     "method": "parquet reads across scope",
     "expected": "0 null PKs, 0 duplicate PKs",
     "severity": "BLOCKER"},
    {"id": "FK", "area": "integrity",
     "invariant": "declared foreign keys resolve (or the exception is a "
                  "documented source-faithful representation)",
     "method": "set-difference orphan counts per relationship",
     "expected": "0 unexplained orphans",
     "severity": "BLOCKER"},
    {"id": "IDENTITY", "area": "identity",
     "invariant": "stable IDs (driver slugs, season-scoped constructors, "
                  "circuits, race ids); display names never keys; no "
                  "fuzzy joins",
     "method": "adversarial data checks + schema/code scans",
     "expected": "collisions 0; renames present as distinct slugs",
     "severity": "BLOCKER"},
    {"id": "TEMPORAL-AVAILABILITY", "area": "temporal",
     "invariant": "every predictive-eligible field is computable from "
                  "information available at or before state_time_s",
     "method": "per-field availability/lineage audit over schemas",
     "expected": "all eligible fields justified; model_feature count 0",
     "severity": "BLOCKER"},
    {"id": "FUTURE-MUTATION", "area": "leakage",
     "invariant": "mutating strictly-future inputs cannot change earlier "
                  "predictive state (per family and combined)",
     "method": "execute leakage test files + combined synthetic test",
     "expected": "suites green",
     "severity": "BLOCKER"},
    {"id": "SEPARATION", "area": "labels",
     "invariant": "state tables carry zero LABEL_ONLY outcome fields; "
                  "labels live at race-driver grain",
     "method": "column-set audit on written parquet + mutation proof (tests)",
     "expected": "0 outcome columns in state",
     "severity": "BLOCKER"},
    {"id": "ELIGIBILITY", "area": "temporal",
     "invariant": "no outcome leaks through predictive_eligible flags; "
                  "quality metadata is never eligible",
     "method": "eligible-field enumeration + anomaly scan",
     "expected": "exact eligible list; 0 anomalies",
     "severity": "BLOCKER"},
    {"id": "LABELS", "area": "labels",
     "invariant": "3,458 labels validate (PK, vocab, winner/pod invariants, "
                  "3 known null-final rows unchanged)",
     "method": "recompute from label parquet",
     "expected": "invariants hold; DNF target still deferred",
     "severity": "MAJOR"},
    {"id": "MISSINGNESS", "area": "quality",
     "invariant": "no silent imputation/drift since stages closed",
     "method": "recompute nulls; compare to stage reports",
     "expected": "equality with d6/d7/d9 validation artifacts",
     "severity": "MAJOR"},
    {"id": "ANOMALIES", "area": "quality",
     "invariant": "documented source anomalies remain present and "
                  "explainable",
     "method": "re-measure the known-anomaly table",
     "expected": "all anomalies reproduce",
     "severity": "MAJOR"},
    {"id": "PARTIAL", "area": "quality",
     "invariant": "shortened races stay PARTIAL with quality metadata; no "
                  "universal modelling exclusion encoded",
     "method": "manifest + state-flag audit + schema scan",
     "expected": "Belgium/Japan partial; others verbatim; no exclusion col",
     "severity": "MAJOR"},
    {"id": "WEATHER", "area": "temporal",
     "invariant": "as-of weather: observed<=state, age>=0, backward-only",
     "method": "independent recomputation on parquet",
     "expected": "0 violations; staleness matches D7 report",
     "severity": "BLOCKER"},
    {"id": "RACE-CONTROL", "area": "temporal",
     "invariant": "message lineage as-of; untimed never attached; D9 flags "
                  "consistent with source codes",
     "method": "recompute splits + attachment audit + token distribution",
     "expected": "14,992/14,923/69; 0 violations",
     "severity": "BLOCKER"},
    {"id": "PIT-STINT", "area": "temporal",
     "invariant": "asymmetric pit boundaries; no negative durations/overlaps; "
                  "no future ends; completed/since semantics hold",
     "method": "recompute + spot-checks + mutation suites (tests)",
     "expected": "5,931/246/159; violations 0",
     "severity": "BLOCKER"},
    {"id": "TELEMETRY", "area": "scope",
     "invariant": "ADR-0001 holds: telemetry deferred, summary inactive, "
                  "cache is source-only",
     "method": "ADR parse + contract/filesystem/code scans",
     "expected": "all hold; cache size recorded",
     "severity": "BLOCKER"},
    {"id": "LEGACY", "area": "regression",
     "invariant": "D10 changed nothing: legacy files/models/behaviour intact",
     "method": "artifact inventory + characterization suites + git status",
     "expected": "7 CSVs, 30 pkls, suites green, tracked paths clean",
     "severity": "BLOCKER"},
    {"id": "MANIFESTS", "area": "operations",
     "invariant": "terminal ingestion states; provenance populated; status "
                  "agrees with artifacts; manifest (not file-existence) is "
                  "authoritative",
     "method": "manifest reads + output_refs existence + code scan",
     "expected": "tierb 76/76 C; tiera 171 C + 2 P; 0 stale claims",
     "severity": "BLOCKER"},
    {"id": "RECOVERY", "area": "operations",
     "invariant": "skip-COMPLETE, partial policy, stale recovery, atomic "
                  "writes, bounded retries (no nested amplification)",
     "method": "execute recovery/idempotency test files",
     "expected": "suites green",
     "severity": "BLOCKER"},
    {"id": "DETERMINISM", "area": "reproducibility",
     "invariant": "D6/D7/D9 rebuilds + D10 audit reproduce identical outputs",
     "method": "rebuild from existing sources; compare sha256/JSON",
     "expected": "identical (wall-clock fields excluded)",
     "severity": "BLOCKER"},
    {"id": "FRESH-ENV", "area": "reproducibility",
     "invariant": "exact requirements install and validate the platform in "
                  "an isolated environment",
     "method": "venv + pip install + import/pytest/CLI smoke",
     "expected": "green, or documented non-code env limitation",
     "severity": "MAJOR"},
    {"id": "CLI", "area": "operations",
     "invariant": "documented commands behave; errors are clear; "
                  "validation paths need no network",
     "method": "help/invalid/read-only/absent-data invocations + import scan",
     "expected": "exit codes 0/2 as appropriate; no fastf1 import",
     "severity": "MAJOR"},
    {"id": "PERFORMANCE", "area": "operations",
     "invariant": "no major unexplained build-time regression",
     "method": "rebuild timings vs recorded build manifests",
     "expected": "within 3x of prior numbers",
     "severity": "MINOR"},
    {"id": "STORAGE", "area": "operations",
     "invariant": "canonical vs cache sizes distinguished and sane",
     "method": "filesystem measurement",
     "expected": "recorded totals",
     "severity": "INFORMATIONAL"},
    {"id": "GIT", "area": "operations",
     "invariant": "generated data/cache untracked; legacy tracked paths "
                  "clean; single repo; no stray temp files",
     "method": "git ls-files/status/check-ignore scans",
     "expected": "clean (pre-existing V2 untracked work noted)",
     "severity": "MAJOR"},
    {"id": "REGRESSION", "area": "regression",
     "invariant": "entire verification battery green",
     "method": "pytest + frontend tests + tsc + lint (+ build if practical)",
     "expected": "all green",
     "severity": "BLOCKER"},
]


def _finding(check_id, severity, passed, evidence, impact=""):
    return {"id": check_id, "severity": severity,
            "status": "pass" if passed else "fail",
            "evidence": evidence, "impact": impact,
            "blocks_phase1": bool(not passed and severity == "BLOCKER"),
            "resolved_in_d11": False}


def _pq(path):
    import pyarrow.parquet as pq

    return pq


def _read_state_files(paths, entity, seasons, unit_fn):
    parts = []
    for season in seasons:
        f = (paths.processed_dir / entity / f"season={season}"
             / f"{entity}__{unit_fn(int(season))}.parquet")
        if f.exists():
            parts.append(pd.read_parquet(f, engine="pyarrow"))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _read_entity_files(paths, entity, seasons):
    parts = []
    for season in seasons:
        for f in sorted((paths.processed_dir / entity
                         / f"season={season}").glob("*.parquet")):
            df = pd.read_parquet(f, engine="pyarrow")
            if len(df):
                parts.append(df)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _concat_entity(paths, entity, seasons, columns=None):
    """Concatenate one entity across seasons, skipping empty files (avoids
    pandas empty-frame concat warnings; empty files are legitimate)."""
    parts = []
    for season in seasons:
        for f in sorted((paths.processed_dir / entity
                         / f"season={season}").glob("*.parquet")):
            df = pd.read_parquet(f, engine="pyarrow", columns=columns)
            if len(df):
                parts.append(df)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


# ---------------------------------------------------------------------------
# §2 artifact inventory.
# ---------------------------------------------------------------------------

EXPECTED_PROCESSED_ENTITIES = (
    "hist_seasons", "hist_circuits", "hist_drivers", "hist_constructors",
    "hist_races", "hist_results", "hist_standings",
    "races", "results", "driver_laps", "pit_stops", "stints", "weather",
    "race_control", "driver_lap_state", "race_quality",
    "driver_lap_state_d7", "driver_lap_state_d9", "race_driver_labels",
)

EXPECTED_REPORTS = (
    "d6_schema.json", "d6_validation.json", "d7_schema.json",
    "d7_validation.json", "d7_coverage.json", "d8_telemetry_sample.json",
    "d9_schema.json", "d9_validation.json", "d10_legacy_comparison.json",
)


def check_artifact_inventory(paths):
    findings, data = [], {}
    entities = {}
    for entity in EXPECTED_PROCESSED_ENTITIES:
        files = sorted((paths.processed_dir / entity).rglob("*.parquet")) \
            if (paths.processed_dir / entity).exists() else []
        nbytes = sum(f.stat().st_size for f in files)
        entities[entity] = {"files": len(files), "bytes": int(nbytes)}
    missing = [e for e, v in entities.items() if v["files"] == 0]
    data["entities"] = entities
    data["missing_entities"] = missing
    findings.append(_finding(
        "ARTIFACT-INVENTORY", "BLOCKER", not missing,
        {"missing_entities": missing},
        "canonical entity absent" if missing else ""))
    # temp / unexpected files
    tmp = sorted(str(p) for p in paths.v2_root.rglob(".tmp-*.parquet"))
    unexpected = []
    for entity in EXPECTED_PROCESSED_ENTITIES:
        base = paths.processed_dir / entity
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if f.is_file() and f.suffix == ".parquet" \
                    and "__" not in f.name:
                unexpected.append(str(f.relative_to(paths.root)))
    data["tmp_files"] = tmp
    data["unexpected_files"] = unexpected
    findings.append(_finding(
        "ARTIFACT-INVENTORY", "BLOCKER", not tmp and not unexpected,
        {"tmp_files": tmp, "unexpected_files": unexpected},
        "partial/corrupt or stray outputs" if (tmp or unexpected) else ""))
    reports = {name: (paths.reports_dir / name).exists()
               for name in EXPECTED_REPORTS}
    data["reports_present"] = reports
    findings.append(_finding(
        "ARTIFACT-INVENTORY", "MAJOR", all(reports.values()),
        {"missing_reports": [k for k, v in reports.items() if not v]},
        "validation evidence report absent" if not all(
            reports.values()) else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §3 contract validation (pyarrow schema scans; telemetry must be absent).
# ---------------------------------------------------------------------------

def _entity_contract_columns(entity):
    if entity in ("driver_lap_state",):
        return D6S.STATE_COLUMNS, True
    if entity == "race_quality":
        return D6S.QUALITY_COLUMNS, True
    if entity == "driver_lap_state_d7":
        return D7S.ENRICHED_COLUMNS, True
    if entity == "driver_lap_state_d9":
        return D9S.STATE_COLUMNS, True
    if entity == "race_driver_labels":
        return D9S.LABEL_COLUMNS, True
    return C.get_table(entity).column_names(), False


# Spot dtype expectations: column -> accepted pandas dtype kinds. D5 files
# use native (non-nullable) dtypes, so an int-logical column may read as
# int64 (no nulls in that file) or float64 (nulls present); both are
# contract-conformant physical representations of the logical type.
_DTYPE_SPOTS = {
    "races": {"race_id": {"O"}, "season": {"i"}},
    "results": {"position_final": {"i", "f"}, "dnf_flag": {"b"}},
    "driver_laps": {"lap_number": {"i", "f"},
                    "session_time_end_s": {"f"}},
    "pit_stops": {"stop_sequence": {"i", "f"}, "pit_in_s": {"f"}},
    "stints": {"stint_number": {"i", "f"}, "start_lap": {"i", "f"}},
    "weather": {"observed_at_s": {"f"}, "wind_speed": {"f"}},
    "race_control": {"message_seq": {"i"}, "observed_at_s": {"f"}},
    "driver_lap_state": {"state_time_s": {"f"}, "lap_number": {"i"}},
    "driver_lap_state_d7": {"wx_air_temp_c": {"f"},
                            "stint_start_lap": {"i"}},
    "driver_lap_state_d9": {"track_state": {"O"},
                            "race_leader_laps_at_state": {"i"}},
    "race_driver_labels": {"winner_flag": {"b", "O"}, "points": {"f"}},
    "hist_results": {"points": {"f"}},
}


def check_contracts(paths):
    import pyarrow.parquet as pq

    findings, data = [], {"drifted_files": [], "dtype_mismatches": []}
    tel_dir = paths.processed_dir / "telemetry_summary"
    data["telemetry_summary_present"] = tel_dir.exists()
    findings.append(_finding(
        "CONTRACTS", "BLOCKER", not tel_dir.exists(),
        {"telemetry_summary_dir": str(tel_dir)},
        "telemetry canonically retained against ADR-0001"
        if tel_dir.exists() else ""))
    checked = 0
    for entity in EXPECTED_PROCESSED_ENTITIES:
        try:
            expected, ordered = _entity_contract_columns(entity)
        except KeyError:
            continue
        base = paths.processed_dir / entity
        if not base.exists():
            continue
        files = sorted(base.rglob("*.parquet"))
        spot_done = False
        for f in files:
            names = pq.read_schema(f).names
            if ordered:
                ok = (names == list(expected))
            else:
                ok = (set(names) == set(expected))
            checked += 1
            if not ok:
                data["drifted_files"].append(
                    {"file": str(f.relative_to(paths.root)),
                     "extra": sorted(set(names) - set(expected)),
                     "missing": sorted(set(expected) - set(names))})
            if not spot_done and entity in _DTYPE_SPOTS:
                df = pd.read_parquet(f, engine="pyarrow")
                for col, kinds in _DTYPE_SPOTS[entity].items():
                    if col not in df.columns:
                        data["dtype_mismatches"].append(
                            {"file": str(f.relative_to(paths.root)),
                             "column": col, "issue": "absent"})
                        continue
                    got = df[col].dtype.kind
                    # nullable BooleanDtype reports kind 'b'; object columns
                    # holding bools/None (winner_flag with nulls) read as 'O'
                    if got not in kinds:
                        data["dtype_mismatches"].append(
                            {"file": str(f.relative_to(paths.root)),
                             "column": col, "dtype": str(df[col].dtype)})
                spot_done = True
    data["files_checked"] = checked
    findings.append(_finding(
        "CONTRACTS", "BLOCKER", not data["drifted_files"],
        {"drifted_files": data["drifted_files"][:20],
         "n_drifted": len(data["drifted_files"]), "checked": checked},
        f"{len(data['drifted_files'])} files drifted from contract"
        if data["drifted_files"] else ""))
    findings.append(_finding(
        "CONTRACTS", "MAJOR", not data["dtype_mismatches"],
        {"dtype_mismatches": data["dtype_mismatches"][:20]},
        "unexpected physical dtypes" if data["dtype_mismatches"] else ""))
    return findings, data

# ---------------------------------------------------------------------------
# §4 primary keys.
# ---------------------------------------------------------------------------

def _pk(entity):
    if entity == "driver_lap_state":
        return list(D6S.state_primary_key())
    if entity == "race_quality":
        return list(D6S.quality_primary_key())
    if entity == "driver_lap_state_d7":
        return list(D7S.enriched_primary_key())
    if entity == "driver_lap_state_d9":
        return list(D9S.state_primary_key())
    if entity == "race_driver_labels":
        return list(D9S.label_primary_key())
    return list(C.get_table(entity).primary_key)


def check_pk(paths):
    import pyarrow.parquet as pq

    findings, data = [], {"tables": {}}
    bad = []
    for entity in EXPECTED_PROCESSED_ENTITIES:
        base = paths.processed_dir / entity
        if not base.exists():
            continue
        keys = _pk(entity)
        dup = null = rows = 0
        present = True
        for f in sorted(base.rglob("*.parquet")):
            names = pq.read_schema(f).names
            cols = [c for c in keys if c in names]
            if any(c not in names for c in keys):
                present = False
                break
            df = pd.read_parquet(f, engine="pyarrow", columns=cols)
            rows += len(df)
            dup += int(df.duplicated(subset=keys).sum())
            null += int(df[keys].isna().any(axis=1).sum())
        data["tables"][entity] = {"rows": int(rows), "duplicate_pks": int(dup),
                                  "null_pks": int(null),
                                  "pk_present": bool(present)}
        if dup or null or not present:
            bad.append(entity)
    findings.append(_finding(
        "PK", "BLOCKER", not bad,
        {"bad_tables": bad, "tables": data["tables"]},
        f"PK violations in: {bad}" if bad else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §5 foreign keys (exact orphan counts).
# ---------------------------------------------------------------------------

def _fk_pairs(paths):
    """Yield (name, child_frame, child_cols, parent_frame, parent_cols)."""
    seasons_a = list(range(2018, 2026))
    seasons_b = list(range(1950, 2026))
    races = _read_entity_files(paths, "races", seasons_a)
    results = _read_entity_files(paths, "results", seasons_a)
    laps = _read_entity_files(paths, "driver_laps", seasons_a)
    pits = _read_entity_files(paths, "pit_stops", seasons_a)
    stints = _read_entity_files(paths, "stints", seasons_a)
    weather = _read_entity_files(paths, "weather", seasons_a)
    rc = _read_entity_files(paths, "race_control", seasons_a)
    d6 = _read_state_files(paths, "driver_lap_state", seasons_a,
                           D6S.d6_unit_id)
    d7 = _read_state_files(paths, "driver_lap_state_d7", seasons_a,
                           D7S.d7_unit_id)
    d9 = _read_state_files(paths, "driver_lap_state_d9", seasons_a,
                           D9S.d9_unit_id)
    labels = _read_state_files(paths, "race_driver_labels", seasons_a,
                               D9S.d9_unit_id)
    hist_races = _read_entity_files(paths, "hist_races", seasons_b)
    hist_results = _read_entity_files(paths, "hist_results", seasons_b)
    hist_drivers = _read_entity_files(paths, "hist_drivers", seasons_b)
    hist_cons = _read_entity_files(paths, "hist_constructors", seasons_b)
    hist_circuits = _read_entity_files(paths, "hist_circuits", seasons_b)
    return [
        ("results.race_id->races", results, ["race_id"], races, ["race_id"]),
        ("driver_laps.race_id->races", laps, ["race_id"], races, ["race_id"]),
        ("driver_laps.(race,driver)->results", laps,
         ["race_id", "driver_id"], results, ["race_id", "driver_id"]),
        ("pit_stops.(race,driver)->driver_laps", pits,
         ["race_id", "driver_id"], laps, ["race_id", "driver_id"]),
        ("stints.(race,driver)->driver_laps", stints,
         ["race_id", "driver_id"], laps, ["race_id", "driver_id"]),
        ("weather.race_id->races", weather, ["race_id"], races, ["race_id"]),
        ("race_control.race_id->races", rc, ["race_id"], races, ["race_id"]),
        ("d6state.(race,driver)->results", d6, ["race_id", "driver_id"],
         results, ["race_id", "driver_id"]),
        ("d7state.pk==d6state.pk", d7,
         ["race_id", "driver_id", "lap_number"], d6,
         ["race_id", "driver_id", "lap_number"]),
        ("d9state.pk==d6state.pk", d9,
         ["race_id", "driver_id", "lap_number"], d6,
         ["race_id", "driver_id", "lap_number"]),
        ("labels.pk==results.pk", labels, ["race_id", "driver_id"], results,
         ["race_id", "driver_id"]),
        ("hist_results.(season,round)->hist_races", hist_results,
         ["season", "round_no"], hist_races, ["season", "round_no"]),
        ("hist_results.driver->hist_drivers", hist_results, ["driver_id"],
         hist_drivers, ["driver_id"]),
        ("hist_results.constructor->hist_constructors",
         hist_results[hist_results["constructor_id"].notna()],
         ["constructor_id"], hist_cons, ["constructor_id"]),
        ("hist_races.circuit->hist_circuits",
         hist_races[hist_races["circuit_id"].notna()], ["circuit_id"],
         hist_circuits, ["circuit_id"]),
        ("results.driver->hist_drivers(Tier-B cross-check)",
         results[~results["driver_id"].isin(
             set(hist_drivers["driver_id"]))], ["driver_id"],
         hist_drivers, ["driver_id"]),
    ]


def check_fk(paths):
    findings, data = [], {"relations": {}}
    bad = []
    for name, child, cc, parent, pc in _fk_pairs(paths):
        if len(child) == 0:
            orphans = 0
        else:
            ck = child[cc].astype(str).agg("|".join, axis=1) \
                if len(cc) > 1 else child[cc[0]].astype(str)
            pk = parent[pc].astype(str).agg("|".join, axis=1) \
                if len(pc) > 1 else parent[pc[0]].astype(str)
            orphans = int((~ck.isin(set(pk))).sum())
        data["relations"][name] = {"child_rows": int(len(child)),
                                   "orphans": orphans}
        if orphans:
            bad.append(name)
    findings.append(_finding(
        "FK", "BLOCKER", not bad,
        {"bad_relations": bad, "relations": data["relations"]},
        f"FK orphans in: {bad}" if bad else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §6 identity adversarial audit.
# ---------------------------------------------------------------------------

def check_identity(paths):
    findings, data = [], {}
    seasons_a = list(range(2018, 2026))
    results = _read_entity_files(paths, "results", seasons_a)
    state = _read_state_files(paths, "driver_lap_state", seasons_a,
                              D6S.d6_unit_id)
    races = _read_entity_files(paths, "races", seasons_a)

    # driver numbers are attributes: drivers spanning multiple numbers
    nums = results.dropna(subset=["driver_number"]).groupby(
        "driver_id")["driver_number"].apply(
            lambda s: sorted({int(v) for v in s}))
    multi = {d: v for d, v in nums.items() if len(v) > 1}
    data["drivers_with_multiple_numbers"] = multi
    findings.append(_finding(
        "IDENTITY", "INFORMATIONAL", True,
        {"multi_number_drivers": multi},
        "attribute variation, not a key violation"))

    # (race, number) must resolve to exactly one driver_id
    coll = results.dropna(subset=["driver_number"]).groupby(
        ["race_id", "driver_number"])["driver_id"].nunique()
    collisions = int((coll > 1).sum())
    data["race_number_collisions"] = collisions
    findings.append(_finding(
        "IDENTITY", "BLOCKER", collisions == 0,
        {"collisions": collisions},
        "car number maps to two drivers in one race" if collisions else ""))

    # constructor season scoping + renames present as distinct slugs
    cons = _read_entity_files(paths, "hist_constructors", list(range(1950,
                                                                     2026)))
    data["constructor_pk_unique"] = bool(
        not cons.duplicated(subset=["constructor_id", "season"]).any())
    slugs = set(cons["constructor_id"].dropna().unique())
    renames = {"toro_rosso": "toro_rosso" in slugs,
               "alphatauri": "alphatauri" in slugs,
               "rb": "rb" in slugs,
               "racing_point": "racing_point" in slugs,
               "aston_martin": "aston_martin" in slugs}
    data["rename_slugs_present"] = renames
    findings.append(_finding(
        "IDENTITY", "BLOCKER",
        data["constructor_pk_unique"] and all(renames.values()),
        {"pk_unique": data["constructor_pk_unique"], "renames": renames},
        "constructor identity collision or missing rename slug"
        if not (data["constructor_pk_unique"]
                and all(renames.values())) else ""))

    # circuit per (season, round): non-null Tier-A + Tier-A vs Tier-B match
    data["races_circuit_null"] = int(races["circuit_id"].isna().sum())
    hist_races = _read_entity_files(paths, "hist_races", seasons_a)
    a = races[["season", "round_no", "circuit_id"]].drop_duplicates()
    b = hist_races[["season", "round_no", "circuit_id"]].drop_duplicates()
    m = a.merge(b, on=["season", "round_no"], how="left",
                suffixes=("_a", "_b"))
    mismatch = int(((m["circuit_id_a"] != m["circuit_id_b"])
                    & m["circuit_id_a"].notna()
                    & m["circuit_id_b"].notna()).sum())
    data["circuit_mismatches_tiera_vs_tierb"] = mismatch
    findings.append(_finding(
        "IDENTITY", "BLOCKER",
        data["races_circuit_null"] == 0 and mismatch == 0,
        {"circuit_nulls": data["races_circuit_null"],
         "mismatches": mismatch},
        "circuit identity failure" if (
            data["races_circuit_null"] or mismatch) else ""))

    # race identity uniqueness
    data["race_ids"] = int(races["race_id"].nunique())
    data["event_ids"] = int(races["event_id"].nunique())
    findings.append(_finding(
        "IDENTITY", "BLOCKER",
        data["race_ids"] == 173 and data["event_ids"] == 173,
        {"race_ids": data["race_ids"], "event_ids": data["event_ids"]},
        "duplicate race identity" if (
            data["race_ids"] != 173 or data["event_ids"] != 173) else ""))

    # display names never participate in keys (schema-level)
    name_in_pk = []
    for table in list(C.ALL_TABLES):
        for k in table.primary_key:
            if "name" in str(k).lower() or "abbreviation" in str(k).lower():
                name_in_pk.append((table.entity, k))
    for cols, label in ((D6S.STATE_COLUMNS, "d6-state"),
                        (D7S.ENRICHED_COLUMNS, "d7-state"),
                        (D9S.STATE_COLUMNS, "d9-state"),
                        (D9S.LABEL_COLUMNS, "d9-labels")):
        for c in ("event_name", "driver_abbreviation"):
            if c in list(D9S.state_primary_key()) + list(
                    D9S.label_primary_key()) and label.startswith("d9"):
                name_in_pk.append((label, c))
    data["display_names_in_keys"] = name_in_pk
    findings.append(_finding(
        "IDENTITY", "BLOCKER", not name_in_pk,
        {"display_names_in_keys": name_in_pk},
        "display string used as a key" if name_in_pk else ""))

    # builder joins never key on display strings (code-level)
    import re as _re
    bad_joins = []
    for mod in ("d6", "d7", "d9", "tiera"):
        src = Path(__file__).with_name(f"{mod}.py").read_text()
        for i, line in enumerate(src.splitlines(), 1):
            if ".merge(" in line and "event_name" in line:
                bad_joins.append(f"{mod}.py:{i}")
    data["display_name_joins_in_code"] = bad_joins
    findings.append(_finding(
        "IDENTITY", "BLOCKER", not bad_joins,
        {"display_name_joins": bad_joins},
        "join on display name in builder code" if bad_joins else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §7 + §10 temporal availability + predictive-eligibility audit (static).
# ---------------------------------------------------------------------------

_PREDICTIVE_SET = {C.Availability.LAP_START, C.Availability.IN_LAP,
                   C.Availability.LAP_END}

_OUTCOME_NAMES = {"position_final", "classified_position", "position_text",
                  "status_text", "points", "laps_completed", "dnf_flag",
                  "winner_flag", "podium_flag", "classified_flag",
                  "points_finish_flag"}

_NON_ELIGIBLE_METADATA = {
    "source_unit_status", "shortened_race", "quality_note",
    "partial_reason", "total_laps_scheduled", "observed_leader_laps",
    "event_name", "constructor_id", "driver_number", "driver_abbreviation",
    "season", "round_no", "event_id", "circuit_id", "race_id", "driver_id",
    "lap_number", "state_time_s", "wx_observed_at_s", "wx_age_s",
    "rc_last_message_seq", "rc_last_message_observed_at_s",
    "rc_last_message_age_s", "rc_last_message_lap_number",
    "rc_last_message_category", "rc_last_message_flag",
    "rc_last_message_text", "pit_last_in_lap", "pit_last_in_s",
    "pit_last_out_lap", "pit_last_out_s", "stint_start_lap",
    "stint_tyre_age_at_start",
}


def _eligible_fields():
    out = []
    for f in D6S.STATE_FIELDS:
        if f.predictive_eligible:
            out.append((f.name, f.availability.value, "d6-state",
                        f.source, f.lineage_kind
                        if hasattr(f, "lineage_kind") else "source_observation"))
    for f in D7S.EXTENSION_FIELDS:
        if f.predictive_eligible:
            out.append((f.name, f.availability.value, "d7-extension",
                        f.source, f.lineage_kind))
    for f in D9S.STATE_EXTENSION_FIELDS:
        if f.predictive_eligible:
            out.append((f.name, f.availability.value, "d9-derived",
                        f.source, f.lineage_kind))
    return out


def check_temporal_availability():
    findings, data = [], {}
    eligible = _eligible_fields()
    data["eligible_fields"] = [
        {"field": n, "availability": a, "table": t, "source": s,
         "lineage": k} for n, a, t, s, k in eligible]
    data["n_eligible"] = len(eligible)
    outside = [n for n, a, _, _, _ in eligible
               if a not in {v.value for v in _PREDICTIVE_SET}]
    outcome = [n for n, _, _, _, _ in eligible if n in _OUTCOME_NAMES]
    model_feature = [n for n, _, t, _, k in eligible if k == "model_feature"]
    data["outside_predictive_set"] = outside
    data["outcome_named"] = outcome
    data["model_feature_count"] = len(model_feature)
    findings.append(_finding(
        "TEMPORAL-AVAILABILITY", "BLOCKER",
        not outside and not outcome and not model_feature,
        {"outside": outside, "outcome_named": outcome,
         "model_features": model_feature},
        "ineligible-by-contract field marked eligible" if (
            outside or outcome or model_feature) else ""))
    return findings, data


def check_eligibility():
    findings, data = [], {}
    eligible = {n for n, _, _, _, _ in _eligible_fields()}
    meta_eligible = sorted(eligible & _NON_ELIGIBLE_METADATA)
    data["eligible_fields"] = sorted(eligible)
    data["metadata_marked_eligible"] = meta_eligible
    findings.append(_finding(
        "ELIGIBILITY", "BLOCKER", not meta_eligible,
        {"metadata_marked_eligible": meta_eligible},
        "quality/metadata field marked predictive-eligible"
        if meta_eligible else ""))
    # every D9 outcome field must be LABEL_ONLY + non-eligible; identity
    # must be non-eligible (keys are not outcomes and not features)
    bad_labels = []
    for f in D9S.LABEL_FIELDS:
        if f.predictive_eligible:
            bad_labels.append((f.name, "eligible"))
        elif f.lineage_kind in (D9S.OUTCOME_FACT, D9S.OUTCOME_DERIVED_FACT):
            if f.availability is not C.Availability.LABEL_ONLY:
                bad_labels.append((f.name, "outcome not LABEL_ONLY"))
        elif f.lineage_kind != D9S.IDENTITY:
            bad_labels.append((f.name, "unknown lineage"))
    data["bad_label_fields"] = bad_labels
    findings.append(_finding(
        "ELIGIBILITY", "BLOCKER", not bad_labels,
        {"bad_label_fields": bad_labels},
        "label field eligible or mis-availabilitied" if bad_labels else ""))
    return findings, data

# ---------------------------------------------------------------------------
# §8 adversarial future-mutation suites (executed, not just referenced).
# ---------------------------------------------------------------------------

LEAKAGE_TEST_FILES = ["tests/test_v2_d6.py", "tests/test_v2_d7.py",
                      "tests/test_v2_d9.py"]
RECOVERY_TEST_FILES = ["tests/test_v2_idempotency.py",
                       "tests/test_v2_manifests.py",
                       "tests/test_v2_storage.py", "tests/test_v2_retry.py",
                       "tests/test_v2_cli.py"]


def _run_pytest(root: Path, files: list, timeout_s: int = 900) -> dict:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest"] + files + ["-q"],
            cwd=str(root), capture_output=True, text=True,
            timeout=timeout_s)
        out = (proc.stdout + proc.stderr)[-3000:]
        return {"returncode": proc.returncode,
                "elapsed_s": round(time.perf_counter() - started, 1),
                "tail": out, "timed_out": False}
    except subprocess.TimeoutExpired:
        return {"returncode": None,
                "elapsed_s": round(time.perf_counter() - started, 1),
                "tail": "", "timed_out": True}


def check_mutation(root: Path):
    findings, data = [], {}
    res = _run_pytest(root, LEAKAGE_TEST_FILES)
    data["leakage_suites"] = res
    findings.append(_finding(
        "FUTURE-MUTATION", "BLOCKER", res["returncode"] == 0,
        {"files": LEAKAGE_TEST_FILES, "result": res},
        "future-mutation leakage suite red" if res["returncode"] != 0
        else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §9 state/label physical separation.
# ---------------------------------------------------------------------------

def check_separation(paths):
    findings, data = [], {}
    labels = set(C.RESULTS.label_columns())
    bad = {}
    for entity, seasons, unit in (
            ("driver_lap_state", range(2018, 2026), D6S.d6_unit_id),
            ("driver_lap_state_d7", range(2018, 2026), D7S.d7_unit_id),
            ("driver_lap_state_d9", range(2018, 2026), D9S.d9_unit_id)):
        cols = set()
        for season in seasons:
            f = (paths.processed_dir / entity / f"season={season}"
                 / f"{entity}__{unit(int(season))}.parquet")
            if f.exists():
                import pyarrow.parquet as pq

                cols |= set(pq.read_schema(f).names)
        hit = sorted(cols & labels)
        bad[entity] = hit
    data["label_columns_in_state"] = bad
    findings.append(_finding(
        "SEPARATION", "BLOCKER", not any(bad.values()),
        {"label_columns_in_state": bad},
        "outcome column present in canonical state" if any(
            bad.values()) else ""))
    # labels grain == official results grain (row counts + PK sets)
    for season in range(2018, 2026):
        lf = (paths.processed_dir / "race_driver_labels"
              / f"season={season}"
              / f"race_driver_labels__{D9S.d9_unit_id(int(season))}.parquet")
        rf = sorted((paths.processed_dir / "results"
                     / f"season={season}").glob("*.parquet"))
        if not lf.exists():
            continue
        lb = pd.read_parquet(lf, engine="pyarrow")
        rs = pd.concat([pd.read_parquet(f, engine="pyarrow") for f in rf],
                       ignore_index=True) if rf else pd.DataFrame()
        if len(lb) != len(rs) or set(
                map(tuple, lb[["race_id", "driver_id"]].values.tolist())) != set(
                map(tuple, rs[["race_id", "driver_id"]].values.tolist())):
            findings.append(_finding(
                "SEPARATION", "BLOCKER", False,
                {"season": season, "label_rows": len(lb),
                 "result_rows": len(rs)},
                f"label grain diverged from results in {season}"))
            data["label_grain_ok"] = False
            return findings, data
    data["label_grain_ok"] = True
    findings.append(_finding("SEPARATION", "BLOCKER", True, {},
                             ""))
    return findings, data


# ---------------------------------------------------------------------------
# §11 label audit.
# ---------------------------------------------------------------------------

def check_labels(paths):
    findings, data = [], {}
    parts = []
    for season in range(2018, 2026):
        f = (paths.processed_dir / "race_driver_labels" / f"season={season}"
             / f"race_driver_labels__{D9S.d9_unit_id(int(season))}.parquet")
        parts.append(pd.read_parquet(f, engine="pyarrow"))
    lb = pd.concat(parts, ignore_index=True)
    data["rows"] = int(len(lb))
    data["token_vocab"] = {str(k): int(v) for k, v in
                           lb["position_text"].value_counts(
                               dropna=False).items()}
    data["status_vocab_n"] = int(lb["status_text"].nunique())
    data["winners"] = int((lb["position_final"] == 1).sum())
    per_race = lb[lb["position_final"] == 1].groupby("race_id").size()
    data["races_with_winner_neq_1"] = sorted(
        str(r) for r, c in per_race.items() if c != 1)
    data["podium_rows"] = int(lb["position_final"].isin([1, 2, 3]).sum())
    data["points_finishers"] = int(lb["points_finish_flag"].sum())
    data["classified"] = int(lb["classified_flag"].sum())
    data["final_null_rows"] = lb[lb["position_final"].isna()][
        ["race_id", "driver_id", "position_text",
         "status_text"]].to_dict(orient="records")
    ok = (len(lb) == 3458 and data["winners"] == 173
          and not data["races_with_winner_neq_1"]
          and data["podium_rows"] == 519
          and len(data["final_null_rows"]) == 3
          and {r["race_id"] for r in data["final_null_rows"]}
          == {"2021-r22-R", "2022-r02-R", "2023-r15-R"})
    findings.append(_finding(
        "LABELS", "MAJOR", ok, data,
        "label invariant violated" if not ok else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §12 missingness audit vs frozen stage reports.
# ---------------------------------------------------------------------------

def check_missingness(paths):
    findings, data = [], {}
    try:
        d6rep = json.loads((paths.reports_dir / "d6_validation.json")
                           .read_text())["validation"]["missingness"]
        d7rep = json.loads((paths.reports_dir / "d7_validation.json")
                           .read_text())["validation"]["extension_missingness"]
    except (FileNotFoundError, KeyError) as exc:
        findings.append(_finding(
            "MISSINGNESS", "MAJOR", False, {"error": str(exc)},
            "stage validation report absent/unreadable"))
        return findings, data
    drift = []
    for season in range(2018, 2026):
        st = pd.read_parquet(
            paths.processed_dir / "driver_lap_state" / f"season={season}"
            / f"driver_lap_state__d6-{season}.parquet", engine="pyarrow")
        for col, counts in d6rep.get(str(season), {}).items():
            if col not in st.columns:
                continue
            now = int(st[col].isna().sum())
            if now != int(counts):
                drift.append({"season": season, "column": col,
                              "stage_report": int(counts), "now": now})
        en = pd.read_parquet(
            paths.processed_dir / "driver_lap_state_d7" / f"season={season}"
            / f"driver_lap_state_d7__d7-{season}.parquet", engine="pyarrow")
        for col, counts in d7rep.get(str(season), {}).items():
            if col not in en.columns:
                continue
            now = int(en[col].isna().sum())
            if now != int(counts):
                drift.append({"season": season, "column": col,
                              "stage_report": int(counts), "now": now})
    data["drifted_columns"] = drift
    findings.append(_finding(
        "MISSINGNESS", "MAJOR", not drift,
        {"drifted_columns": drift},
        f"missingness drifted in {len(drift)} columns" if drift else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §13 source-anomaly regression (expected values from closed-stage docs).
# ---------------------------------------------------------------------------

def check_anomalies(paths):
    findings, data = [], {"anomalies": {}}

    def rec(name, measured, expected, extra=None):
        ok = (measured == expected)
        data["anomalies"][name] = {"measured": measured,
                                   "expected": expected,
                                   "match": bool(ok),
                                   **(extra or {})}
        return ok

    st18 = pd.read_parquet(
        paths.processed_dir / "driver_lap_state" / "season=2018"
        / "driver_lap_state__d6-2018.parquet", engine="pyarrow")
    all_state = pd.concat([
        pd.read_parquet(paths.processed_dir / "driver_lap_state"
                        / f"season={s}"
                        / f"driver_lap_state__d6-{s}.parquet",
                        engine="pyarrow")
        for s in range(2018, 2026)], ignore_index=True)
    ok = True
    ok &= rec("belgium_2021_rows",
              int((all_state["race_id"] == "2021-r12-R").sum()), 60)
    ok &= rec("japan_2022_rows",
              int((all_state["race_id"] == "2022-r18-R").sum()), 507)
    mon = all_state[all_state["race_id"] == "2022-r07-R"]
    ok &= rec("monaco_2022_shortened",
              bool((mon["shortened_race"] == True).all()), True)  # noqa: E712
    ok &= rec("monaco_2022_tyre_life_nulls",
              int(mon["tyre_life"].isna().sum()) > 100, True)
    ok &= rec("track_status_nulls_2018",
              int(st18["track_status"].isna().sum()), 1317)
    rc02 = pd.read_parquet(
        paths.processed_dir / "race_control" / "season=2018"
        / "race_control__2018-r02-R.parquet", engine="pyarrow")
    ok &= rec("bahrain_2018_rc_total", int(len(rc02)), 69)
    ok &= rec("bahrain_2018_rc_untimed",
              int(rc02["observed_at_s"].isna().sum()), 69)
    pits = _concat_entity(paths, "pit_stops", list(range(2018, 2026)))
    ok &= rec("pit_in_only", int(
        (pits["pit_in_s"].notna() & pits["pit_out_s"].isna()).sum()), 246)
    ok &= rec("pit_out_only", int(
        (pits["pit_out_s"].notna() & pits["pit_in_s"].isna()).sum()), 159)
    labels = pd.concat([
        pd.read_parquet(paths.processed_dir / "race_driver_labels"
                        / f"season={s}"
                        / f"race_driver_labels__d9-{s}.parquet",
                        engine="pyarrow") for s in range(2018, 2026)],
        ignore_index=True)
    w3 = labels[labels["position_final"].isna()][
        ["race_id", "driver_id"]].values.tolist()
    ok &= rec("null_final_rows", len(w3), 3,
              {"rows": [[str(a), str(b)] for a, b in w3]})
    wx = pd.concat([
        pd.read_parquet(paths.processed_dir / "driver_lap_state_d7"
                        / f"season={s}"
                        / f"driver_lap_state_d7__d7-{s}.parquet",
                        engine="pyarrow",
                        columns=["race_id", "wx_age_s"])
        for s in range(2018, 2026)], ignore_index=True)
    ok &= rec("weather_max_staleness_s",
              round(float(wx["wx_age_s"].max()), 3), 477.348)
    mi25 = pd.read_parquet(
        paths.processed_dir / "driver_lap_state_d7" / "season=2025"
        / "driver_lap_state_d7__d7-2025.parquet", engine="pyarrow",
        columns=["race_id", "stint_number"])
    mi25 = mi25[mi25["race_id"] == "2025-r06-R"]
    ok &= rec("miami_2025_stint_nulls",
              int(mi25["stint_number"].isna().sum()), 446)
    findings.append(_finding(
        "ANOMALIES", "MAJOR", bool(ok), data["anomalies"],
        "documented anomaly changed or disappeared" if not ok else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §14 PARTIAL / shortened races.
# ---------------------------------------------------------------------------

def check_partial(paths):
    findings, data = [], {}
    from v2.manifests import Manifest, UnitStatus

    statuses = {}
    for season in range(2018, 2026):
        man = Manifest.load(paths.manifest_path(f"tiera-{season}.json"))
        for uid, e in man.units.items():
            if e.status in (UnitStatus.COMPLETE, UnitStatus.PARTIAL):
                statuses[e.race_id or uid] = e.status.value
    data["partial_races"] = sorted(
        [r for r, s in statuses.items() if s == "partial"])
    ok = data["partial_races"] == ["2021-r12-R", "2022-r18-R"]
    findings.append(_finding(
        "PARTIAL", "MAJOR", ok, {"partial_races": data["partial_races"]},
        "PARTIAL set changed" if not ok else ""))
    # no universal modelling-exclusion column exists in any state schema
    bad = [c for cols in (D6S.STATE_COLUMNS, D7S.ENRICHED_COLUMNS,
                          D9S.STATE_COLUMNS) for c in cols
           if "exclu" in c.lower() or "eligib" in c.lower()]
    data["exclusion_columns"] = bad
    findings.append(_finding(
        "PARTIAL", "BLOCKER", not bad, {"exclusion_columns": bad},
        "modelling exclusion encoded in canonical state" if bad else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §15 weather temporal audit (independent recomputation).
# ---------------------------------------------------------------------------

def check_weather(paths):
    findings, data = [], {}
    parts = []
    for season in range(2018, 2026):
        parts.append(pd.read_parquet(
            paths.processed_dir / "driver_lap_state_d7" / f"season={season}"
            / f"driver_lap_state_d7__d7-{season}.parquet", engine="pyarrow"))
    t = pd.concat(parts, ignore_index=True)
    both = t["wx_observed_at_s"].notna() & t["state_time_s"].notna()
    viol = int((t.loc[both, "wx_observed_at_s"]
                > t.loc[both, "state_time_s"] + 1e-6).sum())
    age_bad = int((t.loc[t["wx_age_s"].notna(), "wx_age_s"] < -1e-6).sum())
    age_recomputed = (t.loc[both, "state_time_s"]
                      - t.loc[both, "wx_observed_at_s"])
    age_match = int((((t.loc[both, "wx_age_s"] - age_recomputed).abs() > 1e-6)
                     ).sum())
    data["violations"] = viol
    data["negative_ages"] = age_bad
    data["age_recompute_mismatches"] = age_match
    data["prior_attachment_frac"] = round(float(both.mean()), 6)
    data["max_staleness_s"] = round(float(t["wx_age_s"].max()), 3)
    stale = t[t["wx_age_s"] > 60].groupby("race_id").size().to_dict()
    stale = {str(k): int(v) for k, v in stale.items()}
    data["stale_gt60s_counts"] = stale
    top3 = sorted(stale.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    data["top3_stale_races"] = top3
    ger = t[(t["race_id"] == "2019-r11-R") & (t["wx_rainfall"] == True)]  # noqa: E712
    data["germany2019_rain_states"] = int(len(ger))
    dry = t[t["race_id"].isin(["2018-r01-R", "2023-r01-R", "2024-r01-R"])
            & (t["wx_rainfall"] == True)]  # noqa: E712
    data["dry_bahrain_rain_states"] = int(len(dry))
    ok = (viol == 0 and age_bad == 0 and age_match == 0
          and data["prior_attachment_frac"] == 1.0
          and data["max_staleness_s"] == 477.348
          and data["top3_stale_races"]
          == [("2020-r01-R", 100), ("2023-r14-R", 27), ("2018-r09-R", 9)]
          and data["germany2019_rain_states"] == 1033
          and data["dry_bahrain_rain_states"] == 0)
    findings.append(_finding(
        "WEATHER", "BLOCKER", ok, data,
        "weather temporal violation or coverage drift" if not ok else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §16 race-control temporal audit.
# ---------------------------------------------------------------------------

def check_race_control(paths):
    findings, data = [], {}
    msgs = total = timed = 0
    for season in range(2018, 2026):
        for f in sorted((paths.processed_dir / "race_control"
                         / f"season={season}").glob("*.parquet")):
            rc = pd.read_parquet(f, engine="pyarrow")
            total += len(rc)
            timed += int(rc["observed_at_s"].notna().sum())
    data["messages_total"] = total
    data["messages_timestamped"] = timed
    data["messages_untimestamped"] = total - timed
    parts = []
    for season in range(2018, 2026):
        parts.append(pd.read_parquet(
            paths.processed_dir / "driver_lap_state_d7" / f"season={season}"
            / f"driver_lap_state_d7__d7-{season}.parquet", engine="pyarrow",
            columns=["race_id", "state_time_s",
                     "rc_last_message_observed_at_s",
                     "rc_last_message_age_s", "rc_last_message_seq"]))
    t = pd.concat(parts, ignore_index=True)
    both = t["rc_last_message_observed_at_s"].notna(
    ) & t["state_time_s"].notna()
    viol = int((t.loc[both, "rc_last_message_observed_at_s"]
                > t.loc[both, "state_time_s"] + 1e-6).sum())
    age_bad = int((t.loc[t["rc_last_message_age_s"].notna(),
                         "rc_last_message_age_s"] < -1e-6).sum())
    r02 = t[t["race_id"] == "2018-r02-R"]
    data["violations"] = viol
    data["negative_ages"] = age_bad
    data["r02_states_with_rc"] = int(r02["rc_last_message_seq"].notna().sum())
    data["r02_states"] = int(len(r02))
    # D9 track-token distribution recomputed vs D9 report
    try:
        d9rep = json.loads((paths.reports_dir / "d9_validation.json")
                           .read_text())["validation"]["track_state_token_counts"]
    except (FileNotFoundError, KeyError):
        d9rep = None
    tokens = {}
    for season in range(2018, 2026):
        st = pd.read_parquet(
            paths.processed_dir / "driver_lap_state_d9" / f"season={season}"
            / f"driver_lap_state_d9__d9-{season}.parquet", engine="pyarrow",
            columns=["track_state"])
        tokens[str(season)] = {str(k) if k is not None else "null": int(v)
                               for k, v in st["track_state"].value_counts(
                                   dropna=False).to_dict().items()}
    data["track_token_match_d9_report"] = (tokens == d9rep)
    ok = (total == 14992 and timed == 14923 and total - timed == 69
          and viol == 0 and age_bad == 0
          and data["r02_states_with_rc"] == 0 and data["r02_states"] == 998
          and tokens == d9rep)
    findings.append(_finding(
        "RACE-CONTROL", "BLOCKER", ok, data,
        "race-control temporal violation or coverage drift" if not ok
        else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §17 pit / stint temporal audit.
# ---------------------------------------------------------------------------

def check_pit_stint(paths):
    findings, data = [], {}
    pits = _concat_entity(paths, "pit_stops", list(range(2018, 2026)))
    full = int((pits["pit_in_s"].notna() & pits["pit_out_s"].notna()).sum())
    in_only = int((pits["pit_in_s"].notna() & pits["pit_out_s"].isna()).sum())
    out_only = int((pits["pit_out_s"].notna()
                    & pits["pit_in_s"].isna()).sum())
    data.update({"pit_full": full, "pit_in_only": in_only,
                 "pit_out_only": out_only})
    both = pits["pit_in_s"].notna() & pits["pit_out_s"].notna()
    data["negative_durations"] = int(
        (pits.loc[both, "pit_out_s"] - pits.loc[both, "pit_in_s"] < -1e-6)
        .sum())
    stints = _concat_entity(paths, "stints", list(range(2018, 2026)))
    overlap = 0
    bad_span = 0
    for (rid, drv), g in stints.groupby(["race_id", "driver_id"]):
        spans = sorted((int(r["start_lap"]),
                        None if pd.isna(r["end_lap"]) else int(r["end_lap"]))
                       for _, r in g.iterrows())
        for i, (s0, e0) in enumerate(spans):
            if e0 is not None and s0 > e0:
                bad_span += 1
            for s1, e1 in spans[i + 1:]:
                lo = max(s0, s1)
                hi = min(e0 if e0 is not None else 10 ** 9,
                         e1 if e1 is not None else 10 ** 9)
                if lo <= hi and not (e0 is None or e1 is None):
                    overlap += 1
    data["stint_overlaps"] = overlap
    data["stint_bad_spans"] = bad_span
    # future ends must not appear in any state table
    import pyarrow.parquet as pq

    leak_cols = []
    for entity in ("driver_lap_state_d7", "driver_lap_state_d9"):
        for s in range(2018, 2026):
            f = (paths.processed_dir / entity / f"season={s}"
                 / f"{entity}__{'d7' if entity.endswith('d7') else 'd9'}-{s}.parquet")
            names = pq.read_schema(f).names
            for c in ("end_lap", "stint_end_lap", "pit_out_lap"):
                if c in names:
                    leak_cols.append(f"{entity}/{s}/{c}")
    data["future_end_columns_in_state"] = leak_cols
    # independent spot checks on one race (2023 Bahrain, VER final lap)
    st = pd.read_parquet(
        paths.processed_dir / "driver_lap_state_d9" / "season=2023"
        / "driver_lap_state_d9__d9-2023.parquet", engine="pyarrow")
    ver = st[(st["race_id"] == "2023-r01-R")
             & (st["driver_id"] == "max_verstappen")]
    last = ver.sort_values("lap_number").iloc[-1]
    data["spot_ver_final"] = {
        "completed": int(last["pit_stops_completed_so_far"]),
        "since": (int(last["laps_since_last_pit_stop"])
                  if pd.notna(last["laps_since_last_pit_stop"]) else None),
        "stint_lap": (int(last["stint_lap"])
                      if pd.notna(last["stint_lap"]) else None),
    }
    ok = (full == 5931 and in_only == 246 and out_only == 159
          and data["negative_durations"] == 0 and overlap == 0
          and bad_span == 0 and not leak_cols
          and data["spot_ver_final"]["completed"] == 2)
    findings.append(_finding(
        "PIT-STINT", "BLOCKER", ok, data,
        "pit/stint integrity or temporal violation" if not ok else ""))
    return findings, data

# ---------------------------------------------------------------------------
# §18 D8 telemetry invariant.
# ---------------------------------------------------------------------------

def _walk_bytes(root: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return int(total)


def check_telemetry(paths, root: Path):
    findings, data = [], {}
    adr = root / "docs" / "adr" / "ADR-0001-telemetry-retention.md"
    data["adr_exists"] = adr.exists()
    data["adr_accepted"] = adr.exists() and "Accepted" in adr.read_text()
    data["contract_inactive"] = "INACTIVE" in C.TELEMETRY_SUMMARY.notes
    tel_dir = paths.processed_dir / "telemetry_summary"
    data["telemetry_summary_dir_exists"] = tel_dir.exists()
    tel_cols = [c for c in D9S.STATE_COLUMNS if "tel" in c.lower()]
    data["telemetry_columns_in_d9_state"] = tel_cols
    src = (root / "v2" / "d9.py").read_text()
    data["d9_imports_fastf1"] = ("import fastf1" in src
                                 or "from fastf1" in src)
    data["d9_reads_car_data"] = "car_data" in src
    data["cache_bytes"] = _walk_bytes(paths.cache_dir) \
        if paths.cache_dir.exists() else 0
    ok = (data["adr_exists"] and data["adr_accepted"]
          and data["contract_inactive"]
          and not data["telemetry_summary_dir_exists"]
          and not tel_cols and not data["d9_imports_fastf1"]
          and not data["d9_reads_car_data"])
    findings.append(_finding(
        "TELEMETRY", "BLOCKER", ok, data,
        "telemetry deferral violated" if not ok else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §19 D10 legacy preservation.
# ---------------------------------------------------------------------------

LEGACY_CSVS = [
    "data/processed/lap5/base/dataset_clean.csv",
    "data/processed/lap10/base/dataset_clean.csv",
    "data/processed/lap10/weather/dataset_clean.csv",
    "data/processed/lap10/snapshots/bahrain_2023.csv",
    "data/processed/lap15/base/dataset_clean.csv",
    "data/processed/lap20/base/dataset_clean.csv",
    "data/processed/lap25/base/dataset_clean.csv",
]

LEGACY_TRACKED_PATHS = ["data/processed", "data/interim", "data/sequences",
                        "data/models", "results", "ml", "api", "scripts",
                        "tests/fixtures", "frontend"]


def _git(root: Path, *args, timeout_s: int = 60):
    proc = subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                          text=True, timeout=timeout_s)
    return proc


def check_legacy(root: Path):
    findings, data = [], {}
    data["csvs_present"] = {p: (root / p).exists() for p in LEGACY_CSVS}
    pkls = sorted(str(p) for p in (root / "results" / "models").rglob(
        "*.pkl")) if (root / "results" / "models").exists() else []
    data["model_pkl_count"] = len(pkls)
    data["characterization_tests_present"] = all(
        (root / "tests" / name).exists() for name in (
            "test_known_defects.py", "test_prediction_equivalence.py",
            "test_ensemble.py", "test_datasets.py", "test_model_loading.py"))
    mods = []
    for path in LEGACY_TRACKED_PATHS:
        proc = _git(root, "status", "--porcelain", "--", path)
        if proc.stdout.strip():
            mods.append({"path": path, "status": proc.stdout.strip()})
    data["tracked_modifications"] = mods
    ok = (all(data["csvs_present"].values())
          and data["model_pkl_count"] == 30
          and data["characterization_tests_present"]
          and not mods)
    findings.append(_finding(
        "LEGACY", "BLOCKER", ok, data,
        "legacy artifact changed or missing" if not ok else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §20 manifest state audit.
# ---------------------------------------------------------------------------

def check_manifests(paths):
    from v2.manifests import Manifest, UnitStatus

    findings, data = [], {"seasons": {}}
    tb = Manifest.load(paths.manifest_path("tierb-full.json"))
    counts = tb.status_counts()
    data["tierb"] = counts
    bad = [s for s in counts if s not in ("complete",)
           and counts[s] != 0]
    findings.append(_finding(
        "MANIFESTS", "BLOCKER", not bad and counts.get("complete") == 76,
        {"tierb_counts": counts},
        "Tier-B manifest not fully terminal" if (
            bad or counts.get("complete") != 76) else ""))
    expected_races = {2018: 21, 2019: 21, 2020: 17, 2021: 22, 2022: 22,
                      2023: 22, 2024: 24, 2025: 24}
    total_c = total_p = 0
    others = []
    for season, nraces in expected_races.items():
        man = Manifest.load(paths.manifest_path(f"tiera-{season}.json"))
        st = man.status_counts()
        total_c += st.get("complete", 0)
        total_p += st.get("partial", 0)
        extra = {k: v for k, v in st.items()
                 if k not in ("complete", "partial") and v}
        if extra:
            others.append({season: extra})
        units = len(man.units)
        data["seasons"][str(season)] = {"units": units, "counts": st}
        if units != nraces:
            others.append({season: {"unit_count": units,
                                    "expected": nraces}})
    data["tiera_complete"] = total_c
    data["tiera_partial"] = total_p
    findings.append(_finding(
        "MANIFESTS", "BLOCKER",
        total_c == 171 and total_p == 2 and not others,
        {"complete": total_c, "partial": total_p, "other": others},
        "Tier-A manifest scope drifted" if (
            total_c != 171 or total_p != 2 or others) else ""))
    # provenance + status-agrees-with-artifacts on terminal units
    missing_prov = 0
    missing_files = []
    checked = 0
    for season in expected_races:
        man = Manifest.load(paths.manifest_path(f"tiera-{season}.json"))
        for uid, e in man.units.items():
            if e.status not in (UnitStatus.COMPLETE, UnitStatus.PARTIAL):
                continue
            checked += 1
            if not (e.run_id and e.schema_version == 1 and e.output_refs
                    and len(e.output_refs) == 7):
                missing_prov += 1
            for ref in (e.output_refs or []):
                if not (paths.root / ref).exists():
                    missing_files.append(ref)
    data["terminal_units_checked"] = checked
    data["units_missing_provenance"] = missing_prov
    data["missing_output_files"] = missing_files[:20]
    findings.append(_finding(
        "MANIFESTS", "BLOCKER",
        missing_prov == 0 and not missing_files,
        {"checked": checked, "missing_provenance": missing_prov,
         "missing_files": len(missing_files)},
        "provenance gaps or missing outputs" if (
            missing_prov or missing_files) else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §21 idempotency / recovery (execute the existing suites).
# ---------------------------------------------------------------------------

def check_recovery(root: Path):
    findings, data = [], {}
    res = _run_pytest(root, RECOVERY_TEST_FILES)
    data["recovery_suites"] = res
    findings.append(_finding(
        "RECOVERY", "BLOCKER", res["returncode"] == 0,
        {"files": RECOVERY_TEST_FILES, "result": res},
        "idempotency/recovery suite red" if res["returncode"] != 0 else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §22 deterministic rebuild audit (D6/D7/D9/D10 from existing sources).
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_tree(paths, specs) -> dict:
    out = {}
    for entity, seasons, unit_fn in specs:
        for season in seasons:
            f = (paths.processed_dir / entity / f"season={season}"
                 / f"{entity}__{unit_fn(int(season))}.parquet")
            out[str(f.relative_to(paths.root))] = _sha256(f)
    return out


def check_determinism(paths, root: Path):
    from v2 import d6 as d6mod
    from v2 import d7 as d7mod
    from v2 import d9 as d9mod
    from v2 import d10 as d10mod

    findings, data = [], {"stages": {}}
    scope = list(range(2018, 2026))
    specs = [("driver_lap_state", scope, D6S.d6_unit_id),
             ("race_quality", scope, D6S.d6_unit_id),
             ("driver_lap_state_d7", scope, D7S.d7_unit_id),
             ("driver_lap_state_d9", scope, D9S.state_primary_key
              and D9S.d9_unit_id),
             ("race_driver_labels", scope, D9S.d9_unit_id)]
    before = _hash_tree(paths, specs)
    t0 = time.perf_counter()
    d6mod.build_dataset(paths, write_artifacts=True)
    t6 = round(time.perf_counter() - t0, 2)
    t0 = time.perf_counter()
    d7mod.build_dataset(paths, write_artifacts=True)
    t7 = round(time.perf_counter() - t0, 2)
    t0 = time.perf_counter()
    d9mod.build_dataset(paths, write_artifacts=True)
    t9 = round(time.perf_counter() - t0, 2)
    after = _hash_tree(paths, specs)
    changed = sorted(k for k in before if before[k] != after.get(k))
    data["stages"]["d6"] = {"seconds": t6}
    data["stages"]["d7"] = {"seconds": t7}
    data["stages"]["d9"] = {"seconds": t9}
    data["changed_files"] = changed
    findings.append(_finding(
        "DETERMINISM", "BLOCKER", not changed,
        {"changed_files": changed, "stages": data["stages"]},
        f"rebuild changed {len(changed)} files" if changed else ""))
    t0 = time.perf_counter()
    rep1 = d10mod.run_audit(paths, root)
    rep2 = d10mod.run_audit(paths, root)
    data["stages"]["d10"] = {"seconds": round(time.perf_counter() - t0, 2)}

    def _strip(o):
        if isinstance(o, dict):
            return {k: _strip(v) for k, v in o.items()
                    if k != "elapsed_seconds"}
        if isinstance(o, list):
            return [_strip(v) for v in o]
        return o

    same = _strip(rep1) == _strip(rep2)
    data["d10_audit_stable"] = bool(same)
    findings.append(_finding(
        "DETERMINISM", "BLOCKER", same, {"stable": bool(same)},
        "D10 audit not reproducible" if not same else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §23 fresh-environment reproducibility.
# ---------------------------------------------------------------------------

def check_fresh_env(root: Path):
    findings, data = [], {}
    venv = Path("/tmp/d11-fresh-env")
    if venv.exists():
        import shutil as _shutil

        _shutil.rmtree(venv, ignore_errors=True)
    t0 = time.perf_counter()
    mk = subprocess.run([sys.executable, "-m", "venv", str(venv)],
                        capture_output=True, text=True, timeout=300)
    data["venv_created"] = mk.returncode == 0
    if mk.returncode != 0:
        findings.append(_finding(
            "FRESH-ENV", "MAJOR", False, {"venv_error": mk.stderr[-500:]},
            "cannot create isolated environment"))
        return findings, data
    pip = str(venv / "bin" / "pip")
    py = str(venv / "bin" / "python")
    inst = subprocess.run(
        [pip, "install", "-r", str(root / "requirements.txt"), "-r",
         str(root / "requirements-test.txt")],
        capture_output=True, text=True, timeout=1200)
    data["pip_returncode"] = inst.returncode
    data["pip_seconds"] = round(time.perf_counter() - t0, 1)
    if inst.returncode != 0:
        data["pip_tail"] = (inst.stdout + inst.stderr)[-1500:]
        findings.append(_finding(
            "FRESH-ENV", "MAJOR", False,
            {"pip_returncode": inst.returncode,
             "pip_tail": data["pip_tail"]},
            "exact requirements do not install in isolation "
            "(environment limitation, documented)"))
        return findings, data
    env = dict(os.environ, PYTHONPATH=str(root))
    imp = subprocess.run(
        [py, "-c",
         "import v2.d6, v2.d7, v2.d9, v2.d10, fastf1, pyarrow, pandas; "
         "print('imports ok')"],
        capture_output=True, text=True, timeout=300, cwd=str(root), env=env)
    data["imports_ok"] = imp.returncode == 0
    tst = subprocess.run(
        [py, "-m", "pytest", "tests/test_v2_contracts.py",
         "tests/test_v2_manifests.py", "tests/test_v2_cli.py",
         "tests/test_v2_paths.py", "tests/test_v2_retry.py",
         "tests/test_v2_storage.py", "tests/test_v2_idempotency.py", "-q"],
        capture_output=True, text=True, timeout=600, cwd=str(root), env=env)
    data["subset_returncode"] = tst.returncode
    data["subset_tail"] = (tst.stdout + tst.stderr)[-800:]
    ok = imp.returncode == 0 and tst.returncode == 0
    findings.append(_finding(
        "FRESH-ENV", "MAJOR", ok, data,
        "fresh-environment software validation failed" if not ok else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §24 CLI / developer-experience smoke.
# ---------------------------------------------------------------------------

def check_cli(root: Path):
    findings, data = [], {"commands": {}}

    def run(args, cwd=None):
        try:
            p = subprocess.run([sys.executable, "-m"] + args,
                               cwd=str(cwd or root), capture_output=True,
                               text=True, timeout=300)
            return p.returncode
        except subprocess.TimeoutExpired:
            return None

    for mod in ("v2.cli", "v2.d6", "v2.d7", "v2.d9", "v2.d10", "v2.d8"):
        data["commands"][f"{mod} --help"] = run([mod, "--help"])
    data["commands"]["v2.cli plan explicit scope"] = run(
        ["v2.cli", "--root", str(root), "plan", "--season", "2023",
         "--rounds", "1"])
    # read-only validation path on real manifests (--manifest is global)
    data["commands"]["v2.cli status tierb-full"] = run(
        ["v2.cli", "--root", str(root), "--manifest", "tierb-full.json",
         "status"])
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        data["commands"]["absent-data error"] = run(
            ["v2.cli", "--root", td, "status"])
    cmds = data["commands"]
    ok_help = all(v == 0 for k, v in cmds.items() if k.endswith("--help"))
    ok_readonly = (cmds.get("v2.cli plan explicit scope") == 0
                   and cmds.get("v2.cli status tierb-full") == 0)
    ok_err = cmds.get("absent-data error") == 2
    findings.append(_finding(
        "CLI", "MAJOR", ok_help and ok_readonly and ok_err, cmds,
        "CLI help/read-only/error behaviour broken"
        if not (ok_help and ok_readonly and ok_err) else ""))
    # validation-only commands must not import fastf1 (no network path)
    p = subprocess.run(
        [sys.executable, "-c",
         "import sys; import v2.d6, v2.d7, v2.d9, v2.d10, v2.d11; "
         "print('fastf1' in sys.modules)"],
        cwd=str(root), capture_output=True, text=True, timeout=120)
    data["fastf1_imported_by_validators"] = (p.stdout.strip() == "True")
    findings.append(_finding(
        "CLI", "BLOCKER", p.stdout.strip() == "False", data,
        "validation command pulls fastf1 (network path)" if
        p.stdout.strip() != "False" else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §25 performance sanity (uses rebuild timings + prior manifests).
# ---------------------------------------------------------------------------

def check_performance(paths, rebuild_seconds):
    findings, data = [], {}
    priors = {}
    for name in ("d6-canonical.json", "d7-canonical.json",
                 "d9-canonical.json"):
        try:
            priors[name] = float(json.loads(
                (paths.manifest_path(name)).read_text())
                ["total_build_seconds"])
        except (FileNotFoundError, KeyError, ValueError):
            priors[name] = None
    data["prior_build_seconds"] = priors
    data["rebuild_seconds"] = rebuild_seconds
    regressed = {k: v for k, v in rebuild_seconds.items()
                 if priors.get({"d6": "d6-canonical.json",
                                "d7": "d7-canonical.json",
                                "d9": "d9-canonical.json"}[k]) is not None
                 and v > 3 * priors[{"d6": "d6-canonical.json",
                                     "d7": "d7-canonical.json",
                                     "d9": "d9-canonical.json"}[k]]}
    data["regressed"] = regressed
    findings.append(_finding(
        "PERFORMANCE", "MINOR", not regressed, data,
        f"major build-time regression: {regressed}" if regressed else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §26 storage / scale audit.
# ---------------------------------------------------------------------------

def check_storage(paths):
    findings, data = [], {}
    total_files = 0
    total_bytes = 0
    per_entity = {}
    for entity in EXPECTED_PROCESSED_ENTITIES:
        base = paths.processed_dir / entity
        if not base.exists():
            continue
        files = [f for f in base.rglob("*.parquet")]
        nbytes = sum(f.stat().st_size for f in files)
        per_entity[entity] = {"files": len(files), "bytes": int(nbytes)}
        total_files += len(files)
        total_bytes += nbytes
    reports = [f for f in paths.reports_dir.rglob("*") if f.is_file()]
    data["canonical_files"] = total_files
    data["canonical_bytes"] = int(total_bytes)
    data["per_entity"] = per_entity
    data["report_files"] = len(reports)
    data["report_bytes"] = int(sum(f.stat().st_size for f in reports))
    data["cache_bytes"] = _walk_bytes(paths.cache_dir) \
        if paths.cache_dir.exists() else 0
    findings.append(_finding(
        "STORAGE", "INFORMATIONAL", True, data, ""))
    return findings, data


# ---------------------------------------------------------------------------
# §27 git / repository hygiene.
# ---------------------------------------------------------------------------

def check_git(root: Path):
    findings, data = [], {}
    parquet = _git(root, "ls-files", "*.parquet").stdout.strip()
    ff1 = _git(root, "ls-files", "*.ff1pkl").stdout.strip()
    data["tracked_parquet"] = parquet.splitlines() if parquet else []
    data["tracked_ff1pkl"] = ff1.splitlines() if ff1 else []
    ign_v2 = _git(root, "check-ignore", "-q", "data/v2")
    ign_cache = _git(root, "check-ignore", "-q", "data/raw/fastf1_cache")
    data["data_v2_ignored"] = ign_v2.returncode == 0
    data["cache_ignored"] = ign_cache.returncode == 0
    mods = {}
    for path in ["data/processed", "data/interim", "data/sequences",
                 "data/models", "results", "ml", "api", "scripts",
                 "tests/fixtures", "frontend"]:
        out = _git(root, "status", "--porcelain", "--", path).stdout.strip()
        if out:
            mods[path] = out
    data["tracked_modifications"] = mods
    nested = [str(p.parent) for p in root.rglob(".git")
              if p.is_dir() and p.parent != root]
    data["nested_repos"] = nested
    env_files = [l for l in _git(root, "ls-files").stdout.splitlines()
                 if os.path.basename(l) == ".env"]
    data["tracked_env_files"] = env_files
    ok = (not data["tracked_parquet"] and not data["tracked_ff1pkl"]
          and data["data_v2_ignored"] and data["cache_ignored"]
          and not mods and not nested and not env_files)
    findings.append(_finding(
        "GIT", "MAJOR", ok, data,
        "repository hygiene violation" if not ok else ""))
    return findings, data


# ---------------------------------------------------------------------------
# §28 full regression.
# ---------------------------------------------------------------------------

def check_regression(root: Path, skip_frontend_build=False):
    findings, data = [], {}
    t0 = time.perf_counter()
    py = _run_pytest(root, ["tests/"], timeout_s=1200)
    data["pytest"] = {"returncode": py["returncode"],
                      "elapsed_s": py["elapsed_s"],
                      "tail": py["tail"][-1500:]}
    fe = subprocess.run(
        ["node", "--test", "lib/predictionHelpers.test.ts", "lib/api.test.ts",
         "features/prediction/lib/predictionTransforms.test.ts"],
        cwd=str(root / "frontend"), capture_output=True, text=True,
        timeout=600)
    data["frontend_tests"] = {"returncode": fe.returncode,
                              "tail": (fe.stdout + fe.stderr)[-800:]}
    tsc = subprocess.run(
        [str(root / "frontend" / "node_modules" / ".bin" / "tsc"), "--noEmit",
         "-p", "."],
        cwd=str(root / "frontend"), capture_output=True, text=True,
        timeout=600)
    data["tsc"] = {"returncode": tsc.returncode,
                   "tail": (tsc.stdout + tsc.stderr)[-800:]}
    lint = subprocess.run(["npm", "run", "lint"],
                          cwd=str(root / "frontend"), capture_output=True,
                          text=True, timeout=600)
    data["lint"] = {"returncode": lint.returncode,
                    "tail": (lint.stdout + lint.stderr)[-800:]}
    if skip_frontend_build:
        data["frontend_build"] = {"skipped": True}
    else:
        bld = subprocess.run(["npm", "run", "build"],
                             cwd=str(root / "frontend"), capture_output=True,
                             text=True, timeout=1200)
        data["frontend_build"] = {
            "returncode": bld.returncode,
            "tail": (bld.stdout + bld.stderr)[-1500:]}
    data["elapsed_s"] = round(time.perf_counter() - t0, 1)
    ok = (py["returncode"] == 0 and fe.returncode == 0
          and tsc.returncode == 0 and lint.returncode == 0)
    findings.append(_finding(
        "REGRESSION", "BLOCKER", ok, data,
        "verification battery red" if not ok else ""))
    return findings, data


# ---------------------------------------------------------------------------
# Report assembly + CLI.
# ---------------------------------------------------------------------------

def write_json(dest: Path, data: dict) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def run_gate(paths: V2Paths, root: Path, skip_rebuilds=False,
             skip_tests=False, skip_fresh_env=False,
             skip_frontend_build=False) -> dict:
    t_start = time.perf_counter()
    findings, sections = [], {}

    def section(name, fn, *args):
        t0 = time.perf_counter()
        f, d = fn(*args)
        d["elapsed_s"] = round(time.perf_counter() - t0, 2)
        findings.extend(f)
        sections[name] = d
        print(f"[{name}] {'PASS' if all(x['status'] == 'pass' for x in f) else 'FAIL'} "
              f"({d['elapsed_s']}s)", flush=True)
        return f, d

    section("inventory", check_artifact_inventory, paths)
    section("contracts", check_contracts, paths)
    section("pk", check_pk, paths)
    section("fk", check_fk, paths)
    section("identity", check_identity, paths)
    section("temporal_availability", check_temporal_availability)
    section("eligibility", check_eligibility)
    section("separation", check_separation, paths)
    section("labels", check_labels, paths)
    section("missingness", check_missingness, paths)
    section("anomalies", check_anomalies, paths)
    section("partial", check_partial, paths)
    section("weather", check_weather, paths)
    section("race_control", check_race_control, paths)
    section("pit_stint", check_pit_stint, paths)
    section("telemetry", check_telemetry, paths, root)
    section("legacy", check_legacy, root)
    section("manifests", check_manifests, paths)
    if not skip_tests:
        section("mutation", check_mutation, root)
        section("recovery", check_recovery, root)
    else:
        sections["mutation"] = {"skipped": True}
        sections["recovery"] = {"skipped": True}
    if not skip_rebuilds:
        f_det, d_det = section("determinism", check_determinism, paths,
                               root)
        section("performance", check_performance, paths,
                {k: v["seconds"] for k, v in d_det["stages"].items()
                 if k in ("d6", "d7", "d9")})
    else:
        sections["determinism"] = {"skipped": True}
        sections["performance"] = {"skipped": True}
    if not skip_fresh_env:
        section("fresh_env", check_fresh_env, root)
    else:
        sections["fresh_env"] = {"skipped": True}
    section("cli", check_cli, root)
    section("storage", check_storage, paths)
    section("git", check_git, root)
    if not skip_tests:
        section("regression", check_regression, root,
                skip_frontend_build)
    else:
        sections["regression"] = {"skipped": True}

    blockers = [f for f in findings if f["blocks_phase1"]]
    report = {
        "gate": "D11 Phase-1 final validation",
        "validation_matrix": VALIDATION_MATRIX,
        "findings": findings,
        "n_findings": len(findings),
        "n_failed": sum(1 for f in findings if f["status"] == "fail"),
        "unresolved_blockers": [f["id"] for f in blockers],
        "sections": sections,
        "total_elapsed_s": round(time.perf_counter() - t_start, 1),
        "peak_rss_bytes": int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
    }
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m v2.d11",
        description="D11 Phase-1 final validation gate")
    parser.add_argument("--root", default=None)
    parser.add_argument("--json", default=None)
    parser.add_argument("--skip-rebuilds", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-fresh-env", action="store_true")
    parser.add_argument("--skip-frontend-build", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        paths = V2Paths.resolve(args.root)
        report = run_gate(
            paths, paths.root, skip_rebuilds=args.skip_rebuilds,
            skip_tests=args.skip_tests, skip_fresh_env=args.skip_fresh_env,
            skip_frontend_build=args.skip_frontend_build)
        dest = (Path(args.json) if args.json
                else paths.reports_dir / "d11_validation.json")
        write_json(dest, report)
        print(f"findings: {report['n_findings']} "
              f"failed: {report['n_failed']} "
              f"blockers: {report['unresolved_blockers']}")
        print(f"report: {paths.relative(dest)}")
        return 0 if not report["unresolved_blockers"] else 3
    except IngestionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())


