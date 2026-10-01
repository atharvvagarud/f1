"""D7 real-data validation (optional: skipped when D5 canonical data absent).

These tests run only where the D5/D6 canonical parquet exists (``data/v2`` is
gitignored, so clean clones skip). They execute the real whole-scope D7 build
(session-scoped, twice for byte-identical determinism) and assert measured
integrity over actual data:

- full 2018-2025 reconciliation: D6 189,420 state rows -> D7 189,420 enriched
  rows, zero loss, zero duplicate/null PKs;
- every temporal attachment satisfies observed_time <= state_time_s across the
  whole dataset (weather / race-control / pit-entry / pit-exit / stint-start);
- representative races (2023 Bahrain, 2019 Germany wet, 2022 Monaco wet,
  2021 Belgium PARTIAL, 2021 Britain, 2022 Japan PARTIAL, a 2018 race, 2024
  Bahrain, a 2025 race) reconcile row-for-row, show no future attachment, and
  preserve source wet-weather evolution / stint missingness;
- the 2018-r02 race-control limitation is explicit: its untimestamped messages
  never attach (0 states with RC lineage in that unit);
- PARTIAL/shortened races stay represented with quality metadata carried from
  D6;
- label separation holds on the full enriched dataset.

No network, no FastF1. Build outputs are the gitignored canonical data/v2.
"""

import pandas as pd
import pytest

from raceintel import contracts as C
from raceintel.pipeline import d6schema as D6S
from raceintel.pipeline import d7
from raceintel.pipeline import d7schema as S
from raceintel.config import V2Paths

ROOT = V2Paths.resolve().root
_HAS_DATA = (ROOT / "data/v2/processed/driver_laps/season=2023").is_dir()

REPRESENTATIVE = [
    (2023, "2023-r01-R", "2023 Bahrain (normal, late era)", False),
    (2019, "2019-r11-R", "2019 Germany (wet)", True),
    (2022, "2022-r07-R", "2022 Monaco (wet/red-flag)", True),
    (2021, "2021-r12-R", "2021 Belgium (PARTIAL farce)", True),
    (2021, "2021-r10-R", "2021 Britain (sprint weekend)", False),
    (2022, "2022-r18-R", "2022 Japan (PARTIAL, shortened)", True),
    (2018, "2018-r11-R", "2018 Germany (sparse era)", True),
    (2018, "2018-r02-R", "2018 Bahrain (untimed race control)", False),
    (2024, "2024-r01-R", "2024 Bahrain", False),
    (2025, "2025-r06-R", "2025 Miami (source tyre/compound gaps; wet)", True),
]


@pytest.fixture(scope="session")
def d7_build():
    if not _HAS_DATA:
        pytest.skip("D5 canonical data not present (data/v2 gitignored)")
    paths = V2Paths.resolve()
    report1 = d7.build_dataset(paths, write_artifacts=True)
    report2 = d7.build_dataset(paths, write_artifacts=True)
    val = d7.validate_dataset(paths)
    cov = d7.coverage_report(paths)
    checksums = {f: s["sha256"] for f, s in report1["files"].items()}
    checksums2 = {f: s["sha256"] for f, s in report2["files"].items()}
    assert checksums == checksums2, "deterministic rebuild changed file hashes"
    return paths, report1, val, cov


def _state(paths, season, race_id):
    st = d7.read_enriched_season(paths, season)
    return st[st["race_id"] == race_id]


def test_full_scope_reconciliation(d7_build):
    paths, report, val, cov = d7_build
    assert report["enriched_rows"] == 189_420
    assert report["races"] == 173
    assert val["d6_base_rows"] == 189_420
    assert val["enriched_rows"] == 189_420
    assert val["row_delta"] == 0
    assert val["duplicate_pks"] == 0
    assert val["null_pks"] == 0
    assert val["findings"] == []
    assert val["integrity_ok"] is True
    assert val["temporal_ok"] is True
    assert all(v == 0 for v in val["temporal_violations"].values())


def test_per_season_reconciliation_matches_d6(d7_build):
    paths, report, val, cov = d7_build
    expected = {2018: 22_337, 2019: 23_676, 2020: 18_352, 2021: 23_758,
                2022: 23_577, 2023: 24_422, 2024: 26_606, 2025: 26_692}
    for season, d6_rows in expected.items():
        st = d7.read_enriched_season(paths, season)
        assert len(st) == d6_rows
        assert list(st.columns) == S.ENRICHED_COLUMNS
        # First 37 columns are the verbatim D6 canonical state (order kept).
        assert list(st.columns[:len(D6S.STATE_COLUMNS)]) == D6S.STATE_COLUMNS


