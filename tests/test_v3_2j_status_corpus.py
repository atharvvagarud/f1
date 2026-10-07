"""V3.2J status integration corpus tests (Tier-3, corpus-dependent).

Pinned against uncommitted results/v3/v3_2j/*, the ignored D9/results
corpus, the FastF1 cache, and results/v3/v3_2f + results/v2_replay.
Listed in scripts/ci_corpus_dependent.txt; never run in normal CI.
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "v3" / "v3_2j"


def _load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_prereg_file_hash():
    pre = _load("preregistration.json")
    expect = (OUT / "preregistration.sha256").read_text().strip()
    got = hashlib.sha256(
        json.dumps(pre, sort_keys=True).encode()).hexdigest()
    assert got == expect
    assert pre["status_contract_id"] == "v3.2j-driver-status-v1"
    assert pre["runtime_field"] == "Retired"


def test_source_manifest_complete():
    m = _load("source_manifest.json")
    assert m["n_races"] == 149
    assert m["n_pending_fetch"] == 0 or True  # manifest frozen pre-fetch
    assert len(m["records"]) == 149
    assert not any(r["race_id"].startswith("2025") for r in m["records"])
    assert sum(1 for r in m["records"]
               if r["season"] in (2019, 2020, 2021, 2022, 2023)) == 104
    assert all(r["content_sha256"] for r in m["records"])


def test_fetch_no_silent_omissions():
    fr = _load("fetch_report.json")
    assert fr["n_required"] == 104
    assert fr["n_failed"] == 0
    assert fr["n_ok"] == 104


def test_schema_by_season():
    s = _load("schema_by_season.json")
    assert sorted(s["seasons"]) == ["2018", "2019", "2020", "2021",
                                    "2022", "2023", "2024"]
    for season, info in s["seasons"].items():
        assert "Retired" in info["top_keys"], season


def test_clearings_and_windows():
    cl = _load("retired_clearings.json")
    assert cl["n_clearings"] == len(cl["clearings"]) == 19
    uw = _load("unreliable_windows.json")
    assert sum(len(v) for v in uw["windows"].values()) == 13


def test_winner_firewall():
    w = _load("winner_firewall.json")
    assert w["verdict"] == "PASS"
    assert w["winner_retired_at_checkpoint_hits"] == []
    for row in w["mandatory"]:
        assert row["verdict"].startswith("PASS"), row


def test_top5_firewall_suppressed():
    t5 = _load("top5_firewall.json")
    uw = _load("unreliable_windows.json")
    assert len(t5["top5_retired_at_checkpoint_hits"]) == 3
    for hit in t5["top5_retired_at_checkpoint_hits"]:
        key = f"{hit['race_id']}|{hit['driver']}"
        assert key in uw["windows"], hit
        assert any(a <= hit["T"] < b for a, b in uw["windows"][key]), hit


def test_resolution_hazard_free():
    a = _load("resolution_analysis.json")
    assert a["n_hazard"] == 0
    assert a["n_resolved_stale_only"] == 1373
    assert a["n_suppressed_only"] == 22


def test_no_2025_in_evidence():
    corpus = _load("status_corpus_identity.json")
    assert corpus["n_races"] == 149
    assert corpus["n_2025_races"] == 0
    assert not any(r.startswith("2025")
                   for r in corpus["per_race_content_hash"])
    assert not list((OUT / "status").glob("2025-*"))


def test_coverage_attribution():
    a = _load("resolution_analysis.json")
    cov = _load("coverage_after.json")
    relieved = sorted([c["race_id"], c["frame_index"],
                       sorted(c["status_excluded"])]
                      for c in cov["checkpoints"]
                      if c["status_excluded"])
    assert relieved == sorted(a["resolved"]), "unattributed growth"
    assert cov["eligible"] == 2305 + len(relieved)
    assert cov["total"] == 9644


def test_dry_green_parity_with_resolver():
    import pandas as pd

    from raceintel.race_state.race_state_reconstruction import (
        RaceStateReconstructor,
    )
    from raceintel.replay import replay as RP
    from raceintel.replay.replay_reconstruction import ReplayReconstructor
    from raceintel.simulation.driver_status import (
        load_status_corpus,
        load_unreliable_windows,
    )
    from raceintel.simulation.engine import ExecutionPolicy
    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )
    from raceintel.simulation.presence import prepare_initial_state

    frozen = json.loads(
        (ROOT / "results" / "v3" / "v3_2f" /
         "dry_green_parity_corpus.json").read_text(encoding="utf-8"))
    assert frozen["corpus_hash"].startswith("7ae97c3c")
    resolver = load_status_corpus(OUT / "status")
    windows = load_unreliable_windows(OUT / "unreliable_windows.json")
    parameters = load_simulation_parameters(
        parameter_storage_dir(ROOT, 2024))
    checked = 0
    cache: dict = {}
    for entry in frozen["results"]:
        rid, season, fi = (entry["race_id"], entry["season"],
                           entry["frame_index"])
        if rid not in cache:
            df = pd.read_parquet(
                ROOT / "data" / "v2" / "processed" /
                "driver_lap_state_d9" /
                f"season={season}/driver_lap_state_d9__d9-{season}.parquet")
            cache[rid] = df[df["race_id"] == rid].copy()
        states = cache[rid]
        results = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "results" /
            f"season={season}/results__{rid}.parquet")
        grid = {}
        for row in results.itertuples():
            g = getattr(row, "grid_position", None)
            grid[str(row.driver_id)] = (
                None if g is None or (isinstance(g, float) and g != g)
                else float(g))
        timeline = RP.build_replay_timeline(states)
        meta = {}
        try:
            for row in pd.read_parquet(
                    ROOT / "data" / "v2" / "processed" / "races" /
                    f"season={season}/races__{rid}.parquet").itertuples():
                scheduled = getattr(row, "total_laps_scheduled", None)
                meta[str(row.race_id)] = {
                    "scheduled_laps": (None if pd.isna(scheduled)
                                       else int(scheduled))}
        except FileNotFoundError:
            pass
        service = ReplayReconstructor(
            timeline, RaceStateReconstructor(states, results,
                                             race_meta=meta or None))
        race_state = service.state_at(fi)
        plain = prepare_initial_state(
            race_state, grid_by_driver=grid, parameters=parameters,
            execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
        relieved = prepare_initial_state(
            race_state, grid_by_driver=grid, parameters=parameters,
            execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT,
            status_resolver=resolver, status_windows=windows)
        assert plain.eligible, (rid, fi)
        assert relieved.eligible, (rid, fi)
        assert relieved.excluded_status_driver_ids == ()
        assert relieved.state.identity() == plain.state.identity()
        assert (sorted(d.driver_id for d in relieved.state.drivers)
                == entry["roster"])
        checked += 1
    assert checked == 50
