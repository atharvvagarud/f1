"""P12-4 temporal spatial resolver tests (source-safe: synthetic only).

No observation corpus, no Tier-A tables, no FastF1: tiny synthetic
series plus tmp-dir artifact fixtures exercise the causal contract
(latest <= T, exact boundaries, future-poison, identity, geometry
linkage, cache). Corpus validation runs outside CI via measurement
scripts; the governed CI pin covers this file's collection count.
"""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from raceintel.spatial import contracts as SC
from raceintel.spatial import geometry as G
from raceintel.spatial import manifest as SM
from raceintel.spatial import validation as V
from raceintel.spatial.errors import (
    SpatialArtifactUnavailableError,
    SpatialGeometryMismatchError,
    SpatialIdentityError,
    SpatialProvenanceError,
    SpatialResolutionError,
)
from raceintel.spatial.io import (
    artifact_path,
    geometry_manifest_path,
    geometry_path,
    manifest_path,
    save_geometry_manifest,
    save_manifest,
    write_geometry_atomic,
    write_observations_atomic,
)
from raceintel.spatial.resolver import (
    DriverUniverseEntry,
    RaceSpatialStore,
    SpatialStoreCache,
    _DriverSeries,
    require_query_time,
    resolve_driver,
    resolve_frame,
    resolve_window,
    universe_from_race_state,
)

RACE = "2023-r01-R"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _series(times, xs, ys, source="pos", status="OnTrack"):
    times = np.asarray(times, dtype=np.float64)
    n = len(times)
    return _DriverSeries(
        times,
        np.asarray(xs, dtype=np.int64),
        np.asarray(ys, dtype=np.int64),
        np.asarray([source] * n, dtype=object),
        np.asarray([status] * n, dtype=object),
    )


def _mem_store(series, transform=None, status="COMPLETE",
               race_id=RACE, geometry_ok=False):
    return RaceSpatialStore(
        race_id=race_id, observation_content_sha256="a" * 64,
        observation_status=status, series=dict(series),
        transform=transform, geometry_sha256=("b" * 64 if geometry_ok
                                              else None),
        geometry_ok=geometry_ok, geometry_stale=False,
        geometry_problem=None if geometry_ok else "no geometry")


def _canonical_frame(race_id, rows):
    """rows: (driver_number, time, x, y[, status]) -> persisted frame."""
    raw = [{
        "race_id": race_id, "driver_number": drv,
        "observation_time_s": float(t), "x": int(x), "y": int(y),
        "z": 5, "source": "pos", "status": (r[4] if len(r) > 4
                                             else "OnTrack"),
        "source_observed_at": float(t),
    } for drv, t, x, y, *r in rows]
    return V.canonicalize_observations(pd.DataFrame(raw))


def _write_tmp_race(root, race_id, frame, status="COMPLETE",
                    reason=None, with_geometry=True,
                    geometry_source_hash=None):
    manifest = SM.new_manifest()
    content = V.logical_content_hash(frame)
    numbers = sorted(int(v) for v in frame["driver_number"].unique())
    provenance = SM.build_provenance(
        season=int(race_id[:4]), race_id=race_id, session="R",
        source_input_ref="synthetic/p12-4", fastf1_version="3.7.0",
        raw_row_count=len(frame), kept_row_count=len(frame),
        excluded_zero_fix_rows=0, excluded_exact_duplicate_rows=0,
        driver_numbers=numbers, expected_driver_numbers=numbers,
        time_min_s=float(frame["observation_time_s"].min()),
        time_max_s=float(frame["observation_time_s"].max()),
        observed_source_values=["pos"], observed_status_values=["OnTrack"],
        content_sha256=content)
    manifest = SM.set_race_row(manifest, race_id, status=status,
                               provenance=provenance
                               if status in ("COMPLETE", "PARTIAL")
                               else None,
                               reason=reason)
    save_manifest(manifest, manifest_path(root))
    write_observations_atomic(frame, artifact_path(root, race_id))
    if with_geometry:
        record = _geometry_record(race_id,
                                  geometry_source_hash or content)
        write_geometry_atomic(record, geometry_path(root, race_id))
        geometry_manifest = G.new_geometry_manifest()
        geometry_manifest = G.set_geometry_row(
            geometry_manifest, race_id, status=G.GEOMETRY_STATUS_COMPLETE,
            source_content_sha256=(geometry_source_hash or content),
            geometry_sha256=record["content_sha256"], n_points=64,
            pit_status=G.PIT_DEFERRED)
        save_geometry_manifest(geometry_manifest,
                               geometry_manifest_path(root))
    return content


