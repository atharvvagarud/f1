"""D9 real-data validation (optional: skipped when D7/D5 canonical data absent).

These tests run only where the canonical parquet exists (``data/v2`` is
gitignored, so clean clones skip). They execute the real whole-scope D9 build
(twice for byte-identical determinism) and assert measured integrity over the
actual data:

- full 2018-2025 reconciliation: D7 189,420 state rows -> D9 189,420 derived
  state rows (delta 0); official result population 3,458 -> 3,458 label rows;
- state/label PK + null + temporal integrity and label separation;
- winner invariant (one factual winner per race; 173/173);
- cross-source label comparison vs D4 Tier-B (0 disagreements on non-null
  positions; the known 3 FastF1-null/Jolpica-ranked W rows reported);
- representative races (2023 Bahrain, 2019 Germany wet, 2022 Monaco, 2021
  Belgium shortened, 2021 Britain, 2022 Japan shortened, a 2018 race, 2024
  Bahrain, a 2025 race) reconcile and show correct derived track state /
  PARTIAL handling;
- telemetry remains deferred (ADR-0001): no telemetry entity and no
  telemetry columns anywhere in the D9 outputs.

No network, no FastF1, no telemetry reads.
"""

import pandas as pd
import pytest

from raceintel import contracts as C
from raceintel.pipeline import d7
from raceintel.pipeline import d7schema as D7S
from raceintel.pipeline import d9
from raceintel.pipeline import d9schema as S
from raceintel.config import V2Paths

ROOT = V2Paths.resolve().root
_HAS_DATA = (ROOT / "data/v2/processed/driver_laps/season=2023").is_dir()

REPRESENTATIVE = [
    (2023, "2023-r01-R"),
    (2019, "2019-r11-R"),  # wet / multiple SC + red flag
    (2022, "2022-r07-R"),  # wet / red flag
    (2021, "2021-r12-R"),  # shortened (PARTIAL)
    (2021, "2021-r10-R"),
    (2022, "2022-r18-R"),  # shortened (PARTIAL)
    (2018, "2018-r11-R"),
    (2024, "2024-r01-R"),
    (2025, "2025-r06-R"),
]


@pytest.fixture(scope="session")
def d9_build():
    if not _HAS_DATA:
        pytest.skip("D5/D6/D7 canonical data not present (data/v2 gitignored)")
    paths = V2Paths.resolve()
    report1 = d9.build_dataset(paths, write_artifacts=True)
    report2 = d9.build_dataset(paths, write_artifacts=True)
    val = d9.validate_dataset(paths)
    cross = d9.cross_source_label_comparison(paths)
    checksums = {f: s["sha256"] for f, s in report1["files"].items()}
    checksums2 = {f: s["sha256"] for f, s in report2["files"].items()}
    assert checksums == checksums2, "deterministic rebuild changed hashes"
    return paths, report1, val, cross


def _state(paths, season, race_id):
    st = d9.read_d9_state_season(paths, season)
    return st[st["race_id"] == race_id]


def test_full_scope_reconciliation(d9_build):
    paths, report, val, cross = d9_build
    assert report["state_rows"] == 189_420
    assert report["label_rows"] == 3_458
    assert val["state_rows"] == 189_420
    assert val["label_rows"] == 3_458
    assert val["state_duplicate_pks"] == 0
    assert val["state_null_pks"] == 0
    assert val["label_duplicate_pks"] == 0
    assert val["label_null_pks"] == 0
    assert val["integrity_ok"] is True
    assert val["findings"] == []
    assert all(v == 0 for v in val["temporal"].values())
    assert val["winner_invariant_exceptions"] == []
    assert val["label_columns_in_state"] == []


def test_d7_to_d9_state_delta_zero(d9_build):
    paths, report, val, cross = d9_build
    for season in range(2018, 2026):
        d7st = d7.read_enriched_season(paths, season)
        d9st = d9.read_d9_state_season(paths, season)
        assert len(d9st) == len(d7st)
        assert list(d9st.columns[:len(D7S.ENRICHED_COLUMNS)]) == \
            D7S.ENRICHED_COLUMNS
        assert list(d9st.columns) == S.STATE_COLUMNS


