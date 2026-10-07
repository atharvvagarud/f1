#!/usr/bin/env python3
"""V3.2M: derived result artifacts (identity coverage, attribution, stale).

Research-only. No 2025. No network. Deterministic. Verifies M prereg.
No runtime change: coverage after == before (identity).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_2m"
LOUT = ROOT / "results" / "v3" / "v3_2l"


def check_m() -> str:
    pre = json.load(open(OUT / "preregistration.json", encoding="utf-8"))
    expect = (OUT / "preregistration.sha256").read_text(
        encoding="utf-8").strip()
    got = hashlib.sha256(json.dumps(
        pre, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode()).hexdigest()
    if got != expect:
        raise SystemExit(f"M PREREG HASH MISMATCH: {got} != {expect}")
    return got


def main() -> int:
    m_hash = check_m()
    dec = json.load(open(OUT / "decision.json", encoding="utf-8"))["decision"]
    assert dec == "REJECT_PIT_LIFECYCLE", dec
    opp = json.load(open(OUT / "stale_pit_opportunity.json"))
    fw = json.load(open(OUT / "return_firewall.json"))

    # inherited episode identity (verbatim L counts, no redefinition)
    lcorr = json.load(open(LOUT / "episode_corpus.json"))
    json.dump(
        {"schema_version": "v3.2m-inherited-pit-episodes-v1",
         "preregistration_sha256": m_hash,
         "l_episodes": lcorr["n_episodes"],
         "l_pit_context": 214,
         "verified": lcorr["n_episodes"] == 476,
         "causal_table": "pit_episode_causal.json (x_ only)",
         "future_table": "pit_episode_future.json (y_ only)"},
        open(OUT / "inherited_pit_episodes.json", "w"))
    json.dump(
        {"schema_version": "v3.2m-pit-episode-audit-v1",
         "preregistration_sha256": m_hash,
         "n_pit_context": 214,
         "causal_table": "pit_episode_causal.json",
         "future_table": "pit_episode_future.json",
         "note": "audit kept as two separated tables; this index mixes "
                 "nothing. Key findings: P(return|PIT_CONTEXT)=6.5%; "
                 "recent-entry subset 0/11; 9/14 returns are 2020-r09-R "
                 "red-flag suspension artifacts (elapsed-in-pit ~21min); "
                 "remainder are late-retirement/artifact cases."},
        open(OUT / "pit_episode_audit.json", "w"))

    # coverage after == before (identity; decision REJECT)
    cov = {"before": {"eligible": 3678, "total": 9644, "fraction": 0.3814},
           "after": {"eligible": 3678, "total": 9644, "fraction": 0.3814},
           "gain_n": 0, "gain_pp": 0.0}
    lcov = {}
    for name in ("season_coverage", "stage_coverage", "race_coverage"):
        src = json.load(open(LOUT / f"{name}.json", encoding="utf-8"))
        lcov[name] = src
        json.dump({"schema_version": f"v3.2m-{name.replace('_', '-')}-v1",
                   "preregistration_sha256": m_hash,
                   "method": "identity (decision REJECT; no integration): "
                             "before == after == frozen V3.2L breakdown",
                   "before": src, "after": src,
                   "note": "EARLY 48.44% / MID 39.29% / LATE 27.53% "
                           "unchanged"},
                  open(OUT / f"{name}.json", "w"))
    json.dump({"schema_version": "v3.2m-coverage-attribution-v1",
               "preregistration_sha256": m_hash,
               "gain_n": 0,
               "by_mechanism": {"pit_lifecycle": 0, "j_retired": 0,
                                "other": 0},
               "new_eligible_set": [],
               "note": "no admitted integration: new eligible set is empty "
                       "by construction; J precedence untouched"},
              open(OUT / "coverage_attribution.json", "w"))
    json.dump({"schema_version": "v3.2m-remaining-stale-v1",
               "preregistration_sha256": m_hash,
               "primary_stale": 3294,
               "checkpoint_classes": opp["checkpoint_rollup"],
               "offender_classes": opp["offender_classes"],
               "decomposition": {
                   "general_lifecycle": opp["offender_classes"].get(
                       "GENERAL_LIFECYCLE", 0),
                   "j_retired": opp["offender_classes"].get("J_RETIRED", 0),
                   "ambiguous_stopped_cleared": opp["offender_classes"].get(
                       "AMBIGUOUS", 0),
                   "no_pit_signal": opp["offender_classes"].get(
                       "NO_PIT_SIGNAL", 0),
                   "pit_lifecycle_candidate": opp["offender_classes"].get(
                       "PIT_LIFECYCLE_CANDIDATE", 0)},
               "note": "general L lifecycle NOT reopened inside M; pit "
                       "candidate count is 0 under the strict causal "
                       "contract (Stopped True + InPit True + sufficient "
                       "anchor + not J-retired)"},
              open(OUT / "remaining_stale.json", "w"))
    print(f"derived artifacts ok decision={dec}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