def _geometry_record(race_id, source_hash):
    theta = np.linspace(0.0, 2 * math.pi, 64, endpoint=False)
    raw = np.stack([10000.0 + 5000.0 * np.cos(theta),
                    10000.0 + 5000.0 * np.sin(theta)], 1)
    transform = G.compute_transform(raw)
    rendered = G.apply_transform(raw, transform)
    record = {
        "schema_version": SC.SPATIAL_GEOMETRY_SCHEMA_VERSION,
        "race_id": race_id, "season": int(race_id[:4]),
        "layout_scope": "per-race",
        "algorithm_version": G.GEOMETRY_ALGORITHM_VERSION,
        "source": {"observation_content_sha256": source_hash},
        "main_track": {
            "points": [[float(v[0]), float(v[1])] for v in rendered],
            "raw_points": [[float(v[0]), float(v[1])] for v in raw],
            "n_points": 64, "closed_loop": True, "length_u": 31400.0,
        },
        "pit_lane": None, "pit_status": G.PIT_DEFERRED,
        "pit_defer_reason": "synthetic p12-4 fixture",
        "transform": transform, "quality": {}, "content_sha256": "",
    }
    record["content_sha256"] = G.geometry_content_hash(record)
    return record


def _simple_transform():
    raw = np.array([[0.0, 0.0], [1000.0, 500.0]])
    return G.compute_transform(raw)


# ---------------------------------------------------------------------------
# Part I — boundary lookup (the core temporal contract)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query,expected", [
    (9.9, None), (10.0, 10.0), (10.5, 10.0),
    (11.0, 11.0), (11.999, 11.0), (12.0, 12.0),
])
def test_boundary_lookup_exact(query, expected):
    store = _mem_store({44: _series([10.0, 11.0, 12.0],
                                    [100, 200, 300], [1, 2, 3])})
    state = resolve_driver(store, 44, query)
    assert state.observation_time_s == expected
    if expected is None:
        assert state.availability == SC.AVAILABILITY_UNAVAILABLE
        assert state.raw_x is None and state.age_s is None
    else:
        assert state.age_s == pytest.approx(query - expected)
        assert state.availability == SC.AVAILABILITY_FRESH


# ---------------------------------------------------------------------------
# Part J — future poison (must fail if nearest-neighbor ever lands)
# ---------------------------------------------------------------------------

def test_future_poison_never_selects_next_sample():
    store = _mem_store({44: _series([10.0, 10.01], [100, 999999],
                                    [50, 888888])})
    state = resolve_driver(store, 44, 10.005)
    assert state.observation_time_s == 10.0
    assert state.raw_x == 100
    assert state.raw_y == 50


def test_future_poison_at_availability_edges():
    store = _mem_store({7: _series([100.0, 200.0], [11, 999999],
                                   [22, 888888])})
    assert resolve_driver(store, 7, 103.0).raw_x == 11  # FRESH edge
    assert resolve_driver(store, 7, 103.0).availability == "FRESH"
    assert resolve_driver(store, 7, 115.0).raw_x == 11  # STALE edge
    assert resolve_driver(store, 7, 115.0).availability == "STALE"


def test_window_poison_excludes_sample_just_after_t():
    store = _mem_store({44: _series([10.0, 10.01], [100, 999999],
                                    [50, 888888])})
    samples = resolve_window(store, 44, 10.005, 5.0)
    assert [s.observation_time_s for s in samples] == [10.0]
    assert samples[0].raw_x == 100


# ---------------------------------------------------------------------------
# Parts K/L — before-first / after-last
# ---------------------------------------------------------------------------

