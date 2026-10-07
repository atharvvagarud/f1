"""V3.2J driver-status models (source-safe, normal CI).

Pure-logic pins for the immutable raw TimingData adapter, the causal
state-at-T rule, the T1-T4 lifecycle, poison invariance, and the
exclusion-only presence helper. Fixture streams only: no corpus, no
network, no simulation.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from raceintel.simulation import driver_status as DS  # noqa: E402
from raceintel.simulation.presence import (  # noqa: E402
    status_exclusions_for_offenders,
)

# T1 < T_true < T2; T2 < T_clear < T3; T3 < T_true2 < T4 (Part T fixture).
_FIXTURE = (
    "00:10:00.000{\"Lines\":{\"44\":{\"Retired\":false}}}\n"
    "00:20:00.000{\"Lines\":{\"44\":{\"Retired\":true}}}\n"
    "00:20:00.000{\"Lines\":{\"77\":{\"InPit\":true,\"Stopped\":true}}}\n"
    "00:30:00.000{\"Lines\":{\"44\":{\"GapToLeader\":\"+1.000\"}}}\n"
    "00:40:00.000{\"Lines\":{\"44\":{\"Retired\":false}}}\n"
    "00:50:00.000{\"Lines\":{\"44\":{\"Retired\":true}}}\n"
)
T1, T_TRUE, T2, T_CLEAR, T3, T_TRUE2, T4 = (
    599.0, 1200.0, 1500.0, 2400.0, 2700.0, 3000.0, 3300.0)


def _fixture_transitions():
    events, _ = DS.parse_timing_stream(_FIXTURE)
    return DS.build_retired_transitions(events)


def test_clock_parse():
    assert DS.clock_to_seconds("00:00:04.103") == 4.103
    assert DS.clock_to_seconds("02:28:36.888") == 2 * 3600 + 28 * 60 + 36.888


def test_parser_extracts_retired_only():
    events, diag = DS.parse_timing_stream(_FIXTURE)
    assert diag.n_retired_updates == 4
    assert diag.n_stopped_updates == 1
    assert diag.n_inpit_updates == 1
    assert all(v in (True, False) for _, _, v in events)
    assert {d for _, d, _ in events} == {"44"}


def test_missing_key_preserves_state():
    # GapToLeader-only delta at 00:30 carries no Retired: no event.
    events, _ = DS.parse_timing_stream(_FIXTURE)
    times = sorted(t for t, d, _ in events if d == "44")
    assert times == [600.0, T_TRUE, T_CLEAR, T_TRUE2]


def test_tied_timestamps_deterministic():
    again, _ = DS.parse_timing_stream(_FIXTURE)
    events, _ = DS.parse_timing_stream(_FIXTURE)
    assert events == again


def test_malformed_rows_counted_and_skipped():
    events, diag = DS.parse_timing_stream(
        "short\n"
        "00:01:00.000{not json\n"
        "00:02:00.000{\"Lines\":{\"44\":{\"Retired\":true}}}\n")
    assert diag.n_malformed_rows == 2
    assert events == [(120.0, "44", True)]


def test_unknown_structure_fails_closed():
    for body in ("00:01:00.000[1,2,3]\n",
                 "00:01:00.000{\"Lines\":[1,2]}\n"):
        try:
            DS.parse_timing_stream(body)
        except ValueError:
            continue
        raise AssertionError(f"no fail-closed for {body!r}")


def test_lifecycle_t1_t2_t3_t4():
    trans = _fixture_transitions()["44"]
    assert DS.retired_known_at(trans, T1) is None
    assert DS.retired_known_at(trans, T2) is True
    assert DS.retired_known_at(trans, T3) is False
    assert DS.retired_known_at(trans, T4) is True


def test_exact_timestamp_equality_counts():
    trans = _fixture_transitions()["44"]
    assert DS.retired_known_at(trans, T_TRUE) is True
    assert DS.retired_known_at(trans, T_CLEAR) is False


def test_first_true_is_not_sticky():
    trans = _fixture_transitions()["44"]
    assert DS.retired_known_at(trans, T3) is False


def test_unknown_driver_is_unknown():
    assert DS.retired_known_at([], T4) is None
    assert DS.retired_known_at(None, T4) is None


def test_future_rows_poison_invariant():
    trans = _fixture_transitions()["44"]
    before = DS.retired_known_at(trans, T2)
    extended = trans + [(T4 + 100.0, True), (T4 + 200.0, False)]
    assert DS.retired_known_at(extended, T2) == before


def test_result_labels_cannot_reach_status():
    # The adapter/resolver API surface takes no label input.
    import inspect
    sig = inspect.signature(DS.DriverStatusResolver.retired_known_at)
    assert set(sig.parameters) == {"self", "race_id", "driver_id", "T"}
    sig2 = inspect.signature(DS.retired_known_at)
    assert set(sig2.parameters) == {"transitions", "T"}


def test_stopped_is_not_retirement():
    events, _ = DS.parse_timing_stream(_FIXTURE)
    trans = DS.build_retired_transitions(events)
    assert "77" not in trans


def test_contract_true_only_excludes():
    corpus = {"r": {"a": [(100.0, True)], "b": [(100.0, False)]}}
    res = DS.DriverStatusResolver(corpus)
    assert res.retired_known_at("r", "a", 200.0) is True
    assert res.retired_known_at("r", "b", 200.0) is False
    assert res.retired_known_at("r", "c", 200.0) is None
    assert res.retired_known_at("unknown-race", "a", 200.0) is None
    assert res.retired_known_at("r", "a", 50.0) is None


def test_presence_helper_requires_every_offender_true():
    corpus = {"r": {"a": [(100.0, True)], "b": [(100.0, True)]}}
    res = DS.DriverStatusResolver(corpus)
    assert status_exclusions_for_offenders(
        ("a", "b"), resolver=res, race_id="r", T=200.0) == ("a", "b")
    # one False -> whole checkpoint stays refused
    corpus2 = {"r": {"a": [(100.0, True)], "b": [(100.0, False)]}}
    res2 = DS.DriverStatusResolver(corpus2)
    assert status_exclusions_for_offenders(
        ("a", "b"), resolver=res2, race_id="r", T=200.0) is None
    # unknown -> None; empty -> None; no resolver -> None
    assert status_exclusions_for_offenders(
        ("a", "zzz"), resolver=res, race_id="r", T=200.0) is None
    assert status_exclusions_for_offenders(
        (), resolver=res, race_id="r", T=200.0) is None
    assert status_exclusions_for_offenders(
        ("a",), resolver=None, race_id="r", T=200.0) is None


def test_presence_helper_honors_unreliable_windows():
    corpus = {"r": {"a": [(100.0, True), (300.0, False)]}}
    res = DS.DriverStatusResolver(corpus)
    windows = {("r", "a"): [(100.0, 300.0)]}
    assert status_exclusions_for_offenders(
        ("a",), resolver=res, race_id="r", T=200.0,
        windows=windows) is None
    assert status_exclusions_for_offenders(
        ("a",), resolver=res, race_id="r", T=200.0) == ("a",)


def test_no_runtime_network_dependency():
    src = Path(DS.__file__).read_text(encoding="utf-8")
    for token in ("urllib", "socket", "requests", "http.client",
                  "livetiming", "formula1.com", "fastf1"):
        assert token not in src, token


def test_schema_variants_tolerated():
    # 2024-style extra Status key alongside Retired must not break parse.
    events, diag = DS.parse_timing_stream(
        "00:01:00.000{\"Lines\":{\"44\":{\"Retired\":true,\"Status\":1,"
        "\"InPit\":false}}}\n")
    assert events == [(60.0, "44", True)]
    assert diag.n_malformed_rows == 0
