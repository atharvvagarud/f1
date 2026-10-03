"""Phase-12 circuit geometry extraction (P12-3).

Deterministic 2D circuit geometry derived from canonical P12-2
position observations: eligible-observation selection, reference-lap
ordering backbone, phase-binned robust centerline, optional pit-lane
branch from Tier-A pit windows, smoothing of DERIVED geometry only,
aspect-preserving normalized render transform, validation, content
identity, and geometry-manifest rows with source linkage.

Evidence basis (empirical study on Bahrain 2023, Monaco 2021, Japan
2024, Australia 2023, Italy 2023, Belgium 2021):
- FastF1 position units are integral decimetres (~0.1 m/unit;
  lap-length match), NOT metres. Geometry is scale-agnostic; the
  contract keeps raw int64 units and records a uniform scale.
- 25-90% of samples are stationary repeats (garage/grid/red-flag/
  freeze tails): excluded by a motion rule, never coordinate boxes.
- Teleport spikes (up to ~16 km) break segments; feed gaps (up to
  ~3.8 s, ~340 m at speed) are legitimate and kept.
- A per-driver reference lap (consecutive anchor passes, shortest
  qualifying window) orders the loop; time-ordered phase binning
  survives the Suzuka crossover, which pure spatial clustering
  cannot. Heading-gated assignment separates parallel arms.
- Per-bin medians resist off-track excursions and pit-lane
  minorities; pit windows from Tier-A pit_in_s/out_s trace a clean
  separable branch (PIT_GEOMETRY_SUPPORTED where evidenced).

No temporal driver resolution, no API, no frontend, no predictive
imports. Canonical P12-2 observation artifacts are never modified.
"""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pandas as pd

from raceintel.spatial import contracts as SC
from raceintel.spatial.errors import (
    SpatialContractError,
    SpatialProvenanceError,
)

#: Geometry implementation version (provenance metadata; the
#: scientific identity stays the logical content hash).
GEOMETRY_ALGORITHM_VERSION = "p12-3-v1"

#: Geometry manifest schema version (dedicated manifest, never mixed
#: into the P12-2 observation manifest).
GEOMETRY_MANIFEST_SCHEMA_VERSION = "spatial-geometry-manifest-v1"

GEOMETRY_STATUS_COMPLETE = "COMPLETE"
GEOMETRY_STATUS_FAILED = "FAILED"
GEOMETRY_STATUS_SKIPPED = "SKIPPED"
GEOMETRY_STATUSES = frozenset({
    GEOMETRY_STATUS_COMPLETE, GEOMETRY_STATUS_FAILED,
    GEOMETRY_STATUS_SKIPPED,
})

PIT_SUPPORTED = "PIT_GEOMETRY_SUPPORTED"
PIT_DEFERRED = "PIT_GEOMETRY_DEFERRED"

# ---------------------------------------------------------------------------
# Evidence-derived extraction parameters (raw integer units ~= decimetres)
# ---------------------------------------------------------------------------

#: Moving iff consecutive-sample step exceeds this (0.2 m kills garage/
#: grid/freeze repeats; safety-car crawl at ~30 m/s passes easily).
MOVE_MIN_U = 2.0

#: Teleport threshold: beyond any legitimate gap (3.8 s observed max
#: gap at ~95 m/s ~= 3600 u). Breaks segments, drops adjacent points.
SPIKE_MAX_U = 5000.0

#: Reference backbone must be gap-free (150 m at racing speed covers
#: the observed ~1 s feed gaps; teleports and shortcut jumps are far
#: larger and additionally caught by the anchor-support check below).
REF_SPIKE_MAX_U = 1500.0

#: Minimum share of reference anchors supported by eligible points
#: (a shortcut chord crosses empty regions and fails this).
ANCHOR_SUPPORT_FRAC = 0.97

#: Nearby-point radius / count for anchor support.
ANCHOR_SUPPORT_R_U = 150.0
ANCHOR_SUPPORT_MIN_PTS = 3

#: Anchor search radius around the densest 100-unit grid cell.
ANCHOR_R_U = 100.0

#: Assignment search radius (covers track width + line spread).
SEARCH_R_U = 300.0

#: Heading agreement for phase assignment (separates parallel arms
#: running opposite directions, e.g. Monaco harbour).
HEAD_COS_MIN = 0.2

#: Single-lap duration bounds (F1 laps ~70-110 s; SC/formation margin).
MIN_LAP_S, MAX_LAP_S = 60.0, 300.0

#: Single-lap path bounds in raw units (Monaco ~33k, Spa ~70k).
MIN_LAP_U, MAX_LAP_U = 20000.0, 90000.0

#: Fine phase bins for the robust centerline (pre-simplification).
K_ANCHOR = 2048

#: Per-bin outlier trim radius (15 m keeps racing-line spread, drops
#: pit-lane/off-track minorities that survive the median).
TRIM_R_U = 150.0