def test_before_first_observation_is_unavailable():
    store = _mem_store({44: _series([10.0], [100], [50])})
    state = resolve_driver(store, 44, 9.999)
    assert state.availability == SC.AVAILABILITY_UNAVAILABLE
    assert state.observation_time_s is None
    assert state.age_s is None
    assert state.raw_x is None and state.raw_y is None
    assert state.render_x is None and state.render_y is None
    assert state.source is None and state.status is None
    assert state.outside_viewport is False


@pytest.mark.parametrize("query,availability", [
    (102.0, "FRESH"), (103.0, "FRESH"), (110.0, "STALE"),
    (115.0, "STALE"), (115.001, "UNAVAILABLE"), (200.0, "UNAVAILABLE"),
])
def test_after_last_governed_by_age(query, availability):
    store = _mem_store({44: _series([100.0], [100], [50])})
    state = resolve_driver(store, 44, query)
    assert state.availability == availability
    assert state.observation_time_s == 100.0
    assert state.age_s == pytest.approx(query - 100.0)


def test_stale_after_last_keeps_provenance_but_no_coords():
    store = _mem_store({44: _series([100.0], [100], [50])})
    state = resolve_driver(store, 44, 200.0)
    assert state.availability == SC.AVAILABILITY_UNAVAILABLE
    assert state.observation_time_s == 100.0
    assert state.age_s == pytest.approx(100.0)
    assert state.raw_x is None and state.render_x is None


# ---------------------------------------------------------------------------
# Part E — availability boundaries (frozen P12-1 thresholds)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("age,availability", [
    (0.0, "FRESH"), (3.0, "FRESH"), (15.0, "STALE"),
])
def test_availability_exact_boundaries(age, availability):
    store = _mem_store({44: _series([100.0], [1], [2])})
    state = resolve_driver(store, 44, 100.0 + age)
    assert state.availability == availability


def test_availability_just_past_boundaries():
    # NOTE: exact decimal offsets (e.g. nextafter(3.0)) do not survive
    # session-clock float addition (100.0 + nextafter(3.0) rounds back to
    # 103.0, age exactly 3.0 -> FRESH). Ownership is decided on the
    # computed float age; unambiguous offsets pin the STALE side.
    store = _mem_store({44: _series([100.0], [1], [2])})
    assert resolve_driver(store, 44, 103.001).availability == "STALE"
    assert resolve_driver(store, 44,
                          115.001).availability == "UNAVAILABLE"


def test_negative_age_is_invalid():
    with pytest.raises(Exception):
        SC.classify_availability(-0.001)
    with pytest.raises(Exception):
        SC.classify_availability(float("-inf"))


# ---------------------------------------------------------------------------
# Parts AF/AG — no-future + monotonic properties
# ---------------------------------------------------------------------------

def test_no_future_property_across_grid():
    store = _mem_store({
        1: _series([100.0, 101.5, 105.0], [1, 2, 3], [1, 2, 3]),
        44: _series([99.0, 103.0], [7, 8], [7, 8]),
    })
    for step in range(0, 120):
        query = 98.0 + step * 0.25
        for drv in (1, 44):
            state = resolve_driver(store, drv, query)
            if state.availability != SC.AVAILABILITY_UNAVAILABLE \
                    or state.observation_time_s is not None:
                assert state.observation_time_s <= query
                assert state.age_s == pytest.approx(
                    query - state.observation_time_s)
                assert state.age_s >= 0


def test_monotonic_queries_never_go_backwards():
    store = _mem_store({44: _series([10.0, 10.7, 11.3, 20.0],
                                    [1, 2, 3, 4], [1, 2, 3, 4])})
    seen = []
    query = 9.0
    while query < 25.0:
        state = resolve_driver(store, 44, query)
        seen.append(state.observation_time_s)
        query += 0.37
    causal = [t for t in seen if t is not None]
    assert causal == sorted(causal)


# ---------------------------------------------------------------------------
# Parts N/O — raw exactness + render transform
# ---------------------------------------------------------------------------

def test_raw_coordinates_equal_canonical_observation():
    store = _mem_store({16: _series([50.0, 51.0], [-12345, 67890],
                                    [11111, -22222])})
    state = resolve_driver(store, 16, 51.4)
    assert (state.raw_x, state.raw_y) == (67890, -22222)
    assert state.source == "pos" and state.status == "OnTrack"


