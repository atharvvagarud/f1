#!/usr/bin/env python3
"""V3.2F offline regime pace evidence (Parts G/H/I/J/L, parquet-only).

Read-only scan of the D9 driver_lap_state parquets (2018-2024). No
RaceState reconstruction, no simulation, no truth join beyond lap times
already in the frame. All comparisons are within-(circuit, compound,
era) so eras/regulations do not confound regime deltas.

Outputs (JSON):
- green reference medians per (circuit_id, compound),
- lap-time delta distributions per track_state token (dry compounds,
  lap>1, no pit in/out),
- per-yellow-lap affected-driver fractions (driver delta vs own green
  median: is the field slowed or a subset?),
- SC restart laps (first 2 green laps after an SC episode) vs green,
- VSC duration distribution (episodes in laps),
- wet-lap dataset counts by era x compound x rainfall,
- yellow RC message semantics (category/flag/sector-mention/age).

No simulator source, parameter, artifact, or replay cache is modified.
No model training. Output carries no timestamps, usernames, or paths.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "results" / "v3" / "v3_2f"
SEASONS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)
DRY = ("SOFT", "MEDIUM", "HARD", "SUPERSOFT", "ULTRASOFT", "HYPERSOFT")


def _q(sorted_vals: list, q: float):
    if not sorted_vals:
        return None
    k = min(len(sorted_vals) - 1, max(0, int(q * len(sorted_vals))))
    return sorted_vals[k]


def _summarize(vals: list) -> dict:
    vals = sorted(vals)
    n = len(vals)
    if n == 0:
        return {"n": 0}
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / n
    return {"n": n, "mean": round(mean, 3),
            "p10": round(_q(vals, 0.10), 3), "p50": round(_q(vals, 0.50), 3),
            "p90": round(_q(vals, 0.90), 3),
            "sd": round(var ** 0.5, 3)}


def main() -> int:
    import pandas as pd

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for season in SEASONS:
        p = (ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9" /
             f"season={season}" /
             f"driver_lap_state_d9__d9-{season}.parquet")
        df = pd.read_parquet(p)
        frames.append(df)
    d9 = pd.concat(frames, ignore_index=True)

    usable = d9[
        d9["lap_time_s"].notna() & (d9["lap_number"] > 1)
        & d9["pit_in_s"].isna() & d9["pit_out_s"].isna()
    ].copy()

    # Green references per (circuit_id, compound), dry only.
    green = usable[(usable["track_state"] == "all_clear")
                   & usable["compound"].isin(DRY)
                   & (usable["wx_rainfall"] != True)]  # noqa: E712
    ref = green.groupby(["circuit_id", "compound"])["lap_time_s"].median()
    ref_dict = {(c, k): float(v) for (c, k), v in ref.items()}

    # Regime deltas vs same-circuit-compound green median (dry only).
    by_regime: dict[str, list] = {}
    for tok, g in usable[usable["compound"].isin(DRY)].groupby("track_state"):
        deltas = []
        for row in g.itertuples():
            r = ref_dict.get((row.circuit_id, row.compound))
            if r is not None and pd.notna(row.lap_time_s):
                deltas.append(float(row.lap_time_s) - r)
        by_regime[str(tok)] = _summarize(deltas)

    # Per-yellow-lap affected fractions (driver vs OWN green median).
    own_green = green.groupby(
        ["race_id", "driver_id", "compound"])["lap_time_s"].median()
    own_dict = {(r, d, c): float(v)
                for (r, d, c), v in own_green.items()}
    ylaps = usable[(usable["track_state"] == "yellow")
                   & usable["compound"].isin(DRY)]
    lap_fracs, lap_n = [], []
    for (race, lap), g in ylaps.groupby(["race_id", "lap_number"]):
        slowed, total = 0, 0
        for row in g.itertuples():
            b = own_dict.get((race, row.driver_id, row.compound))
            if b is None or not pd.notna(row.lap_time_s):
                continue
            total += 1
            if float(row.lap_time_s) - b > 2.0:
                slowed += 1
        if total >= 5:
            lap_fracs.append(slowed / total)
            lap_n.append(total)
    yellow_affected = {
        "n_yellow_laps": len(lap_fracs),
        "frac_slowed": _summarize(lap_fracs),
        "drivers_per_lap": _summarize(lap_n),
    }

    # SC restart: first 2 all_clear laps after a safety_car episode.
    restart_deltas = []
    for race, g in usable.sort_values(
            ["race_id", "lap_number"]).groupby("race_id"):
        toks = g[["lap_number", "track_state"]].drop_duplicates(
            "lap_number").sort_values("lap_number")
        seq = list(toks.itertuples(index=False))
        for i, r in enumerate(seq):
            if r.track_state == "safety_car":
                j = i
                while j + 1 < len(seq) and seq[j + 1].track_state \
                        == "safety_car":
                    j += 1
                for k in (j + 1, j + 2):
                    if k < len(seq) and seq[k].track_state == "all_clear":
                        lap = seq[k].lap_number
                        rows = g[(g["lap_number"] == lap)
                                 & g["compound"].isin(DRY)]
                        for row in rows.itertuples():
                            refv = ref_dict.get(
                                (row.circuit_id, row.compound))
                            if refv is not None and pd.notna(
                                    row.lap_time_s):
                                restart_deltas.append(
                                    float(row.lap_time_s) - refv)
                break
    sc_restart = {"n_laps_rows": len(restart_deltas),
                  "delta": _summarize(restart_deltas)}

    # VSC / SC episode durations in laps (offline, from frame tokens).
    durations: dict[str, list] = {}
    for race, g in usable.groupby("race_id"):
        toks = (g[["lap_number", "track_state"]]
                .drop_duplicates("lap_number").sort_values("lap_number"))
        cur, run = None, 0
        for r in toks.itertuples(index=False):
            if r.track_state == cur:
                run += 1
            else:
                if cur in ("vsc", "safety_car", "yellow", "red_flag",
                           "vsc_ending"):
                    durations.setdefault(cur, []).append(run)
                cur, run = r.track_state, 1
        if cur in ("vsc", "safety_car", "yellow", "red_flag",
                   "vsc_ending"):
            durations.setdefault(cur, []).append(run)
    episode_durations = {k: _summarize(v)
                         for k, v in sorted(durations.items())}

    # Wet dataset counts (Part L): usable laps by era x compound x rain.
    def _era(s: int) -> str:
        return "2018-2021" if s <= 2021 else "2022-2024"

    wet = usable[usable["compound"].isin(("INTERMEDIATE", "WET"))
                 | (usable["wx_rainfall"] == True)].copy()  # noqa: E712
    wet["era"] = wet["season"].map(_era)
    wet_counts = (wet.groupby(["era", "compound", "wx_rainfall"])
                  .size().to_dict())
    wet_counts = {f"{e}|{c}|rain={bool(r)}": int(n)
                  for (e, c, r), n in sorted(
                      wet_counts.items(), key=lambda kv: str(kv[0]))}
    # Dry compounds under rainfall (slicks-in-rain shape).
    slicks_rain = usable[usable["compound"].isin(DRY)
                         & (usable["wx_rainfall"] == True)]  # noqa: E712
    slicks_counts = (slicks_rain.groupby(["season", "compound"])
                     .size().to_dict())
    slicks_counts = {f"{s}|{c}": int(n)
                     for (s, c), n in sorted(
                         slicks_counts.items(), key=lambda kv: str(kv[0]))}

    # Yellow RC semantics (Part G).
    yrows = d9[d9["track_state"] == "yellow"]
    rc_cat = yrows["rc_last_message_category"].value_counts(
        dropna=False).to_dict()
    rc_flag = yrows["rc_last_message_flag"].value_counts(
        dropna=False).to_dict()
    texts = yrows["rc_last_message_text"].dropna()
    sector_hit = int(texts.str.contains(
        "SECTOR", case=False, na=False).sum())
    yellow_rc = {
        "n_yellow_rows": int(len(yrows)),
        "rc_category": {str(k): int(v) for k, v in rc_cat.items()},
        "rc_flag": {str(k): int(v) for k, v in rc_flag.items()},
        "n_texts": int(texts.notna().sum()),
        "sector_mention_rows": sector_hit,
        "rc_age_s": _summarize(
            [float(v) for v in
             yrows["rc_last_message_age_s"].dropna().tolist()]),
    }

    doc = {
        "schema_version": "v3.2f-pace-evidence-raw-v1",
        "seasons": list(SEASONS),
        "n_frame_rows": int(len(d9)),
        "n_usable_lap_rows": int(len(usable)),
        "green_reference_cells": len(ref_dict),
        "regime_delta_s": by_regime,
        "yellow_affected": yellow_affected,
        "sc_restart": sc_restart,
        "episode_durations_laps": episode_durations,
        "wet_counts_era_compound_rain": wet_counts,
        "slicks_under_rain_counts": slicks_counts,
        "yellow_rc": yellow_rc,
    }
    (OUT_DIR / "pace_evidence_raw.json").write_text(
        json.dumps(doc, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "OK",
        "regimes": {k: v.get("n") for k, v in by_regime.items()},
        "yellow_laps": len(lap_fracs),
        "wet_cells": len(wet_counts)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
