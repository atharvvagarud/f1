"""D6 real-data validation (optional: skipped when D5 canonical data absent).

These tests run only where the D5 processed parquet exists (``data/v2`` is
gitignored, so clean clones skip). They execute the real whole-scope build
(session-scoped) and assert measured integrity over actual data:

- full 2018-2025 row reconciliation (189,420 source rows -> 189,420 state
  rows, zero loss, zero duplicate PKs);
- representative races from the D6 mission list reconcile row-for-row and
  preserve source missingness;
- PARTIAL races (2021 Belgium, 2022 Japan) stay represented with quality
  metadata;
- label separation holds on the full dataset.

No network, no FastF1. Build outputs are the gitignored canonical data/v2.
"""

import pandas as pd
import pytest

from v2 import contracts as C
from v2 import d6schema as S
from v2 import d6
from v2.config import V2Paths
from v2.errors import IngestionError
from v2.storage import dest_for_unit

ROOT = V2Paths.resolve().root
_HAS_DATA = (ROOT / "data/v2/processed/driver_laps/season=2023").is_dir()

# Representative races required by the D6 mission (§20).
REPRESENTATIVE = [
    (2023, 1, "2023-r01-R"),   # 2023 Bahrain (normal, late era)
    (2019, 11, "2019-r11-R"),  # 2019 Germany (wet)
    (2022, 7, "2022-r07-R"),   # 2022 Monaco (wet/red-flag missingness)
    (2021, 12, "2021-r12-R"),  # 2021 Belgium (PARTIAL farce)
    (2021, 10, "2021-r10-R"),  # 2021 Britain (sprint weekend)
    (2022, 18, "2022-r18-R"),  # 2022 Japan (PARTIAL, shortened)
    (2024, 1, "2024-r01-R"),   # 2024 Bahrain
    (2018, 11, "2018-r11-R"),  # 2018 Germany (sparse track status/traps)
    (2025, 6, "2025-r06-R"),   # 2025 Miami (source tyre/compound gaps)
]


@pytest.fixture(scope="session")
def d6_build():
    if not _HAS_DATA:
        pytest.skip("D5 canonical data not present (data/v2 gitignored)")
    paths = V2Paths.resolve()
    # Deterministic rebuild: build twice, compare bytes + logical equality.
    report1 = d6.build_dataset(paths, write_artifacts=True)
    report2 = d6.build_dataset(paths, write_artifacts=True)
    val = d6.validate_dataset(paths)
    checksums = {f: s["sha256"] for f, s in report1["files"].items()}
    checksums2 = {f: s["sha256"] for f, s in report2["files"].items()}
    assert checksums == checksums2, "deterministic rebuild changed file hashes"
    return paths, report1, val


def _read_source(paths, season, race_id, entity):
    dest = dest_for_unit(paths.processed_dir, entity, season, race_id)
    return pd.read_parquet(dest, engine="pyarrow")


def _state_for(paths, season, race_id):
    st = d6.read_state_season(paths, season)
    return st[st["race_id"] == race_id]


def test_full_scope_reconciliation(d6_build):
    paths, report, val = d6_build
    assert report["input_driver_lap_rows"] == 189_420
    assert report["canonical_state_rows"] == 189_420
    assert report["dropped_rows"] == 0
    assert report["duplicate_input_pks"] == 0
    assert report["quality_rows"] == 173
    assert report["races"] == 173
    assert val["state_rows"] == 189_420
    assert val["duplicate_state_pks"] == 0
    assert val["null_state_pks"] == 0
    assert val["findings"] == []
    assert val["label_separation_ok"] is True
    assert val["fk_ok"] is True


def test_representative_races_row_reconcile_and_missingness(d6_build):
    paths, report, _ = d6_build
    # Missingness must be identical for every column carried verbatim.
    state_carried = {"position": "position", "lap_start_s": "lap_start_s",
                     "lap_time_s": "lap_time_s",
                     "sector_1_s": "sector_1_s", "sector_2_s": "sector_2_s",
                     "sector_3_s": "sector_3_s",
                     "sector_1_end_s": "sector_1_end_s",
                     "sector_2_end_s": "sector_2_end_s",
                     "sector_3_end_s": "sector_3_end_s",
                     "speed_i1_kmh": "speed_i1_kmh",
                     "speed_i2_kmh": "speed_i2_kmh",
                     "speed_fl_kmh": "speed_fl_kmh",
                     "speed_st_kmh": "speed_st_kmh",
                     "compound": "compound", "tyre_life": "tyre_life",
                     "stint_number": "stint_number",
                     "fresh_tyre": "fresh_tyre", "pit_in_s": "pit_in_s",
                     "pit_out_s": "pit_out_s",
                     "track_status": "track_status",
                     "deleted": "deleted",
                     "deleted_reason": "deleted_reason",
                     "is_accurate": "is_accurate",
                     "fastf1_generated": "fastf1_generated"}
    for season, round_no, race_id in REPRESENTATIVE:
        src = _read_source(paths, season, race_id, "driver_laps")
        st = _state_for(paths, season, race_id)
        assert len(st) == len(src), (
            f"{race_id}: state {len(st)} != source {len(src)}")
        assert st.duplicated(subset=["race_id", "driver_id",
                                     "lap_number"]).sum() == 0
        # Identifiers present and evidence-backed.
        assert (st["season"] == season).all()
        assert (st["round_no"] == round_no).all()
        assert (st["event_id"] == f"{season}-r{round_no:02d}").all()
        assert st["circuit_id"].notna().all()
        assert st["constructor_id"].notna().all()
        # Missingness preserved verbatim for every carried source column.
        for st_col, src_col in state_carried.items():
            a = int(st[st_col].isna().sum())
            b = int(src[src_col].isna().sum())
            assert a == b, (
                f"{race_id} {st_col}: state nulls {a} != source {b}")