def test_render_reuses_stored_transform_exactly():
    transform = _simple_transform()
    store = _mem_store({16: _series([50.0], [333], [444])},
                       transform=transform, geometry_ok=True)
    state = resolve_driver(store, 16, 52.0)
    expected = G.apply_transform(np.array([[333.0, 444.0]]), transform)
    assert state.render_x == pytest.approx(expected[0, 0])
    assert state.render_y == pytest.approx(expected[0, 1])


def test_same_raw_point_same_render_regardless_of_t():
    transform = _simple_transform()
    store = _mem_store({16: _series([50.0], [333], [444])},
                       transform=transform, geometry_ok=True)
    early = resolve_driver(store, 16, 50.0)
    late = resolve_driver(store, 16, 52.9)
    assert (early.render_x, early.render_y) == (late.render_x,
                                               late.render_y)


def test_no_geometry_means_no_render_coords():
    store = _mem_store({16: _series([50.0], [333], [444])})
    state = resolve_driver(store, 16, 51.0)
    assert state.availability == "FRESH"
    assert (state.raw_x, state.raw_y) == (333, 444)
    assert state.render_x is None and state.render_y is None


# ---------------------------------------------------------------------------
# Part P — off-track positions preserved, flagged, never clamped
# ---------------------------------------------------------------------------

def test_outside_viewport_preserved_and_flagged():
    transform = _simple_transform()  # bounds from (0,0)-(1000,500)
    store = _mem_store({16: _series([50.0, 51.0], [500, 5000],
                                    [250, 250])},
                       transform=transform, geometry_ok=True)
    inside = resolve_driver(store, 16, 50.5)
    assert inside.outside_viewport is False
    outside = resolve_driver(store, 16, 53.0)
    assert outside.raw_x == 5000  # true coordinate kept
    assert outside.render_x > 1  # not clamped into [0, 1]
    assert outside.outside_viewport is True


# ---------------------------------------------------------------------------
# Part U — query-time domain
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [float("nan"), float("inf"),
                                 float("-inf"), "10", None, True])
def test_invalid_query_time_rejected(bad):
    store = _mem_store({44: _series([10.0], [1], [2])})
    with pytest.raises(SpatialResolutionError):
        resolve_driver(store, 44, bad)


def test_negative_query_time_yields_unavailable_frame():
    store = _mem_store({44: _series([10.0], [1], [2])})
    frame = resolve_frame(store, -5.0, require_geometry=False)
    assert frame.unavailable_count == 1
    assert frame.drivers[0].observation_time_s is None


# ---------------------------------------------------------------------------
# Parts F/G — driver universe + identity join
# ---------------------------------------------------------------------------

def test_observation_only_mode_uses_sorted_drivers():
    store = _mem_store({
        44: _series([10.0], [1], [1]),
        1: _series([10.0], [2], [2]),
    })
    frame = resolve_frame(store, 11.0, require_geometry=False)
    assert [d.driver_number for d in frame.drivers] == [1, 44]


def test_replay_universe_order_preserved_and_missing_unavailable():
    store = _mem_store({44: _series([10.0], [1], [1])})
    universe = (DriverUniverseEntry(driver_number=44,
                                    driver_id="hamilton"),
                DriverUniverseEntry(driver_number=99,
                                    driver_id="ghost"))
    frame = resolve_frame(store, 11.0, universe, require_geometry=False)
    assert [d.driver_id for d in frame.drivers] == ["hamilton", "ghost"]
    assert frame.drivers[0].availability == "FRESH"
    assert frame.drivers[1].availability == "UNAVAILABLE"
    assert frame.drivers[1].observation_time_s is None


def test_universe_accepts_dict_and_pair_forms():
    store = _mem_store({44: _series([10.0], [1], [1])})
    frame = resolve_frame(
        store, 11.0,
        ({"driver_number": 44, "driver_id": "hamilton"}, (99, "ghost")),
        require_geometry=False)
    assert [d.driver_number for d in frame.drivers] == [44, 99]


def test_universe_none_number_resolves_unavailable():
    store = _mem_store({44: _series([10.0], [1], [1])})
    frame = resolve_frame(
        store, 11.0, (DriverUniverseEntry(driver_number=None,
                                          driver_id="zero_state"),),
        require_geometry=False)
    assert frame.drivers[0].availability == "UNAVAILABLE"
    assert frame.drivers[0].driver_number is None


