"""V3.2G corpus verification (Tier-3, corpus-dependent manifest).

Verifies every frozen V3.2G finding against the ignored corpus:
- position_null provenance (generated-row overlap, trailing-only,
  winner/podium/top-5 counts),
- STOPPED evaluation (precision, later-rows, latency, seasons),
- agreement matrix and terminal-absence recall,
- causal-table freeze integrity,
- runtime label firewall (no results-label imports in runtime paths),
- dry-green MC2-E parity (V3.2F corpus, Part AH gate).

Deterministic; no model, no refit, no science change.
"""

import glob
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

GDIR = ROOT / "results" / "v3" / "v3_2g"


def _hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   allow_nan=False, default=str).encode()).hexdigest()


def _tables():
    tables = json.loads(
        (GDIR / "causal_tables.json").read_text(encoding="utf-8"))
    assert _hash({k: v for k, v in tables.items()
                  if k != "freeze_hash"}) == tables["freeze_hash"]
    assert tables["freeze_hash"] == \
        "1465c11b50e898ca094ed35dd87bd075b446c26bdb55d73fe878bb14e0d7b0a8"
    return tables


def _eval():
    return json.loads(
        (GDIR / "offline_evaluation.json").read_text(encoding="utf-8"))


def test_causal_tables_frozen():
    tables = _tables()
    assert tables["n_null_episodes"] == 261
    assert tables["n_stopped_messages"] == 62
    assert tables["n_obs_episodes"] == 2973


def test_position_null_provenance_overlap():
    import pandas as pd

    frames = []
    for f in sorted(glob.glob(
            str(ROOT / "data" / "v2" / "processed" / "driver_laps" /
                "season=*" / "driver_laps__*.parquet"))):
        frames.append(pd.read_parquet(f))
    dl = pd.concat(frames, ignore_index=True)
    gen = dl[dl["fastf1_generated"] == True]  # noqa: E712
    null = dl[dl["position"].isna()]
    assert len(gen) == 294
    assert len(null) == 294
    assert set(gen.index) == set(null.index)


def test_position_null_all_trailing():
    tables = _tables()
    for e in tables["null_episodes"]:
        later = [x for x in tables["obs_episodes"]
                 if (x["race_id"], x["driver_id"])
                 == (e["race_id"], e["driver_id"])][0]
        assert e["generated_laps"][-1] >= (later["last_timed_lap"] or 0)


def test_position_null_winner_firewall():
    ev = _eval()
    n = ev["null_eval"]
    assert sorted([(e["race_id"], e["driver_id"]) for e in n
                   if e["winner"]]) == [
        ("2018-r02-R", "vettel"), ("2020-r01-R", "bottas"),
        ("2022-r18-R", "max_verstappen")]
    assert sum(1 for e in n if e["podium"]) == 7
    assert sum(1 for e in n
               if e["classified"] is not None
               and e["classified"] <= 5) == 9


def test_stopped_evaluation():
    ev = _eval()
    s = ev["stop_eval"]
    assert len(s) == 62
    assert sum(1 for e in s if e["dnf"]) == 57
    assert sum(1 for e in s if e["returned_after_message"]) == 9
    assert sorted([(e["race_id"], e["driver_id"]) for e in s
                   if e["winner"]]) == [("2021-r06-R", "perez")]
    assert len({(e["race_id"], e["driver_id"]) for e in s
                if e["returned_after_message"] or not e["terminal"]}) == 14


def test_stopped_season_instability():
    tables = _tables()
    by_season = Counter(x["race_id"][:4]
                        for x in tables["stopped_messages"])
    assert by_season["2023"] == 0
    assert sum(by_season.values()) == 62


def test_no_retired_message_family():
    import pandas as pd

    hits = 0
    for f in sorted(glob.glob(
            str(ROOT / "data" / "v2" / "processed" / "race_control" /
                "season=*" / "race_control__*.parquet"))):
        rc = pd.read_parquet(f)
        hits += int(rc["message_text"].fillna("").str.contains(
            "RETIRE", case=False, regex=False).sum())
    assert hits == 0


def test_runtime_label_firewall():
    """Truth columns stay out of runtime status/eligibility paths.

    The frozen RaceState firewall (label_outcome_fields) must still
    exclude every V3.2G-relevant outcome name, and the runtime
    status-relevant modules must not reference them at all. R7
    evaluation (validation.py) is the designated evaluation seam and
    is excluded from this check by design.
    """
    from raceintel.race_state.race_state import label_outcome_fields

    outcome = label_outcome_fields()
    for name in ("dnf_flag", "winner_flag", "podium_flag",
                 "classified_position", "position_final", "status_text"):
        assert name in outcome, name
    import re

    forbidden = re.compile(
        r"dnf_flag|winner_flag|podium_flag|classified_position|"
        r"position_final|status_text")
    runtime_modules = [
        "raceintel/simulation/presence.py",
        "raceintel/simulation/adapter.py",
        "raceintel/simulation/engine.py",
        "raceintel/simulation/field_contract.py",
        "raceintel/simulation/regime_support.py",
        "raceintel/race_state/race_state_reconstruction.py",
    ]
    for rel in runtime_modules:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert not forbidden.search(text), rel


def test_transient_cases_preserved():
    tables = _tables()
    gaps = [e for e in tables["obs_episodes"]
            if e["returned_after_gap"]]
    # Lap sequences are contiguous corpus-wide (factual zero); driver
    # transience lives at checkpoint grain and in stopped-then-observed
    # rows, both recorded in the protection corpus.
    assert gaps == []
    ev = _eval()
    returned = [(e["race_id"], e["driver_id"]) for e in ev["stop_eval"]
                if e["returned_after_message"]]
    assert len(returned) == 9
    assert any(e["winner"] for e in ev["null_eval"])
    prot = json.loads(
        (GDIR / "transient_protection.json").read_text(encoding="utf-8"))
    assert prot["v32c_transient_records"] == {
        "n": 407, "top5": 55, "winners": 6,
        "note": prot["v32c_transient_records"]["note"]}
    assert len(prot["returned_after_stopped"]) == 9


def test_dry_green_parity_corpus_bit_exact():
    import concurrent.futures

    import freeze_v3_2f_parity_corpus as F

    frozen = json.loads(
        (ROOT / "results" / "v3" / "v3_2f" /
         "dry_green_parity_corpus.json").read_text(encoding="utf-8"))
    assert frozen["corpus_hash"].startswith("7ae97c3c")
    corpus = [
        {"race_id": r["race_id"], "season": r["season"],
         "frame_index": r["frame_index"], "stage": r["stage"],
         "fold_through": r["fold_through"], "roster": r["roster"]}
        for r in frozen["results"]]
    with concurrent.futures.ProcessPoolExecutor(max_workers=8) as pool:
        outs = list(pool.map(F._worker, corpus))
    assert all(o.get("ok") for o in outs)

    def _norm(obj):
        return json.loads(json.dumps(obj, sort_keys=True, default=str))

    by_key = {(r["race_id"], r["frame_index"]): r
              for r in frozen["results"]}
    for o in outs:
        r = o["result"]
        ref = by_key[(r["race_id"], r["frame_index"])]
        for key in ("valid", "invalid", "winner_counts",
                    "winner_frequency", "expected_finish",
                    "position_counts", "sample_order"):
            assert _norm(r[key]) == _norm(ref[key]), (
                r["race_id"], r["frame_index"], key)
