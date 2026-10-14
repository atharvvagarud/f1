"""V3.10F telemetry source audit (read-only, offline).

Audits the frozen D9 corpus (driver_lap_state_d9, stints, pit_stops) that
backs the served replay, establishing for every candidate telemetry field:
source, availability class, temporal semantics, missingness, and whether the
current replay payload already carries it.

Output: results/v3/v3_10f/telemetry_source_audit.json
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results" / "v3" / "v3_10f" / "telemetry_source_audit.json"
SEASONS = list(range(2018, 2025))

D9_COLS = [
    "race_id", "driver_id", "lap_number", "state_time_s", "lap_start_s",
    "lap_time_s", "sector_1_s", "sector_2_s", "sector_3_s",
    "sector_1_end_s", "sector_2_end_s", "sector_3_end_s",
    "compound", "tyre_life", "stint_number", "fresh_tyre",
    "pit_in_s", "pit_out_s", "track_status", "deleted", "deleted_reason",
    "is_accurate", "fastf1_generated", "position", "stint_lap",
    "race_leader_laps_at_state",
]


def load(entity: str) -> pd.DataFrame:
    frames = []
    for season in SEASONS:
        pattern = str(REPO / "data" / "v2" / "processed" / entity
                       / f"season={season}" / "*.parquet")
        for path in sorted(glob.glob(pattern)):
            df = pd.read_parquet(path)
            frames.append(df)
    return pd.concat(frames, ignore_index=True)


def pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 2) if d else 0.0


def main() -> None:
    d9 = load("driver_lap_state_d9")
    st = load("stints")
    ps = load("pit_stops")
    d9 = d9[d9["season"].isin(SEASONS)].copy()

    races = sorted(d9["race_id"].unique())
    n_rows = len(d9)
    n_drivers = int(d9[["race_id", "driver_id"]].drop_duplicates()
                    .shape[0])

    def cov(col: str) -> dict:
        present = int(d9[col].notna().sum())
        return {"present": present, "total": n_rows,
                "coverage_pct": pct(present, n_rows),
                "missing": n_rows - present,
                "missing_pct": pct(n_rows - present, n_rows)}

    fields = {c: cov(c) for c in D9_COLS if c in d9.columns}

    # Lap-time present but sectors missing (and vice versa).
    has_lap = d9["lap_time_s"].notna()
    sec_any = d9[["sector_1_s", "sector_2_s",
                  "sector_3_s"]].notna().any(axis=1)
    sec_all = d9[["sector_1_s", "sector_2_s",
                  "sector_3_s"]].notna().all(axis=1)
    lap_no_sector = int((has_lap & ~sec_any).sum())
    sector_no_lap = int((~has_lap & sec_any).sum())
    full_lap = int((has_lap & sec_all).sum())

    # Observation-boundary skew: state_time_s vs sector_3_end_s.
    both = d9[d9["state_time_s"].notna()
              & d9["sector_3_end_s"].notna()].copy()
    skew = (both["state_time_s"] - both["sector_3_end_s"])
    skew_stats = {
        "n": int(len(both)),
        "min_s": round(float(skew.min()), 3),
        "p50_s": round(float(skew.median()), 3),
        "p99_s": round(float(skew.quantile(0.99)), 3),
        "max_s": round(float(skew.max()), 3),
        "state_before_sector_end_frac_pct": pct(int((skew < 0).sum()),
                                                len(both)),
    }
    # state_time_s ordering within driver == lap_number ordering?
    ordered = d9.sort_values(["race_id", "driver_id", "lap_number"])
    mono = bool((ordered.groupby(["race_id", "driver_id"])["state_time_s"]
                 .apply(lambda s: bool((s.diff().dropna() > 0).all()))).all())

    # Lap 1 sector-1 missingness (standing-start quirk).
    lap1 = d9[d9["lap_number"] == 1]
    lap1_s1_missing_pct = pct(int(lap1["sector_1_s"].isna().sum()),
                              len(lap1))

    # Validity / quality flags.
    deleted_n = int(d9["deleted"].fillna(False).astype(bool).sum())
    generated_n = int(d9["fastf1_generated"].fillna(False).astype(bool).sum())
    accurate_n = int(d9["is_accurate"].fillna(False).astype(bool).sum())
    pit_laps = int((d9["pit_in_s"].notna()
                    | d9["pit_out_s"].notna()).sum())

    # Tyre-life quirk: lap-1 tyre_life > 1 (laps in other sessions).
    lap1_tl = lap1[lap1["tyre_life"].notna()]["tyre_life"]
    tl_quirk_pct = pct(int((lap1_tl > 1).sum()), len(lap1_tl))

    # Compound / stint coverage.
    compound_values = sorted(str(v) for v in
                             d9["compound"].dropna().unique())

    # Stints entity shape.
    st_race_n = int(st["race_id"].nunique())
    st_open = int(st["end_lap"].isna().sum())
    st_rows = len(st)

    # Replay payload check: DriverRaceState fields (frontend/lib/v2.ts).
    replay_carried = ["observed_lap_number", "observed_time_s", "compound",
                      "tyre_life", "fresh_tyre", "stint_number", "stint_lap",
                      "pit_stops_completed_so_far", "position"]
    replay_missing = ["lap_time_s", "sector_1_s", "sector_2_s", "sector_3_s",
                      "sector_1_end_s", "sector_2_end_s", "sector_3_end_s",
                      "lap_start_s", "pit_in_s", "pit_out_s", "deleted",
                      "is_accurate", "fastf1_generated", "state_time_s"]

    audit = {
        "scope": {
            "seasons": SEASONS,
            "races_audited": len(races),
            "driver_race_entries": n_drivers,
            "lap_rows": n_rows,
            "stint_rows": st_rows,
            "stint_races": st_race_n,
            "pit_stop_rows": len(ps),
        },
        "field_coverage": fields,
        "lap_sector_joint": {
            "completed_lap_with_all_sectors": full_lap,
            "completed_lap_no_sector": lap_no_sector,
            "sectors_but_no_lap_time": sector_no_lap,
        },
        "observation_boundary": {
            "rule": "lap (driver, lap_number) becomes observable when its "
                    "D9 row state_time_s <= replay T (anchor_state_time_s). "
                    "Replay frames ARE the unique state_time_s grid, so the "
                    "lap row's own state_time_s is a frame anchor time.",
            "state_time_monotonic_per_driver": mono,
            "state_minus_sector3end_skew_s": skew_stats,
            "sector_ends_available_but_unused": {
                "sector_1_end_s": fields.get("sector_1_end_s"),
                "sector_2_end_s": fields.get("sector_2_end_s"),
                "sector_3_end_s": fields.get("sector_3_end_s"),
            },
            "partial_sector_policy": "V3.10F uses completed-lap (LAP_END) "
                                     "evidence only; IN_LAP sector-end "
                                     "timestamps are audited but not exposed.",
        },
        "validity": {
            "deleted_laps": deleted_n,
            "deleted_pct": pct(deleted_n, n_rows),
            "deleted_availability": "POST_RACE (stewards decision) — MUST "
                                    "NOT filter the causal reference; "
                                    "documented as limitation.",
            "is_accurate_true_pct": pct(accurate_n, n_rows),
            "is_accurate_availability": "POST_RACE flag, not a filter — "
                                        "informational only.",
            "fastf1_generated": generated_n,
            "fastf1_generated_pct": pct(generated_n, n_rows),
            "fastf1_generated_availability": "SOURCE_METADATA (known with "
                                             "the source row, not a future "
                                             "outcome) — safe to exclude "
                                             "from reference + mark.",
            "pit_laps": pit_laps,
            "pit_lap_pct": pct(pit_laps, n_rows),
            "pit_lap_policy": "IN_LAP evidence (pit_in_s/pit_out_s), "
                              "causally known; NOT excluded from history, "
                              "NOT excluded from best-so-far reference "
                              "(a pit lap can never be the minimum); "
                              "displayed factually.",
            "sc_vsc_policy": "track_status is IN_LAP and causally known; "
                             "SC/VSC-affected laps are NOT excluded "
                             "(limitation documented — deltas stay "
                             "descriptive).",
            "lap1_sector1_missing_pct": lap1_s1_missing_pct,
        },
        "tyre_semantics": {
            "compound_values": compound_values,
            "tyre_life_lap1_gt1_pct": tl_quirk_pct,
            "tyre_life_note": "source TyreLife INCLUDES laps in other "
                              "sessions (contract quirk) — raw tyre_life "
                              "must NOT be relabelled as laps-on-set. "
                              "V3.10F uses STINT AGE (stint_lap / "
                              "observed_lap - start_lap + 1).",
            "stint_open_end_lap_nulls": st_open,
        },
        "replay_payload": {
            "already_carried": replay_carried,
            "not_carried": replay_missing,
            "new_readout_required": True,
            "new_endpoint_justification": "lap_time_s and sector_*_s are "
                "absent from every served replay payload "
                "(DriverRaceState has no lap/sector slots; verified in "
                "api/v2_schemas.py + frontend/lib/v2.ts). Deriving lap "
                "times from frame-to-frame observed_time deltas would be "
                "estimation, forbidden by V3.10F S5. One race-scoped "
                "read-only endpoint over the same frozen D9 corpus is "
                "required; the causal selector enforces <=T client-side.",
        },
        "per_field": {
            "lap_number": {"source": "driver_lap_state_d9.lap_number",
                           "availability": "LAP_START",
                           "becomes_known": "when the lap begins",
                           "in_replay_payload": False},
            "lap_time_s": {"source": "driver_lap_state_d9.lap_time_s",
                            "availability": "LAP_END",
                            "becomes_known": "at lap completion "
                                             "(state_time_s of the lap row)",
                            "in_replay_payload": False},
            "sector_1_s": {"source": "driver_lap_state_d9.sector_1_s",
                            "availability": "LAP_END (conservative V3.10F "
                                            "rule; source also has IN_LAP "
                                            "sector_1_end_s)",
                            "becomes_known": "with the completed lap",
                            "in_replay_payload": False},
            "sector_2_s": {"source": "driver_lap_state_d9.sector_2_s",
                            "availability": "LAP_END (conservative)",
                            "becomes_known": "with the completed lap",
                            "in_replay_payload": False},
            "sector_3_s": {"source": "driver_lap_state_d9.sector_3_s",
                            "availability": "LAP_END (conservative)",
                            "becomes_known": "with the completed lap",
                            "in_replay_payload": False},
            "compound": {"source": "driver_lap_state_d9.compound + "
                                   "stints.compound",
                         "availability": "IN_LAP",
                         "becomes_known": "during the lap / at stint start; "
                                          "current compound always from the "
                                          "causal frame state, never "
                                          "backfilled",
                         "in_replay_payload": True},
            "tyre_life": {"source": "driver_lap_state_d9.tyre_life",
                          "availability": "IN_LAP",
                          "semantics": "FastF1 TyreLife incl. other "
                                       "sessions — NOT laps-on-set",
                          "in_replay_payload": True},
            "stint_number": {"source": "driver_lap_state_d9.stint_number + "
                                       "stints.stint_number",
                             "availability": "IN_LAP",
                             "in_replay_payload": True},
            "pit_in_s/pit_out_s": {"source": "driver_lap_state_d9 + "
                                             "pit_stops entity",
                                   "availability": "IN_LAP",
                                   "in_replay_payload": False},
            "pit_stops_completed_so_far": {"source": "D9 derived",
                                           "availability": "IN_LAP",
                                           "in_replay_payload": True},
            "completed_lap_status": {"source": "row presence in D9 "
                                               "(one row per recorded lap)",
                                     "availability": "LAP_END",
                                     "in_replay_payload": False},
            "observation_boundary": {"source": "driver_lap_state_d9."
                                               "state_time_s",
                                     "availability": "LAP_END grid == "
                                                    "replay frame grid",
                                     "in_replay_payload": False},
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, indent=2) + "\n")
    print(f"wrote {OUT}")
    print(f"races={len(races)} rows={n_rows} "
          f"lap_cov={fields['lap_time_s']['coverage_pct']}% "
          f"s1={fields['sector_1_s']['coverage_pct']}% "
          f"s2={fields['sector_2_s']['coverage_pct']}% "
          f"s3={fields['sector_3_s']['coverage_pct']}% "
          f"compound={fields['compound']['coverage_pct']}% "
          f"stint={fields['stint_number']['coverage_pct']}%")


if __name__ == "__main__":
    main()