def test_ambiguous_identity_fails_closed():
    store = _mem_store({44: _series([10.0], [1], [1])})
    with pytest.raises(SpatialIdentityError):
        resolve_frame(store, 11.0,
                      (DriverUniverseEntry(44, "hamilton"),
                       DriverUniverseEntry(44, "russell")),
                      require_geometry=False)
    with pytest.raises(SpatialIdentityError):
        resolve_frame(store, 11.0,
                      (DriverUniverseEntry(44, "hamilton"),
                       DriverUniverseEntry(63, "hamilton")),
                      require_geometry=False)


def test_universe_from_race_state_structural():
    class _Entry:
        def __init__(self, driver_id, driver_number):
            self.driver_id = driver_id
            self.driver_number = driver_number

    class _RaceState:
        def __init__(self, drivers):
            self.drivers = drivers

    race_state = _RaceState((_Entry("russell", 63),
                             _Entry("hamilton", 44),
                             _Entry("zero_state", None)))
    universe = universe_from_race_state(race_state)
    assert [(e.driver_number, e.driver_id) for e in universe] == [
        (63, "russell"), (44, "hamilton"), (None, "zero_state")]
    store = _mem_store({44: _series([10.0], [1], [1]),
                        63: _series([10.0], [2], [2])})
    frame = resolve_frame(store, 11.0, universe, require_geometry=False)
    assert [d.driver_id for d in frame.drivers] == ["russell", "hamilton",
                                                   "zero_state"]


def test_frame_coverage_counts():
    store = _mem_store({
        1: _series([100.0], [1], [1]),
        2: _series([100.0], [1], [1]),
        3: _series([100.0], [1], [1]),
    })
    frame = resolve_frame(store, 120.0, require_geometry=False)
    assert (frame.fresh_count, frame.stale_count,
            frame.unavailable_count) == (0, 0, 3)
    frame = resolve_frame(store, 101.0, require_geometry=False)
    assert (frame.fresh_count, frame.stale_count,
            frame.unavailable_count) == (3, 0, 0)


# ---------------------------------------------------------------------------
# Parts X/Y — causal window
# ---------------------------------------------------------------------------

def test_window_returns_exact_causal_samples():
    store = _mem_store({44: _series([10.0, 11.0, 12.0, 13.0],
                                    [1, 2, 3, 4], [5, 6, 7, 8])})
    samples = resolve_window(store, 44, 12.5, 2.5)
    assert [s.observation_time_s for s in samples] == [10.0, 11.0, 12.0]
    assert [(s.raw_x, s.raw_y) for s in samples] == [(1, 5), (2, 6),
                                                    (3, 7)]
    assert all(s.observation_time_s <= 12.5 for s in samples)


def test_window_unknown_or_pre_first_driver_is_empty():
    store = _mem_store({44: _series([10.0], [1], [2])})
    assert resolve_window(store, 99, 12.0, 5.0) == ()
    assert resolve_window(store, 44, 9.0, 5.0) == ()


def test_window_zero_history_only_exact_hits():
    store = _mem_store({44: _series([10.0, 11.0], [1, 2], [3, 4])})
    assert [s.observation_time_s
            for s in resolve_window(store, 44, 11.0, 0.0)] == [11.0]
    assert resolve_window(store, 44, 10.5, 0.0) == ()


def test_window_rejects_bad_args():
    store = _mem_store({44: _series([10.0], [1], [2])})
    with pytest.raises(SpatialResolutionError):
        resolve_window(store, 44, 11.0, -1.0)
    with pytest.raises(SpatialResolutionError):
        resolve_window(store, 44, float("nan"), 1.0)


# ---------------------------------------------------------------------------
# Parts Q/R/S — geometry consistency, missing geometry/observations
# ---------------------------------------------------------------------------