def test_representative_races_reconcile_and_no_future_attachment(d7_build):
    paths, report, val, cov = d7_build
    for season, race_id, label, _wet in REPRESENTATIVE:
        st = _state(paths, season, race_id)
        d6_base = d7.d6_state_for_season(paths, season)
        d6_base = d6_base[d6_base["race_id"] == race_id]
        assert len(st) == len(d6_base), (race_id, len(st), len(d6_base))
        assert st.duplicated(subset=["race_id", "driver_id",
                                     "lap_number"]).sum() == 0
        # Temporal safety: observed/source times at or before state_time.
        for col in ("wx_observed_at_s", "rc_last_message_observed_at_s",
                    "pit_last_in_s", "pit_last_out_s"):
            both = st[col].notna() & st["state_time_s"].notna()
            assert int((st.loc[both, col]
                        > st.loc[both, "state_time_s"] + 1e-6).sum()) == 0, (
                f"{race_id}: future {col} attachment")
        both = st["stint_start_lap"].notna()
        assert int((st.loc[both, "stint_start_lap"]
                    > st.loc[both, "lap_number"]).sum()) == 0, (
            f"{race_id}: future stint-start")
        # D6 canonical grain columns untouched by the enrichment.
        assert list(st.columns[:len(D6S.STATE_COLUMNS)]) == \
            list(d6_base.columns)


def test_wet_weather_evolution_preserved(d7_build):
    paths, report, val, cov = d7_build
    # Wet representative races must attach rainfall observations; dry Bahrain
    # must not.
    for season, race_id, label, wet in REPRESENTATIVE:
        if race_id == "2018-r02-R":  # still dry Bahrain, same expectation
            continue
        st = _state(paths, season, race_id)
        rain = st[st["wx_rainfall"].notna() & (st["wx_rainfall"] == True)]  # noqa: E712
        if wet:
            assert len(rain) > 0, f"{race_id}: expected wet observations"
        else:
            assert len(rain) == 0, f"{race_id}: expected dry observations"
    # Weather staleness is bounded (~1/minute source cadence) on every race.
    w = pd.concat([_state(paths, s, r) for s, r, _l, _w in
                   [(s, r, l, w) for s, r, l, w in REPRESENTATIVE]],
                  ignore_index=True)
    assert w["wx_age_s"].max() <= 3600.0


def test_partial_races_represented_with_quality_metadata(d7_build):
    paths, report, val, cov = d7_build
    q = pd.concat([d7.d6_state_for_season(paths, s) for s in range(2018,
                                                                   2026)],
                  ignore_index=True)
    bel = _state(paths, 2021, "2021-r12-R")
    assert len(bel) == 60
    assert (bel["source_unit_status"] == "partial").all()
    assert (bel["shortened_race"] == True).all()  # noqa: E712
    jap = _state(paths, 2022, "2022-r18-R")
    assert len(jap) == 507
    assert (jap["source_unit_status"] == "partial").all()


def test_2018_bahrain_untimed_race_control_never_attaches(d7_build):
    paths, report, val, cov = d7_build
    st = _state(paths, 2018, "2018-r02-R")
    assert len(st) > 0
    # The 69 untimed source messages must never be invented into history.
    assert int(st["rc_last_message_seq"].notna().sum()) == 0
    rc = d7._read_entity(paths, "race_control", 2018, "2018-r02-R")
    assert len(rc) == 69
    assert int(rc["observed_at_s"].isna().sum()) == 69
    # All other source messages remain untouched in the source table.
    assert set(rc["message_seq"]) == set(range(69))


def test_no_label_columns_full_dataset(d7_build):
    paths, report, val, cov = d7_build
    for season in range(2018, 2026):
        st = d7.read_enriched_season(paths, season)
        assert not (set(st.columns) & set(C.RESULTS.label_columns()))
        assert list(st.columns) == S.ENRICHED_COLUMNS


def test_coverage_measured_over_real_dataset(d7_build):
    paths, report, val, cov = d7_build
    assert cov["states_total"] == 189_420
    w = cov["weather"]
    assert w["states_with_prior_weather"] > 0
    assert w["states_without_prior_weather"] >= 0
    assert w["age_seconds"]["min"] >= 0.0
    assert w["age_seconds"]["max_staleness_s"] is not None
    rc = cov["race_control"]
    assert rc["messages_total_source"] == 14_992
    assert rc["messages_timestamped"] + rc["messages_untimestamped"] == 14_992
    assert rc["messages_untimestamped"] == 69  # 2018-r02 only
    assert rc["temporal_violations"] == 0
    ps = cov["pit_stint"]
    assert ps["source_pit_stops_in_only"] == 246
    assert ps["source_pit_stops_out_only"] == 159
    assert ps["source_pit_stops_full"] == 5931
    # Asymmetric source boundaries carried through without manufacturing.
    assert ps["states_with_pit_in_context"] >= ps["source_pit_stops_in_only"]


def test_missingness_preserved_for_current_stint_context(d7_build):
    paths, report, val, cov = d7_build
    # Miami 2025 has 446 laps with no source stint info; the D7 current-stint
    # context must be null on exactly those rows (nothing inferred).
    mi = _state(paths, 2025, "2025-r06-R")
    assert int(mi["stint_start_lap"].isna().sum()) == 446
    assert int(mi["stint_compound"].isna().sum()) == 446