#: Savitzky-Golay smoothing of derived centerline (closed loop).
SMOOTH_WINDOW, SMOOTH_POLY = 41, 3

#: Render points (resolution study: 512 keeps max deviation < 1.5 m;
#: 256 does not on all circuits).
N_RENDER = 512

#: ViewBox padding fraction per side (stored; renderer needs nothing).
RENDER_PAD = 0.03

#: Pit window margin around pit_in_s/out_s (seconds).
PIT_WINDOW_MARGIN_S = 8.0

#: Pit phase bins across normalized stop time.
PIT_PHASE_BINS = 64

#: Minimum non-empty pit windows for a supported branch.
PIT_MIN_WINDOWS = 3

#: Entry/exit connection tolerance to the main trace (30 m).
PIT_CONNECT_MAX_U = 300.0


class GeometryError(SpatialContractError):
    """Geometry extraction/validation failure (fail-closed per race)."""


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def add_motion(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-driver consecutive step (raw units) + heading unit vectors."""
    work = frame.sort_values(
        ["driver_number", "observation_time_s"]).reset_index(drop=True)
    xy = work[["x", "y"]].to_numpy().astype(float)
    step = np.full(len(work), np.nan)
    for _drv, idx in work.groupby("driver_number").groups.items():
        pos = work.index.get_indexer_for(idx)
        step[pos[1:]] = np.hypot(*np.diff(xy[pos], axis=0).T)
    work = work.assign(step=step)
    heading = np.full((len(work), 2), np.nan)
    for _drv, idx in work.groupby("driver_number").groups.items():
        pos = work.index.get_indexer_for(idx)
        d = np.diff(xy[pos], axis=0)
        n = np.hypot(d[:, 0], d[:, 1])
        ok = n > 1e-9
        heading[pos[1:][ok]] = (d[ok].T / n[ok]).T
    work[["hx", "hy"]] = heading
    return work


def select_eligible(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Moving, non-spike observations eligible for geometry.

    Stationary clusters (garage/grid/red-flag/freeze) drop out by the
    motion rule; teleports break segments. No coordinate boxes, no
    lap/outcome labels.
    """
    work = add_motion(frame)
    step = work.step.to_numpy()
    moving = (step > MOVE_MIN_U) & (step <= SPIKE_MAX_U)
    # points adjacent to a spike are untrustworthy (landing side unknown)
    spike = np.zeros(len(work), dtype=bool)
    for _drv, idx in work.groupby("driver_number").groups.items():
        pos = work.index.get_indexer_for(idx)
        bad = np.where(~np.isfinite(step[pos])
                       | (step[pos] > SPIKE_MAX_U))[0]
        for b in bad:
            spike[pos[max(0, b - 1):b + 2]] = True
    eligible = work.loc[moving & ~spike].reset_index(drop=True)
    stats = {
        "source_rows": int(len(frame)),
        "eligible_rows": int(len(eligible)),
        "excluded_stationary": int(
            ((step <= MOVE_MIN_U) & np.isfinite(step)).sum()),
        "excluded_spikes": int(
            ((step > SPIKE_MAX_U) & np.isfinite(step)).sum()
            + int(np.isfinite(step).sum() - moving.sum()
                  - ((step <= MOVE_MIN_U)
                     & np.isfinite(step)).sum())),
    }
    return eligible, stats


# ---------------------------------------------------------------------------
# Reference lap
# ---------------------------------------------------------------------------

def _anchor_point(eligible: pd.DataFrame) -> np.ndarray:
    """Center of the densest 100-unit grid cell (lap-periodic region)."""
    if eligible.empty:
        raise GeometryError("no eligible observations for anchor search")
    P = eligible[["x", "y"]].to_numpy().astype(float)
    grid = np.floor(P / 100.0).astype(int)
    cells, counts = np.unique(grid, axis=0, return_counts=True)
    return (cells[np.argmax(counts)].astype(float) + 0.5) * 100.0


def anchor_support_frac(trace: np.ndarray, P: np.ndarray,
                          k: int = 512) -> float:
    """Share of resampled trace anchors near eligible observations.

    A shortcut/teleport chord crosses empty regions and scores low;
    a data-faithful loop scores ~1. Deterministic.
    """
    anchors, _ = resample_arc(trace, k)
    d2 = ((P[:, None, :] - anchors[None, :, :]) ** 2).sum(-1)
    supported = (d2 < ANCHOR_SUPPORT_R_U ** 2).sum(0) \
        >= ANCHOR_SUPPORT_MIN_PTS
    return float(supported.mean())


def find_reference_lap(frame: pd.DataFrame,
                       eligible: pd.DataFrame) -> dict:
    """Shortest qualifying window between consecutive anchor passes.

    Anchor passes segment every lap by construction; the shortest
    qualifying window is the cleanest single lap (pit/formation/SC
    windows are strictly longer). Deterministic tie-break on
    (path, driver_number, start time). Fail closed with a reason.
    """
    anchor = _anchor_point(eligible)
    order = frame.groupby("driver_number").size().sort_values(
        ascending=False).index.tolist()
    cands = []
    for drv in order:
        h = frame[frame.driver_number == drv].reset_index(drop=True)
        h = add_motion(h)
        hx = h[["x", "y"]].to_numpy().astype(float)
        ht = h.observation_time_s.to_numpy()
        near = np.hypot(*(hx - anchor).T) < ANCHOR_R_U
        passes = []
        k = 0
        while k < len(h):
            if near[k]:
                k2 = k
                while k2 + 1 < len(h) and near[k2 + 1]:
                    k2 += 1
                passes.append((k, k2))
                k = k2 + 1
            else:
                k += 1
        for (i0, _i1), (j0, j1) in zip(passes, passes[1:]):
            dt = float(ht[j0] - ht[i0])
            if not (MIN_LAP_S <= dt <= MAX_LAP_S):
                continue
            s = h.step.to_numpy()[i0:j1 + 1][1:]
            if len(s) == 0 or np.isnan(s).any():
                continue
            if s.max() > REF_SPIKE_MAX_U:
                continue
            path = float(s.sum())
            if not (MIN_LAP_U <= path <= MAX_LAP_U):
                continue
            cands.append((path, int(drv), float(ht[i0]), float(ht[j1]),
                          i0, j1, dt, len(passes)))
    if not cands:
        raise GeometryError(
            "no qualifying reference lap (anchor passes found but no "
            "gap-free single-lap window in duration/path bounds)")
    cands.sort(key=lambda c: (c[0], c[1], c[2]))
    P = eligible[["x", "y"]].to_numpy().astype(float)
    for path, drv, t0, t1, i0, j1, dt, npass in cands:
        h = frame[frame.driver_number == drv].reset_index(drop=True)
        trace = h[["x", "y"]].to_numpy().astype(float)[i0:j1 + 1]
        support = anchor_support_frac(trace, P)
        if support < ANCHOR_SUPPORT_FRAC:
            continue  # shortcut/teleport chord: unsupported region
        return {
            "driver_number": drv,
            "start_time_s": t0,
            "end_time_s": t1,
            "duration_s": dt,
            "path_units": path,
            "anchor_passes": npass,
            "anchor": [float(anchor[0]), float(anchor[1])],
            "anchor_support_frac": support,
            "trace": trace,
        }
    raise GeometryError(
        "no supported reference lap (candidate windows cross "
        "regions without eligible observations)")


# ---------------------------------------------------------------------------
# Centerline
# ---------------------------------------------------------------------------

def resample_arc(xy: np.ndarray, k: int) -> tuple[np.ndarray, float]:
    """Arc-length-uniform resampling of a closed loop (cyclic closure)."""
    seg = np.hypot(*np.diff(np.vstack([xy, xy[:1]]), axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    targets = np.linspace(0.0, cum[-1], k, endpoint=False)
    xs = np.interp(targets, cum,
                   np.concatenate([xy[:, 0], xy[:1, 0]]))
    ys = np.interp(targets, cum,
                   np.concatenate([xy[:, 1], xy[:1, 1]]))
    return np.stack([xs, ys], 1), float(cum[-1])


def resample_open(xy: np.ndarray, k: int) -> np.ndarray:
    """Arc-length-uniform resampling of an OPEN path (no closure)."""
    seg = np.hypot(*np.diff(xy, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    if not np.isfinite(cum[-1]) or cum[-1] <= 0:
        raise GeometryError("degenerate open path")
    targets = np.linspace(0.0, cum[-1], k)
    return np.stack([np.interp(targets, cum, xy[:, 0]),
                     np.interp(targets, cum, xy[:, 1])], 1)


def _tangents(anchors: np.ndarray) -> np.ndarray:
    tan = np.diff(np.vstack([anchors, anchors[:1]]), axis=0)
    n = np.hypot(tan[:, 0], tan[:, 1])
    return tan / np.maximum(n[:, None], 1e-9)


def assign_bins(P: np.ndarray, H: np.ndarray,
                anchors: np.ndarray) -> np.ndarray:
    """Nearest anchor with heading agreement (fallback: nearest).

    Direction-aware assignment keeps parallel opposite arms (pit
    straight vs pit lane, harbour arms, crossover passes) on their
    own phase.
    """
    tan = _tangents(anchors)
    lab = np.full(len(P), -1)
    for a in range(0, len(P), 20000):
        Pb, Hb = P[a:a + 20000], H[a:a + 20000]
        d2 = ((Pb[:, None, :] - anchors[None, :, :]) ** 2).sum(-1)
        near = d2 < SEARCH_R_U ** 2
        gated = near & (Hb @ tan.T > HEAD_COS_MIN)
        has = gated.any(1)
        sub = np.where(has)[0]
        masked = np.where(gated[sub], d2[sub], np.inf)
        finite = np.isfinite(masked.min(1))
        lab[a:a + 20000][sub[finite]] = masked[finite].argmin(1)
        rest = np.concatenate([np.where(~has)[0], sub[~finite]])
        lab[a:a + 20000][rest] = d2[rest].argmin(1)
    return lab


def bin_centerline(P: np.ndarray, labels: np.ndarray,
                   k: int) -> tuple[np.ndarray, np.ndarray]:
    """Robust per-bin median with trim recomputation."""
    cx = np.full(k, np.nan)
    cy = np.full(k, np.nan)
    cov = np.zeros(k, dtype=int)
    for b in range(k):
        sel = P[labels == b]
        cov[b] = len(sel)
        if not len(sel):
            continue
        med = np.median(sel, axis=0)
        keep = sel[np.hypot(*(sel - med).T) <= TRIM_R_U]
        if len(keep):
            med = np.median(keep, axis=0)
        cx[b], cy[b] = med
    return np.stack([cx, cy], 1), cov


def interpolate_closed(xy: np.ndarray) -> np.ndarray:
    """Cyclic linear interpolation over empty (NaN) bins."""
    out = xy.copy()
    n = len(out)
    bad = np.isnan(out[:, 0]) | np.isnan(out[:, 1])
    if bad.all():
        raise GeometryError("centerline has no populated bins")
    if not bad.any():
        return out
    good = np.where(~bad)[0]
    for b in np.where(bad)[0]:
        nxt = good[good > b]
        nxt = nxt[0] if len(nxt) else good[0] + n
        prv = good[good < b]
        prv = prv[-1] if len(prv) else good[-1] - n
        frac = (b - prv) / (nxt - prv)
        out[b] = (1 - frac) * out[prv % n] + frac * out[nxt % n]
    return out


def smooth_closed(xy: np.ndarray) -> np.ndarray:
    """Savitzky-Golay smoothing on the closed loop (derived geometry)."""
    from scipy.signal import savgol_filter

    n = len(xy)
    window = min(SMOOTH_WINDOW, n - (1 - n % 2))
    if window < 5:
        return xy.copy()
    sx = savgol_filter(xy[:, 0], window, SMOOTH_POLY, mode="wrap")
    sy = savgol_filter(xy[:, 1], window, SMOOTH_POLY, mode="wrap")
    return np.stack([sx, sy], 1)


def extract_main_trace(frame: pd.DataFrame) -> tuple[dict, dict]:
    """Reference lap -> phase bins -> robust medians -> smoothed loop."""
    eligible, stats = select_eligible(frame)
    if eligible.empty:
        raise GeometryError("no eligible observations after selection")
    ref = find_reference_lap(frame, eligible)
    anchors, _loop = resample_arc(ref["trace"], K_ANCHOR)
    P = eligible[["x", "y"]].to_numpy().astype(float)
    H = eligible[["hx", "hy"]].to_numpy().astype(float)
    H[~np.isfinite(H)] = 0.0
    labels = assign_bins(P, H, anchors)
    medians, coverage = bin_centerline(P, labels, K_ANCHOR)
    empty_bins = int(np.isnan(medians[:, 0]).sum())
    filled = interpolate_closed(medians)
    # simplification error of the raw medians vs smoothed (diagnostic)
    smooth = smooth_closed(filled)
    disp = float(np.hypot(*(smooth - filled).T).max())
    center, _plen = resample_arc(smooth, N_RENDER)
    trace = {
        "raw_centerline": center,
        "reference": ref,
        "anchor_bins": K_ANCHOR,
        "empty_bins": empty_bins,
        "smooth_displacement_u": disp,
    }
    info = {**stats, "empty_bins": empty_bins,
            "smooth_displacement_u": disp}
    return trace, info


# ---------------------------------------------------------------------------
# Pit lane
# ---------------------------------------------------------------------------

def _tiera_table(season: int, entity: str, race_id: str,
                 data_root) -> pd.DataFrame | None:
    """Read one Tier-A processed table (historical fact, pit windows)."""
    from pathlib import Path

    if data_root is None:
        return None
    path = (Path(data_root) / "data" / "v2" / "processed" / entity
            / f"season={season}" / f"{entity}__{race_id}.parquet")
    if not path.is_file():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def collect_pit_windows(race_id: str, frame: pd.DataFrame,
                        data_root) -> tuple[list[np.ndarray], dict]:
    """Window position streams by Tier-A pit_in_s/out_s (documented use).

    Returns per-stop time-ordered paths plus window statistics. Empty
    windows (stop outside observation range) are tolerated; missing
    Tier-A tables defer the branch without failing geometry.
    """
    season = int(race_id[:4])
    stops = _tiera_table(season, "pit_stops", race_id, data_root)
    results = _tiera_table(season, "results", race_id, data_root)
    if stops is None or results is None or stops.empty:
        return [], {"windows": 0, "empty_windows": 0, "note": "no Tier-A "
                    "pit/result tables; pit branch deferred"}
    did2num = dict(zip(results["driver_id"].astype(str),
                       results["driver_number"].astype(int)))
    paths: list[np.ndarray] = []
    empty = 0
    for _, s in stops.iterrows():
        drv = did2num.get(str(s["driver_id"]))
        if drv is None:
            empty += 1
            continue
        try:
            lo = float(s["pit_in_s"]) - PIT_WINDOW_MARGIN_S
            hi = float(s["pit_out_s"]) + PIT_WINDOW_MARGIN_S
        except (TypeError, ValueError):
            empty += 1
            continue
        if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
            empty += 1
            continue
        h = frame[(frame.driver_number == drv)
                  & (frame.observation_time_s >= lo)
                  & (frame.observation_time_s <= hi)]
        h = h.sort_values("observation_time_s")
        if len(h) < 8:
            empty += 1
            continue
        pts = h[["x", "y"]].to_numpy().astype(float)
        # The pit branch describes lane traversal: keep moving samples
        # only. Rationale: pit boxes sit under GPS-denying structures;
        # the feed parks on one fallback cell per race while boxed
        # (observed: identical freeze cell across all stops of a race)
        # and teleports on reacquire. Frozen repeats are box/fallback
        # dwells (a render point, not a path) and would drag the
        # phase-normalized median off the lane.
        jumps = np.hypot(*np.diff(pts, axis=0).T)
        keep = np.ones(len(pts), dtype=bool)
        keep[1:][jumps <= MOVE_MIN_U] = False
        keep[:-1][jumps <= MOVE_MIN_U] = False
        bad = np.zeros(len(pts), dtype=bool)
        bad[1:][jumps > SPIKE_MAX_U] = True
        bad[:-1][jumps > SPIKE_MAX_U] = True
        pts = pts[keep & ~bad]
        if len(pts) < 8:
            empty += 1
            continue
        paths.append(pts)
    return paths, {"windows": len(paths), "empty_windows": empty,
                   "total_stops": int(len(stops))}


def pit_centerline(paths: list[np.ndarray],
                   main_render_raw: np.ndarray) -> tuple[dict | None, dict]:
    """Median pit path across normalized stop phases + connections.

    Evidence-gated: too few windows, bad entry/exit connections, or
    degenerate length defer the branch (returned None + reason) while
    main geometry stays COMPLETE.
    """
    info = {"windows": len(paths)}
    if len(paths) < PIT_MIN_WINDOWS:
        return None, {**info, "pit_status": PIT_DEFERRED,
                      "reason": f"only {len(paths)} non-empty pit "
                      f"windows (< {PIT_MIN_WINDOWS})"}
    # normalize each stop to phase 0..1 by index, median per phase bin
    stacked = []
    for p in paths:
        idx = np.linspace(0, len(p) - 1, PIT_PHASE_BINS).astype(int)
        stacked.append(p[idx])
    stacked = np.array(stacked)
    med = np.median(stacked, axis=0)
    # entry/exit connections to main trace (raw units, shared space)
    d_entry = np.hypot(*(main_render_raw - med[0]).T).min()
    d_exit = np.hypot(*(main_render_raw - med[-1]).T).min()
    entry_ix = int(np.hypot(*(main_render_raw - med[0]).T).argmin())
    exit_ix = int(np.hypot(*(main_render_raw - med[-1]).T).argmin())
    plen = float(np.hypot(*np.diff(med, axis=0).T).sum())
    info.update({
        "entry_distance_u": float(d_entry),
        "exit_distance_u": float(d_exit),
        "entry_main_index": entry_ix,
        "exit_main_index": exit_ix,
        "path_length_u": plen,
    })
    if max(d_entry, d_exit) > PIT_CONNECT_MAX_U:
        return None, {**info, "pit_status": PIT_DEFERRED,
                      "reason": "pit path endpoints do not connect to "
                      f"the main trace ({d_entry:.0f}u/{d_exit:.0f}u)"}
    if plen < 500.0:
        return None, {**info, "pit_status": PIT_DEFERRED,
                      "reason": f"degenerate pit path ({plen:.0f}u)"}
    pit = resample_open(med, 128)
    return {"raw_path": pit, **info, "pit_status": PIT_SUPPORTED}, \
        {**info, "pit_status": PIT_SUPPORTED}


# ---------------------------------------------------------------------------
# Transform (Parts N-Q)
# ---------------------------------------------------------------------------

def compute_transform(raw_main: np.ndarray,
                      raw_pit: np.ndarray | None = None) -> dict:
    """Aspect-preserving raw -> normalized render (SVG-ready, y-down).

    Single uniform scale (never independent X/Y scaling); source
    orientation preserved (rotation 0, no aesthetic rotation); y grows
    downward so render points need no client-side flip. All numbers
    stored: future driver coordinates reuse exactly this transform.
    """
    pts = raw_main if raw_pit is None else np.vstack([raw_main, raw_pit])
    x0, y0 = float(pts[:, 0].min()), float(pts[:, 1].min())
    x1, y1 = float(pts[:, 0].max()), float(pts[:, 1].max())
    span = max(x1 - x0, y1 - y0)
    if not (np.isfinite(span) and span > 0):
        raise GeometryError("degenerate geometry bounds")
    scale = (1.0 - 2.0 * RENDER_PAD) / span
    ox = RENDER_PAD + (span - (x1 - x0)) / 2.0 * scale - x0 * scale
    oy = RENDER_PAD + (span - (y1 - y0)) / 2.0 * scale + y1 * scale
    return {
        "scale": scale,
        "offset_u": ox,
        "offset_v": oy,
        "rotation_deg": 0.0,
        "y_down": True,
        "pad": RENDER_PAD,
        "raw_bounds": {"x_min": x0, "y_min": y0, "x_max": x1,
                       "y_max": y1},
        "render_bounds": {"u_min": 0.0, "v_min": 0.0, "u_max": 1.0,
                          "v_max": 1.0},
    }


def apply_transform(raw: np.ndarray, transform: dict) -> np.ndarray:
    """Raw (x, y) -> render (u, v) with the stored artifact transform."""
    s, ox, oy = (transform["scale"], transform["offset_u"],
                 transform["offset_v"])
    out = np.empty_like(raw, dtype=float)
    out[:, 0] = ox + s * raw[:, 0]
    out[:, 1] = oy - s * raw[:, 1]
    return out


def invert_transform(render: np.ndarray, transform: dict) -> np.ndarray:
    """Render (u, v) -> raw (x, y); kept for validation/debugging."""
    s, ox, oy = (transform["scale"], transform["offset_u"],
                 transform["offset_v"])
    out = np.empty_like(render, dtype=float)
    out[:, 0] = (render[:, 0] - ox) / s
    out[:, 1] = (oy - render[:, 1]) / s
    return out


# ---------------------------------------------------------------------------
# Assembly / validation / identity
# ---------------------------------------------------------------------------

def _point_list(xy: np.ndarray) -> list[list[float]]:
    return [[float(v[0]), float(v[1])] for v in xy]


def build_geometry(race_id: str, frame: pd.DataFrame,
                   data_root=None) -> dict:
    """Derive the full geometry record for one race (fail-closed)."""
    season = int(race_id[:4])
    trace, info = extract_main_trace(frame)
    raw_main = trace["raw_centerline"]
    paths, pit_windows = collect_pit_windows(race_id, frame, data_root)
    pit, pit_info = pit_centerline(paths, raw_main)
    raw_pit = pit["raw_path"] if pit is not None else None
    transform = compute_transform(raw_main, raw_pit)
    render_main = apply_transform(raw_main, transform)
    record: dict = {
        "schema_version": SC.SPATIAL_GEOMETRY_SCHEMA_VERSION,
        "race_id": race_id,
        "season": season,
        "layout_scope": "per-race",
        "algorithm_version": GEOMETRY_ALGORITHM_VERSION,
        "source": {
            "observation_content_sha256": None,  # filled by caller
            "source_rows": info["source_rows"],
            "eligible_rows": info["eligible_rows"],
            "excluded_stationary": info["excluded_stationary"],
            "excluded_spikes": info["excluded_spikes"],
            "empty_anchor_bins": info["empty_bins"],
            "smooth_displacement_u": info["smooth_displacement_u"],
            "reference_driver_number": trace["reference"]["driver_number"],
            "reference_start_s": trace["reference"]["start_time_s"],
            "reference_end_s": trace["reference"]["end_time_s"],
            "reference_path_u": trace["reference"]["path_units"],
            "reference_anchor_support_frac": trace["reference"].get(
                "anchor_support_frac", float("nan")),
        },
        "main_track": {
            "points": _point_list(render_main),
            "raw_points": _point_list(raw_main),
            "n_points": int(len(render_main)),
            "closed_loop": True,
            "length_u": float(
                np.hypot(*np.diff(np.vstack(
                    [raw_main, raw_main[:1]]), axis=0).T).sum()),
        },
        "pit_lane": None if pit is None else {
            "points": _point_list(apply_transform(raw_pit, transform)),
            "raw_points": _point_list(raw_pit),
            "n_points": int(len(raw_pit)),
            "entry_main_index": pit_info["entry_main_index"],
            "exit_main_index": pit_info["exit_main_index"],
            "entry_distance_u": pit_info["entry_distance_u"],
            "exit_distance_u": pit_info["exit_distance_u"],
            "path_length_u": pit_info["path_length_u"],
        },
        "pit_status": pit_info["pit_status"],
        "transform": transform,
        "quality": {},
        "content_sha256": "",
    }
    if pit is None:
        record["pit_defer_reason"] = pit_info.get("reason", "")
    record["quality"] = quality_metrics(record, frame)
    record["content_sha256"] = geometry_content_hash(record)
    validate_geometry(record)
    return record


def quality_metrics(record: dict, frame: pd.DataFrame) -> dict:
    """Detection-oriented metrics only (no composite score, no ranking)."""
    raw_main = np.array(record["main_track"]["raw_points"])
    P = frame[["x", "y"]].to_numpy().astype(float)
    d2 = ((P[:, None, :] - raw_main[None, :, :]) ** 2).sum(-1)
    nearest = np.sqrt(d2.min(1))
    segs = np.hypot(*np.diff(np.vstack(
        [raw_main, raw_main[:1]]), axis=0).T)
    full = resample_arc(raw_main, K_ANCHOR)[0]
    simp = resample_arc(raw_main, N_RENDER)[0]
    # simplification error: full-trace vs render resolution
    d2s = ((full[:, None, :] - simp[None, :, :]) ** 2).sum(-1)
    return {
        "source_to_centerline_median_u": float(np.median(nearest)),
        "source_to_centerline_p95_u": float(np.quantile(nearest, 0.95)),
        "closure_u": float(segs[-1]),
        "closure_over_median_segment": float(
            segs[-1] / max(np.median(segs[:-1]), 1e-9)),
        "segment_median_u": float(np.median(segs[:-1])),
        "segment_max_u": float(segs[:-1].max()),
        "simplification_error_u": float(np.sqrt(d2s.min(1)).max()),
        "point_reduction_ratio": float(
            len(P) / max(len(raw_main), 1)),
    }


def geometry_content_hash(record: dict) -> str:
    """Logical identity over canonical values (not file bytes)."""
    payload = {
        "schema_version": record["schema_version"],
        "race_id": record["race_id"],
        "algorithm_version": record["algorithm_version"],
        "source_content": record["source"][
            "observation_content_sha256"],
        "main_track": record["main_track"]["points"],
        "pit_lane": (record["pit_lane"]["points"]
                     if record["pit_lane"] is not None else None),
        "transform": {k: record["transform"][k] for k in
                      ("scale", "offset_u", "offset_v", "rotation_deg",
                       "y_down", "pad")},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_geometry(record: object) -> dict:
    """Fail-closed geometry validation; returns a metrics report."""
    if not isinstance(record, dict):
        raise GeometryError("geometry record must be a mapping")
    if record.get("schema_version") != SC.SPATIAL_GEOMETRY_SCHEMA_VERSION:
        raise GeometryError("unsupported geometry schema_version")
    for key in ("race_id", "algorithm_version"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise GeometryError(f"geometry {key} must be non-empty")
    main = record.get("main_track")
    if not isinstance(main, dict) or not main.get("closed_loop", False):
        raise GeometryError("main_track must be a closed loop")
    raw = np.array(main.get("raw_points", []), dtype=float)
    rendered = np.array(main.get("points", []), dtype=float)
    if raw.shape != rendered.shape or raw.ndim != 2 or raw.shape[1] != 2:
        raise GeometryError("main_track raw/render points must match Nx2")
    if len(raw) < 64:
        raise GeometryError("main_track needs >= 64 points for rendering")
    if not (np.isfinite(raw).all() and np.isfinite(rendered).all()):
        raise GeometryError("geometry points must be finite")
    transform = record.get("transform")
    for key in ("scale", "offset_u", "offset_v"):
        value = transform.get(key) if isinstance(transform, dict) else None
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise GeometryError(f"transform {key} must be finite")
    if not transform["scale"] > 0:
        raise GeometryError("transform scale must be positive")
    if transform.get("rotation_deg", 0.0) != 0.0:
        raise GeometryError("non-zero rotation must be explicit (P12-3 "
                            "preserves source orientation)")
    # transform consistency: raw -> render must reproduce stored points
    recomputed = apply_transform(raw, transform)
    if not np.allclose(recomputed, rendered, rtol=0, atol=1e-9):
        raise GeometryError("stored render points do not match the "
                            "stored transform (one transform per artifact)")
    if not ((rendered >= -1e-9).all() and (rendered <= 1 + 1e-9).all()):
        raise GeometryError("render points leave the declared [0,1] "
                            "render space")
    # closure sanity: closing segment vs normal segments
    segs = np.hypot(*np.diff(np.vstack([raw, raw[:1]]), axis=0).T)
    if segs[-1] > 5 * max(np.median(segs[:-1]), 1e-9):
        raise GeometryError(
            f"closure segment {segs[-1]:.1f}u dwarfs normal segments "
            f"(median {np.median(segs[:-1]):.1f}u)")
    if (segs[:-1] <= 0).any():
        raise GeometryError("degenerate zero-length segments present")
    # pit branch consistency (when supported)
    pit = record.get("pit_lane")
    if record.get("pit_status") == PIT_SUPPORTED and pit is None:
        raise GeometryError("pit supported but no pit_lane payload")
    if record.get("pit_status") == PIT_DEFERRED and pit is not None:
        raise GeometryError("pit deferred but pit_lane payload present")
    if pit is not None:
        praw = np.array(pit["raw_points"], dtype=float)
        pren = np.array(pit["points"], dtype=float)
        if praw.shape != pren.shape or praw.shape[1] != 2:
            raise GeometryError("pit raw/render points must match Nx2")
        if not (np.isfinite(praw).all() and np.isfinite(pren).all()):
            raise GeometryError("pit points must be finite")
        if not np.allclose(apply_transform(praw, transform), pren,
                           rtol=0, atol=1e-9):
            raise GeometryError("pit render points do not match transform")
        pseg = np.hypot(*np.diff(praw, axis=0).T)
        if (pseg <= 0).any():
            raise GeometryError("degenerate pit segments present")
    # identity reproducibility
    if record.get("content_sha256") != geometry_content_hash(record):
        raise GeometryError("geometry content hash does not reproduce")
    quality = record.get("quality", {})
    return {
        "race_id": record["race_id"],
        "n_points": int(len(raw)),
        "pit_status": record.get("pit_status"),
        "closure_u": float(segs[-1]),
        "segment_median_u": float(np.median(segs[:-1])),
        "simplification_error_u": float(
            quality.get("simplification_error_u", float("nan"))),
    }


# ---------------------------------------------------------------------------
# Geometry manifest (dedicated; source-linked for staleness)
# ---------------------------------------------------------------------------

def new_geometry_manifest() -> dict:
    return {
        "manifest_schema_version": GEOMETRY_MANIFEST_SCHEMA_VERSION,
        "geometry_schema_version": SC.SPATIAL_GEOMETRY_SCHEMA_VERSION,
        "algorithm_version": GEOMETRY_ALGORITHM_VERSION,
        "races": {},
    }


def set_geometry_row(manifest: dict, race_id: str, *, status: str,
                     source_content_sha256: str | None = None,
                     geometry_sha256: str | None = None,
                     n_points: int | None = None,
                     pit_status: str | None = None,
                     reason: str | None = None) -> dict:
    """Pure geometry-manifest row upsert (no mutation)."""
    if not isinstance(manifest, dict) or not isinstance(
            manifest.get("races"), dict):
        raise SpatialProvenanceError("geometry manifest needs races mapping")
    if manifest.get("manifest_schema_version") != \
            GEOMETRY_MANIFEST_SCHEMA_VERSION:
        raise SpatialProvenanceError("unsupported geometry manifest version")
    if status not in GEOMETRY_STATUSES:
        raise SpatialProvenanceError(
            f"status must be one of {sorted(GEOMETRY_STATUSES)}")
    row: dict = {"status": status}
    if status == GEOMETRY_STATUS_COMPLETE:
        for key, value in (("source_content_sha256",
                            source_content_sha256),
                           ("geometry_sha256", geometry_sha256)):
            if not isinstance(value, str) or len(value) != 64:
                raise SpatialProvenanceError(
                    f"COMPLETE rows require {key} hex digest")
            row[key] = value
        if not isinstance(n_points, int) or n_points < 64:
            raise SpatialProvenanceError("COMPLETE rows require n_points")
        row["n_points"] = n_points
        if pit_status not in (PIT_SUPPORTED, PIT_DEFERRED):
            raise SpatialProvenanceError("COMPLETE rows require pit_status")
        row["pit_status"] = pit_status
        if reason is not None:
            raise SpatialProvenanceError("COMPLETE rows carry no reason")
    else:
        if not (reason and reason.strip()):
            raise SpatialProvenanceError(f"{status} rows require a reason")
        row["reason"] = reason
    updated = dict(manifest)
    races = dict(manifest["races"])
    races[race_id] = row
    updated["races"] = races
    return updated


def validate_geometry_manifest(manifest: object) -> dict:
    if not isinstance(manifest, dict):
        raise SpatialProvenanceError("geometry manifest must be a mapping")
    if manifest.get("manifest_schema_version") != \
            GEOMETRY_MANIFEST_SCHEMA_VERSION:
        raise SpatialProvenanceError("unsupported geometry manifest version")
    races = manifest.get("races")
    if not isinstance(races, dict):
        raise SpatialProvenanceError("geometry manifest races must map")
    for race_id, row in races.items():
        if not isinstance(row, dict) or row.get("status") not in \
                GEOMETRY_STATUSES:
            raise SpatialProvenanceError(
                f"bad geometry row for {race_id!r}")
    return manifest


def verify_geometry_artifact(geometry_dir, race_id: str, row: dict,
                             source_content_sha256: str) -> bool:
    """Resume check: row COMPLETE + source-linked + artifact validates.

    Never trusts a JSON file merely for existing: the manifest row must
    reference the current observation identity, the artifact must pass
    validation, and its content hash must match the row.
    """
    from pathlib import Path

    try:
        if row.get("status") != GEOMETRY_STATUS_COMPLETE:
            return False
        if row.get("source_content_sha256") != source_content_sha256:
            return False
        path = Path(geometry_dir) / f"{race_id}.json"
        if not path.is_file():
            return False
        record = json.loads(path.read_text(encoding="utf-8"))
        validate_geometry(record)
        return (record.get("content_sha256")
                == row.get("geometry_sha256")
                == geometry_content_hash(record))
    except Exception:
        return False