def test_tmp_store_load_roundtrip_resolves_exactly(tmp_path):
    frame = _canonical_frame(RACE, [(44, 10.0, 100, 50),
                                    (44, 11.0, 200, 60),
                                    (1, 10.5, 300, 70)])
    _write_tmp_race(tmp_path, RACE, frame)
    store = RaceSpatialStore.load(tmp_path, RACE)
    assert store.geometry_ok is True
    assert store.observation_status == "COMPLETE"
    state = resolve_driver(store, 44, 10.5)
    assert (state.raw_x, state.raw_y) == (100, 50)
    assert state.render_x is not None
    resolved = resolve_frame(store, 10.5)
    assert [d.driver_number for d in resolved.drivers] == [1, 44]
    assert resolved.geometry_sha256 == store.geometry_sha256


def test_failed_race_is_unsupported(tmp_path):
    manifest = SM.set_race_row(SM.new_manifest(), RACE,
                               status=SM.STATUS_FAILED,
                               reason="synthetic failure")
    save_manifest(manifest, manifest_path(tmp_path))
    with pytest.raises(SpatialArtifactUnavailableError):
        RaceSpatialStore.load(tmp_path, RACE)


def test_missing_geometry_fails_render_frame_only(tmp_path):
    frame = _canonical_frame(RACE, [(44, 10.0, 100, 50)])
    _write_tmp_race(tmp_path, RACE, frame, with_geometry=False)
    store = RaceSpatialStore.load(tmp_path, RACE)
    assert store.geometry_ok is False
    with pytest.raises(SpatialArtifactUnavailableError):
        resolve_frame(store, 10.5, require_geometry=True)
    raw = resolve_frame(store, 10.5, require_geometry=False)
    assert raw.drivers[0].availability == "FRESH"
    assert raw.drivers[0].render_x is None


def test_geometry_source_mismatch_fails_closed(tmp_path):
    frame = _canonical_frame(RACE, [(44, 10.0, 100, 50)])
    _write_tmp_race(tmp_path, RACE, frame,
                    geometry_source_hash="0" * 64)
    store = RaceSpatialStore.load(tmp_path, RACE)
    assert store.geometry_ok is False
    assert store.geometry_stale is True
    with pytest.raises(SpatialGeometryMismatchError):
        resolve_frame(store, 10.5, require_geometry=True)
    driver = resolve_driver(store, 44, 10.5)
    assert (driver.raw_x, driver.raw_y) == (100, 50)
    assert driver.render_x is None


def test_observation_drift_fails_provenance(tmp_path):
    frame = _canonical_frame(RACE, [(44, 10.0, 100, 50)])
    _write_tmp_race(tmp_path, RACE, frame)
    drifted = _canonical_frame(RACE, [(44, 10.0, 101, 50)])
    write_observations_atomic(drifted, artifact_path(tmp_path, RACE))
    with pytest.raises(SpatialProvenanceError):
        RaceSpatialStore.load(tmp_path, RACE)


def test_partial_status_preserved_with_unavailable_gap(tmp_path):
    frame = _canonical_frame(RACE, [(44, 10.0, 100, 50)])
    manifest = SM.new_manifest()
    content = V.logical_content_hash(frame)
    provenance = SM.build_provenance(
        season=2023, race_id=RACE, session="R",
        source_input_ref="synthetic/p12-4", fastf1_version="3.7.0",
        raw_row_count=1, kept_row_count=1, excluded_zero_fix_rows=0,
        excluded_exact_duplicate_rows=0, driver_numbers=[44],
        expected_driver_numbers=[1, 44],
        time_min_s=10.0, time_max_s=10.0,
        observed_source_values=["pos"], observed_status_values=["OnTrack"],
        content_sha256=content)
    manifest = SM.set_race_row(manifest, RACE, status=SM.STATUS_PARTIAL,
                               provenance=provenance,
                               reason="synthetic partial")
    save_manifest(manifest, manifest_path(tmp_path))
    write_observations_atomic(frame, artifact_path(tmp_path, RACE))
    store = RaceSpatialStore.load(tmp_path, RACE)
    assert store.observation_status == "PARTIAL"
    universe = (DriverUniverseEntry(44, "hamilton"),
                DriverUniverseEntry(1, "verstappen"))
    resolved = resolve_frame(store, 11.0, universe,
                             require_geometry=False)
    assert resolved.drivers[0].availability == "FRESH"
    assert resolved.drivers[1].availability == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Parts AA/AK — bounded identity-aware cache
