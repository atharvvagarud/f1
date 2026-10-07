#!/usr/bin/env python3
"""V3.2N Parts V/W/X: API contract + replay sync + failure modes.

Small simulation counts (behavioral, not scientific). No 2025.
No network (TestClient in-process). Deterministic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "v3" / "v3_2n"


def anchors() -> dict:
    out = {}
    for path in sorted((ROOT / "results" / "v2_replay" / "checkpoints").glob(
            "*.json")):
        d = json.load(open(path, encoding="utf-8"))
        for entry in d["checkpoints"]:
            cp = entry["checkpoint"]
            out[(cp["race_id"], cp["frame_index"])] = cp
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cat = json.load(open(OUT / "final_eligibility_catalogue.json",
                         encoding="utf-8"))
    cps = cat["checkpoints"]
    by_key = {(c["race_id"], c["frame_index"]): c for c in cps}
    anch = anchors()

    from fastapi.testclient import TestClient
    from api.main import app
    from api.v2_service import load_v2_service
    from api.v2_simulation_service import (
        build_v2_simulation_service,
        get_v2_simulation_service,
    )
    from raceintel.simulation.driver_status import (  # noqa: E402
        load_status_corpus,
        load_unreliable_windows,
    )
    resolver = load_status_corpus(ROOT / "results" / "v3" / "v3_2j" / "status")
    windows = load_unreliable_windows(
        ROOT / "results" / "v3" / "v3_2j" / "unreliable_windows.json")
    svc = build_v2_simulation_service(
        load_v2_service(), status_resolver=resolver, status_windows=windows)
    app.dependency_overrides[get_v2_simulation_service] = lambda: svc
    client = TestClient(app)

    def call(race_id, frame_index, count=10):
        a = anch[(race_id, frame_index)]
        return client.post("/v2/simulations/race", json={
            "race_id": race_id, "anchor_driver_id": a["anchor_driver_id"],
            "anchor_lap_number": a["anchor_lap_number"],
            "anchor_state_time_s": a["anchor_state_time_s"],
            "simulation_count": count}), a

    elig_pre = next(c for c in cps
                    if c["verdict"] == "SIMULATION_CAPABLE"
                    and not c["status_excluded"])
    elig_rel = next(c for c in cps
                    if c["verdict"] == "SIMULATION_CAPABLE"
                    and c["status_excluded"])

    api_rows = []
    for label, c in [("eligible-pre-J", elig_pre),
                      ("eligible-J-relieved", elig_rel)]:
        r, a = call(c["race_id"], c["frame_index"])
        body = r.json()
        api_rows.append({
            "case": label,
            "race_id": c["race_id"], "frame_index": c["frame_index"],
            "http": r.status_code,
            "ok": r.status_code == 200,
            "valid": body.get("valid_simulations"),
            "requested": body.get("requested_simulation_count"),
            "state_time_match": body.get("anchor_state_time_s")
            == a["anchor_state_time_s"],
        })
    json.dump({"schema_version": "v3.2n-api-contract-v1",
               "rows": api_rows,
               "all_ok": all(r["ok"] and r["valid"] == r["requested"]
                             and r["state_time_match"] for r in api_rows),
               "notes": ["eligible + J-relieved return success",
                         "no request-time network/raw-parse/future access "
                         "(service loads pinned artifacts at startup)"]},
              open(OUT / "api_contract.json", "w"), indent=1)

    # ---- W: replay sync on the same two states ----
    from raceintel.race_state.race_state_reconstruction import (  # noqa: E402
        RaceStateReconstructor,
    )
    from raceintel.replay import replay as RP  # noqa: E402
    from raceintel.replay.replay_reconstruction import (  # noqa: E402
        ReplayReconstructor,
    )
    import pandas as pd  # noqa: E402
    sync_rows = []
    for c in (elig_pre, elig_rel):
        rid, fi = c["race_id"], c["frame_index"]
        season = int(rid.split("-")[0])
        base = ROOT / "data" / "v2" / "processed"
        states = pd.read_parquet(
            base / "driver_lap_state_d9" / f"season={season}" /
            f"driver_lap_state_d9__d9-{season}.parquet")
        states = states[states["race_id"] == rid].copy()
        results = pd.read_parquet(
            base / "results" / f"season={season}" / f"results__{rid}.parquet")
        tl = RP.build_replay_timeline(states)
        frame = tl.frame_at(fi)
        svc2 = ReplayReconstructor(
            tl, RaceStateReconstructor(states, results, race_meta=None))
        rs = svc2.state_at(fi)
        a = anch[(rid, fi)]
        sync_rows.append({
            "race_id": rid, "frame_index": fi,
            "replay_anchor_time": float(frame.anchor_state_time_s),
            "request_anchor_time": a["anchor_state_time_s"],
            "race_state_time": float(rs.state_time_s),
            "catalogue_match": (c["race_id"], c["frame_index"]) == (rid, fi),
            "in_sync": abs(float(frame.anchor_state_time_s)
                           - a["anchor_state_time_s"]) < 1e-9
            and abs(float(rs.state_time_s)
                    - a["anchor_state_time_s"]) < 1e-6,
        })
    json.dump({"schema_version": "v3.2n-replay-integration-v1",
               "rows": sync_rows,
               "in_sync": all(r["in_sync"] for r in sync_rows)},
              open(OUT / "replay_integration.json", "w"), indent=1)

    # ---- X: failure modes, one representative per blocker ----
    want = {"STALE_ROSTER_OBSERVATION": None,
            "UNSUPPORTED_TRACK_STATE": None, "WET_CONDITIONS": None,
            "MISSING_DRIVER_OBSERVATION": None, "MISSING_TYRE_STATE": None,
            "TERMINAL_STATE": None}
    for c in cps:
        if c["verdict"] in want and want[c["verdict"]] is None:
            want[c["verdict"]] = c
    fail_rows = []
    for verdict, c in want.items():
        if c is None:
            fail_rows.append({"blocker": verdict, "representative": None,
                              "note": "no representative in catalogue"})
            continue
        r, _ = call(c["race_id"], c["frame_index"])
        body = r.json() if r.status_code != 200 else {}
        fail_rows.append({
            "blocker": verdict, "race_id": c["race_id"],
            "frame_index": c["frame_index"], "http": r.status_code,
            "explicit_refusal": r.status_code == 422 and body.get(
                "error") == "simulation_unsupported",
            "reason": (body.get("reason") or body.get("detail")
                       or c["reason"])[:160],
        })
    json.dump({"schema_version": "v3.2n-failure-mode-audit-v1",
               "rows": fail_rows,
               "all_explicit": all(r.get("explicit_refusal")
                                   for r in fail_rows if r.get(
                                       "representative") is not False
                                   and r.get("race_id"))},
              open(OUT / "failure_mode_audit.json", "w"), indent=1)
    print("api=" + str([ (r['case'], r['http']) for r in api_rows]),
          flush=True)
    print("sync=" + str([r["in_sync"] for r in sync_rows]), flush=True)
    print("fail=" + str([(r["blocker"], r.get("http")) for r in fail_rows]),
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
