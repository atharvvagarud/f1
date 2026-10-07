#!/usr/bin/env python3
"""V3.2J Parts AA-AH + AM: coverage aggregation from the recount.

Reads coverage_after.json + frozen V3.2C/V3.2F references. Writes
coverage_attribution, season/stage/race coverage, blockers_after,
signal_coverage, regime_opportunity_after, temporal_poison (corpus
stream-truncation check), reproducibility, decision inputs.
Verifies prereg hash. Deterministic. No MC runs.
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

OUT = ROOT / "results" / "v3" / "v3_2j"


def check_prereg() -> str:
    pre = json.load(open(OUT / "preregistration.json", encoding="utf-8"))
    expect = open(OUT / "preregistration.sha256", encoding="utf-8").read().strip()
    got = hashlib.sha256(json.dumps(pre, sort_keys=True).encode()).hexdigest()
    if got != expect:
        raise SystemExit(f"PREREG HASH MISMATCH: {got} != {expect}")
    return got


def main() -> int:
    check_prereg()
    from raceintel.simulation import driver_status as DS  # noqa: E402

    cov = json.load(open(OUT / "coverage_after.json", encoding="utf-8"))
    cps = cov["checkpoints"]
    before_cov = json.load(
        open(ROOT / "results" / "v3" / "v3_2c_coverage.json",
             encoding="utf-8"))
    before_by_key = {(c["race_id"], c["frame_index"]): c["verdict"]
                     for c in before_cov["checkpoints"]}
    raw = json.load(
        open(ROOT / "results" / "v3" / "v3_2f" / "coverage_opportunity_raw.json",
             encoding="utf-8"))
    raw_by_key = {(c["race_id"], c["frame_index"]): c for c in raw["checkpoints"]}

    after_elig = {(c["race_id"], c["frame_index"])
                  for c in cps if c["verdict"] == "SIMULATION_CAPABLE"}
    before_elig = {(r, f) for (r, f), v in before_by_key.items()
                   if v == "SIMULATION_CAPABLE"}
    assert before_elig <= after_elig, "J must only add eligibility"
    assert len(before_elig) == 2305, len(before_elig)
    gained = sorted(after_elig - before_elig)
    assert len(after_elig) == 3678, len(after_elig)

    # attribution: every gained checkpoint relieved by status
    relieved_keys = {(c["race_id"], c["frame_index"]) for c in cps
                     if c["status_excluded"]}
    assert set(gained) == relieved_keys, "unattributed growth"
    offenders = {}
    for c in cps:
        if (c["race_id"], c["frame_index"]) in relieved_keys:
            offenders[f"{c['race_id']}@{c['frame_index']}"] = sorted(
                c["status_excluded"])
    json.dump({"schema_version": "v3.2j-coverage-attribution-v1",
               "before": {"eligible": 2305, "total": 9644},
               "after": {"eligible": 3678, "total": 9644},
               "checkpoint_gain": len(gained),
               "percentage_point_gain": round(
                   (len(after_elig) - len(before_elig)) / 9644 * 100, 2),
               "contract": "v3.2j-driver-status-v1",
               "new_eligible_eq_resolved_stale_only": True,
               "relieved_offenders": offenders},
              open(OUT / "coverage_attribution.json", "w"),
              indent=2, sort_keys=True)

    def split(key):
        rows = [c for c in cps if key(c) is not None]
        out = {}
        groups: dict = {}
        for c in rows:
            groups.setdefault(key(c), []).append(c)
        for g, items in sorted(groups.items(), key=lambda x: str(x[0])):
            b = sum(1 for c in items
                    if before_by_key[(c["race_id"], c["frame_index"])]
                    == "SIMULATION_CAPABLE")
            a = sum(1 for c in items if c["verdict"] == "SIMULATION_CAPABLE")
            out[str(g)] = {"before": b, "after": a, "total": len(items),
                           "before_cov": round(b / len(items), 4),
                           "after_cov": round(a / len(items), 4)}
        return out

    json.dump({"schema_version": "v3.2j-season-coverage-v1",
               "by_season": split(lambda c: c["season"])},
              open(OUT / "season_coverage.json", "w"),
              indent=2, sort_keys=True)
    json.dump({"schema_version": "v3.2j-stage-coverage-v1",
               "by_stage": split(lambda c: c["stage"])},
              open(OUT / "stage_coverage.json", "w"),
              indent=2, sort_keys=True)

    races: dict = {}
    for c in cps:
        races.setdefault(c["race_id"], []).append(c)
    race_rows = []
    for rid, items in sorted(races.items()):
        b = sum(1 for c in items
                if before_by_key[(c["race_id"], c["frame_index"])]
                == "SIMULATION_CAPABLE")
        a = sum(1 for c in items if c["verdict"] == "SIMULATION_CAPABLE")
        race_rows.append({"race_id": rid, "season": items[0]["season"],
                          "before": b, "after": a, "total": len(items),
                          "after_cov": round(a / len(items), 4)})
    covs = sorted(r["after_cov"] for r in race_rows)
    json.dump({"schema_version": "v3.2j-race-coverage-v1",
               "races_with_ge1_supported": sum(1 for r in race_rows
                                               if r["after"] >= 1),
               "zero_support_races": sum(1 for r in race_rows
                                         if r["after"] == 0),
               "median_race_coverage": covs[len(covs) // 2],
               "ge50": sum(1 for r in race_rows if r["after_cov"] >= 0.5),
               "ge75": sum(1 for r in race_rows if r["after_cov"] >= 0.75),
               "ge95": sum(1 for r in race_rows if r["after_cov"] >= 0.95),
               "full": sum(1 for r in race_rows if r["after"] == r["total"]),
               "races": race_rows},
              open(OUT / "race_coverage.json", "w"),
              indent=2, sort_keys=True)

    # blockers after (primary from recount; all-blocker sets from F raw)
    primary = Counter(c["verdict"] for c in cps)
    refused = [c for c in cps if c["verdict"] != "SIMULATION_CAPABLE"]
    inter = Counter()
    for c in refused:
        key = tuple(sorted(raw_by_key[(c["race_id"], c["frame_index"])]
                           ["all_blockers"]))
        inter[key] += 1
    json.dump({"schema_version": "v3.2j-blockers-after-v1",
               "primary_after": dict(sorted(primary.items())),
               "all_blocker_sets_after": {
                   "+".join(k) if k else "NONE": v
                   for k, v in sorted(inter.items())},
               "track_only_after": inter.get(
                   ("UNSUPPORTED_TRACK_STATE",), 0),
               "wet_only_after": inter.get(("WET_CONDITIONS",), 0),
               "track_x_stale_after": inter.get(
                   ("STALE_ROSTER_OBSERVATION",
                    "UNSUPPORTED_TRACK_STATE"), 0),
               "wet_x_stale_after": inter.get(
                   ("STALE_ROSTER_OBSERVATION", "WET_CONDITIONS"), 0)},
              open(OUT / "blockers_after.json", "w"),
              indent=2, sort_keys=True)

    # regime opportunity after J (informational; H rejection frozen)
    json.dump({"schema_version": "v3.2j-regime-opportunity-after-v1",
               "track_only_after": inter.get(
                   ("UNSUPPORTED_TRACK_STATE",), 0),
               "wet_only_after": inter.get(("WET_CONDITIONS",), 0),
               "note": "informational for roadmap only; V3.2H scientific "
                       "rejection remains frozen; more opportunity does not "
                       "invalidate failed regime science"},
              open(OUT / "regime_opportunity_after.json", "w"),
              indent=2, sort_keys=True)

    # signal coverage per season (diagnostic: final-label join)
    lab = json.load(open(OUT / "label_diagnostics.json", encoding="utf-8"))
    sig: dict = {}
    for r in lab["rows"]:
        s = sig.setdefault(str(r["season"]), {
            "drivers_with_retired_true": 0, "tp": 0, "fp": 0})
        s["drivers_with_retired_true"] += 1
        if r["n_true"] and r["official_dnf"]:
            s["tp"] += 1
        if r["n_true"] and not r["official_dnf"]:
            s["fp"] += 1
    import pandas as pd  # noqa: E402
    for season in ("2018", "2019", "2020", "2021", "2022", "2023", "2024"):
        df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "results" /
            f"season={season}",
            columns=["race_id", "driver_id", "dnf_flag"])
        s = sig.setdefault(season, {"drivers_with_retired_true": 0,
                                    "tp": 0, "fp": 0})
        s["official_dnf_count"] = int(df["dnf_flag"].sum())
        s["missed_dnf"] = s["official_dnf_count"] - s["tp"]
    cl = json.load(open(OUT / "retired_clearings.json", encoding="utf-8"))
    for season in sig:
        sig[season]["clearings"] = sum(
            1 for c in cl["clearings"] if str(c["season"]) == season)
    json.dump({"schema_version": "v3.2j-signal-coverage-v1",
               "note": "final-label diagnostic join; 'recall-like' only, "
                       "never a runtime input",
               "by_season": dict(sorted(sig.items()))},
              open(OUT / "signal_coverage.json", "w"),
              indent=2, sort_keys=True)

    # temporal poison on real streams: status(T) computed from the
    # full stream must equal status(T) from the stream truncated to
    # rows <= T (prefix-closed reconstruction => future rows cannot
    # influence the past). Checked on sampled relieved checkpoints.
    seqs = json.load(open(OUT / "retired_transitions.json",
                          encoding="utf-8"))["sequences"]
    poison_rows = []
    for c in sorted(relieved_keys)[:5]:
        rid, fi = c
        rec = next(x for x in cps
                   if x["race_id"] == rid and x["frame_index"] == fi)
        import pandas as pd  # noqa: E402
        from raceintel.replay import replay as RP  # noqa: E402
        df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9" /
            f"season={rec['season']}/driver_lap_state_d9__d9-{rec['season']}.parquet")
        tl = RP.build_replay_timeline(df[df["race_id"] == rid].copy())
        T = float(tl.frame_at(fi).anchor_state_time_s)
        for did in sorted(rec["status_excluded"]):
            full = [(t, v) for t, v in seqs.get(rid, {}).get(did, [])]
            trunc = [(t, v) for t, v in full if t <= T]
            assert DS.retired_known_at(full, T) is True
            assert DS.retired_known_at(trunc, T) is True
            poison_rows.append({"race_id": rid, "frame_index": fi,
                                "driver": did, "T": T,
                                "full_eq_truncated": True})
    json.dump({"schema_version": "v3.2j-temporal-poison-v1",
               "rule": "removing all raw rows after T leaves status(T) "
                       "unchanged (prefix-closed reconstruction)",
               "n_checks": len(poison_rows),
               "rows": poison_rows},
              open(OUT / "temporal_poison.json", "w"),
              indent=2, sort_keys=True)
    print(f"gain={len(gained)} after={len(after_elig)} "
          f"primary_STALE={primary.get('STALE_ROSTER_OBSERVATION')} "
          f"poison_checks={len(poison_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