# ---------------------------------------------------------------------------

def test_cache_reuses_store_and_invalidates(tmp_path):
    frame = _canonical_frame(RACE, [(44, 10.0, 100, 50)])
    _write_tmp_race(tmp_path, RACE, frame)
    cache = SpatialStoreCache(max_races=2)
    first = cache.get(tmp_path, RACE)
    assert cache.get(tmp_path, RACE) is first
    assert len(cache) == 1
    assert cache.invalidate(RACE, root=tmp_path) == 1
    assert len(cache) == 0
    assert cache.get(tmp_path, RACE) is not first


def test_cache_evicts_oldest_beyond_bound(tmp_path):
    cache = SpatialStoreCache(max_races=1)
    for race in ("2023-r01-R", "2023-r02-R"):
        frame = _canonical_frame(race, [(44, 10.0, 100, 50)])
        _write_tmp_race(tmp_path, race, frame)
        cache.get(tmp_path, race)
    assert len(cache) == 1


def test_cache_reload_on_identity_change(tmp_path):
    frame = _canonical_frame(RACE, [(44, 10.0, 100, 50)])
    _write_tmp_race(tmp_path, RACE, frame)
    cache = SpatialStoreCache()
    cache.get(tmp_path, RACE)
    drifted = _canonical_frame(RACE, [(44, 10.0, 101, 50)])
    write_observations_atomic(drifted, artifact_path(tmp_path, RACE))
    # Manifest still pins the old identity: reload detects drift instead
    # of serving the stale index.
    with pytest.raises(SpatialProvenanceError):
        cache.get(tmp_path, RACE)


# ---------------------------------------------------------------------------
# Parts M/AL — retirement separation, 2025 data-vs-serving
# ---------------------------------------------------------------------------

def test_offtrack_status_does_not_change_age_math():
    store = _mem_store({44: _series([100.0], [100], [50],
                                    status="OffTrack")})
    fresh = resolve_driver(store, 44, 102.0)
    assert fresh.availability == "FRESH"
    assert fresh.status == "OffTrack"
    retired = resolve_driver(store, 44, 200.0)
    assert retired.availability == "UNAVAILABLE"  # age math only


def test_2025_data_resolvable_but_not_product_servable():
    store = _mem_store({44: _series([10.0], [1], [2])},
                       race_id="2025-r01-R")
    assert resolve_driver(store, 44, 11.0).availability == "FRESH"
    assert SC.is_data_ingestible(2025) is True
    assert SC.is_product_servable(2025) is False
    from api import v2_service as VS

    assert tuple(VS.SERVED_SEASONS) == tuple(range(2018, 2025))


def test_resolver_imports_stay_outside_predictive_firewall():
    text = (ROOT / "raceintel" / "spatial" / "resolver.py").read_text()
    for token in ("raceintel.features", "raceintel.labels",
                  "raceintel.model_lab", "raceintel.simulation",
                  "raceintel.strategy", "raceintel.explainability",
                  "raceintel.serving", "raceintel.prediction", "fastapi",
                  "starlette", "from api", "import api"):
        assert token not in text, f"firewall breach: {token}"


# ---------------------------------------------------------------------------
# Misc contract checks
# ---------------------------------------------------------------------------

def test_require_query_time_domain():
    assert require_query_time(10) == 10.0
    assert require_query_time(-3.5) == -3.5
    for bad in (float("nan"), float("inf"), "x", None, True):
        with pytest.raises(SpatialResolutionError):
            require_query_time(bad)


def test_resolve_driver_rejects_non_integral_number():
    store = _mem_store({44: _series([10.0], [1], [2])})
    with pytest.raises(SpatialResolutionError):
        resolve_driver(store, 44.5, 11.0)
    with pytest.raises(SpatialResolutionError):
        resolve_driver(store, "44", 11.0)


def test_frame_contract_version_pinned():
    store = _mem_store({44: _series([10.0], [1], [2])})
    frame = resolve_frame(store, 11.0, require_geometry=False)
    assert frame.resolver_contract_version == "spatial-resolver-v1"
    assert frame.observation_content_sha256 == "a" * 64