def test_known_source_gap_races_preserved(d6_build):
    paths, report, _ = d6_build
    # Monaco 2022: source tyre-life/compound missingness survives cast.
    m = _state_for(paths, 2022, "2022-r07-R")
    src = _read_source(paths, 2022, "2022-r07-R", "driver_laps")
    assert int(src["tyre_life"].isna().sum()) > 100
    assert int(m["tyre_life"].isna().sum()) == int(
        src["tyre_life"].isna().sum())
    # Miami 2025: compound/tyre-life/stint gaps preserved.
    mi = _state_for(paths, 2025, "2025-r06-R")
    src_mi = _read_source(paths, 2025, "2025-r06-R", "driver_laps")
    assert int(src_mi["compound"].isna().sum()) > 400
    assert int(mi["compound"].isna().sum()) == int(
        src_mi["compound"].isna().sum())


def test_partial_races_represented_with_quality_metadata(d6_build):
    paths, report, _ = d6_build
    q = pd.concat([d6.read_quality_season(paths, s)
                   for s in range(2018, 2026)], ignore_index=True)
    partial = q[q["source_unit_status"] == "partial"]
    assert set(partial["race_id"]) == {"2021-r12-R", "2022-r18-R"}
    for _, row in partial.iterrows():
        assert row["shortened_race"] is True
        assert row["partial_reason"]
    # Belgium farce row count 60, all state rows flagged partial/shortened.
    bel = _state_for(paths, 2021, "2021-r12-R")
    assert len(bel) == 60
    assert (bel["source_unit_status"] == "partial").all()
    assert (bel["shortened_race"] == True).all()  # noqa: E712
    jap = _state_for(paths, 2022, "2022-r18-R")
    assert (jap["source_unit_status"] == "partial").all()
    # Quality metadata carries the verbatim partial reason.
    bq = q[q["race_id"] == "2021-r12-R"].iloc[0]
    assert "shortened race" in bq["partial_reason"]


def test_shortened_race_flag_data_derived(d6_build):
    paths, report, _ = d6_build
    q = pd.concat([d6.read_quality_season(paths, s)
                   for s in range(2018, 2026)], ignore_index=True)
    flagged = set(q[q["shortened_race"] == True]["race_id"])  # noqa: E712
    # All five races where the leader completed fewer laps than scheduled.
    expected = {row["race_id"] for _, row in q.iterrows()
                if row["total_laps_scheduled"] is not None
                and row["observed_leader_laps"] < row["total_laps_scheduled"]}
    assert flagged == expected
    assert {"2021-r12-R", "2022-r18-R", "2022-r07-R", "2020-r01-R",
            "2022-r17-R"} <= flagged


def test_no_label_columns_full_dataset(d6_build):
    paths, report, _ = d6_build
    for season in range(2018, 2026):
        st = d6.read_state_season(paths, season)
        assert not (set(st.columns) & set(C.RESULTS.label_columns()))
        assert list(st.columns) == S.STATE_COLUMNS


def test_pk_fk_timestamps_full_dataset(d6_build):
    paths, report, val = d6_build
    assert val["pks_ok"] and val["fk_ok"] and val["findings"] == []
    # state_time validity: lap start precedes state time within each row,
    # and state time is strictly increasing over lap number per driver.
    violations = 0
    for season in range(2018, 2026):
        st = d6.read_state_season(paths, season)
        both = st[st["lap_start_s"].notna() & st["state_time_s"].notna()]
        violations += int((both["lap_start_s"] > both["state_time_s"]).sum())
        g = st.sort_values("lap_number")
        inc = g.groupby(["race_id", "driver_id"])["state_time_s"].diff()
        violations += int((inc < 0).sum())
    assert violations == 0