def test_cross_source_label_comparison(d9_build):
    paths, report, val, cross = d9_build
    assert cross["label_rows_compared"] == 3_458
    assert cross["tierb_matches"] == 3_458
    assert cross["position_final_disagreements"] == []
    assert cross["position_text_disagreements"] == 0
    assert cross["points_disagreements"] == 0
    # The 3 known DNS/withdrawn rows: FastF1 leaves final position null,
    # Jolpica ranks them at the back. Reported, never overwritten.
    ranked = cross["fastf1_null_jolpica_ranked"]
    assert len(ranked) == 3
    assert {r["race_id"] for r in ranked} == {
        "2021-r22-R", "2022-r02-R", "2023-r15-R"}
    assert all(r["token"] == "W" for r in ranked)


def test_representative_races_derived_state(d9_build):
    paths, report, val, cross = d9_build
    for season, race_id in REPRESENTATIVE:
        st = _state(paths, season, race_id)
        assert len(st) > 0
        assert st.duplicated(subset=["race_id", "driver_id",
                                     "lap_number"]).sum() == 0
        # derived columns present and consistent
        known = st[st["track_state"].notna()]
        if len(known):
            n_true = known[["flag_yellow", "flag_safety_car", "flag_red",
                            "flag_vsc"]].sum(axis=1)
            expected = (known["track_state"] != "all_clear").astype(int)
            assert (n_true == expected).all()
        # leader laps >= own lap; progress in [0,1]
        assert (st.loc[st["race_leader_laps_at_state"].notna(),
                       "race_leader_laps_at_state"]
                >= st["lap_number"]).all()
        pr = st[st["race_progress_frac"].notna()]
        assert ((pr["race_progress_frac"] >= 0)
                & (pr["race_progress_frac"] <= 1.0 + 1e-6)).all()
        assert (st.loc[st["laps_since_last_pit_stop"].notna(),
                       "laps_since_last_pit_stop"] >= 0).all()
        assert (st.loc[st["stint_lap"].notna(), "stint_lap"] >= 1).all()


def test_partial_shortened_races_represented(d9_build):
    paths, report, val, cross = d9_build
    bel = _state(paths, 2021, "2021-r12-R")
    assert len(bel) == 60
    assert (bel["source_unit_status"] == "partial").all()
    assert bel["shortened_race"].all()
    jap = _state(paths, 2022, "2022-r18-R")
    assert len(jap) == 507
    assert (jap["source_unit_status"] == "partial").all()
    # time-limited Monaco stays represented too.
    mon = _state(paths, 2022, "2022-r07-R")
    assert (mon["shortened_race"] == True).all()  # noqa: E712


def test_wet_race_track_state_flags_present(d9_build):
    paths, report, val, cross = d9_build
    # Germany 2019 and Monaco 2022 contained SC/VSC/red-flag phases: the
    # derived track-state tokens must show non-all-clear states.
    for season, race_id in ((2019, "2019-r11-R"), (2022, "2022-r07-R")):
        st = _state(paths, season, race_id)
        assert (st["track_state"] != "all_clear").any()
        assert st["track_state"].notna().all()  # full status coverage era


def test_label_vs_state_separation_full_dataset(d9_build):
    paths, report, val, cross = d9_build
    result_labels = set(C.RESULTS.label_columns())
    for season in range(2018, 2026):
        st = d9.read_d9_state_season(paths, season)
        assert not (set(st.columns) & result_labels)
        lb = d9.read_d9_label_season(paths, season)
        assert list(lb.columns) == S.LABEL_COLUMNS
        assert lb.duplicated(subset=["race_id", "driver_id"]).sum() == 0


def test_telemetry_deferred_invariant(d9_build):
    paths, report, val, cross = d9_build
    # no canonical telemetry_summary entity exists
    assert not (ROOT / "data/v2/processed/telemetry_summary").exists()
    for season in range(2018, 2026):
        st = d9.read_d9_state_season(paths, season)
        assert not any("tel" in c.lower() for c in st.columns)
    # D9 manifest records telemetry as deferred
    assert "telemetry" in report["telemetry"]
    assert "deferred" in report["telemetry"]
