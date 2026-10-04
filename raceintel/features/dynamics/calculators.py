"""V3.1B causal dynamics calculators (frozen V3.1A-C1 contract implementation).

Two-level design reusing frozen infrastructure semantics:

1. :func:`sweep_race` — one time-ordered sweep per race over joined
   per-row states. Maintains latest-per-driver snapshots (``state_time_s
   <= T``, no fall-forward) and emits per-row follower-observation
   provenance (successor identity, its latest observation time/lap, its
   predecessor at that observation, red-side flag) plus field spread.
   No same-lap follower seconds are emitted: the follower has generally
   not crossed yet at T (V3.1A-C1 asymmetry).
2. :func:`assemble_driver` — per-(race, driver) lap-ordered window
   assembly of all 29 contracted features over per-row frozen values
   (gap levels, pace medians, relative levels, traffic band) plus D9
   source fields (position, track_state, pit markers, lap times). The
   follower last-gap level is resolved here from the sweep provenance
   against the target's own causal history (latest own observation
   with time <= F).

Label-blind by construction: the point schema carries no label, mask,
or result field; calculators never read them.

Masking (uniform): a trajectory point is *usable* iff its lap is not a
pit in/out lap and ``track_state == 'all_clear'``. Masked laps are
excluded from every trajectory point set and break runs. Levels
(last-gap level, staleness, lap diff, spread level, flags,
counts/depths) are exempt — they carry their own geometric/validity
gating.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np

from raceintel.features.dynamics.contract import (
    ALL_DEFINITIONS,
    FEATURE_SETS,
)
from raceintel.features.gaps import (
    GapStatus,
    ahead_reference,
    leader_reference,
)

#: Trajectory point keys consumed by the calculators (documentation of
#: the label-blind schema; builders map real frames onto these).
POINT_KEYS = (
    "lap", "t", "pos", "track", "pit_in", "pit_out",
    "elig", "lt",
    "gL_sec", "gL_valid", "gL_ref",
    "gA_sec", "gA_valid", "gA_ref",
    "b_ref", "b_F", "b_Fl", "b_predF", "b_red",
    "pace_m3", "pace_m5",
    "rel_field", "rel_ahead", "traffic",
    "laps_since", "stint_no", "stint_lap",
    "spread", "spread_n",
    "driver",
)

_ALL_29 = tuple(d.name for d in ALL_DEFINITIONS)
_CORE_26 = tuple(FEATURE_SETS["V3_1_DYNAMICS_CORE"])


# ---------------------------------------------------------------------------
# Numerical primitives (exact contracted forms; OLS mirrors F8 math)
# ---------------------------------------------------------------------------

def ols_slope(xs, ys) -> float | None:
    """Closed-form OLS slope over x (target laps); None when degenerate.

    Identical math to ``rates.ols_slope_xy`` (pinned by parity test):
    requires >= 2 points spanning x > 0.
    """
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if len(x) < 2:
        return None
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        return None
    if float(x.max() - x.min()) <= 0:
        return None
    xm, ym = x.mean(), y.mean()
    den = float(((x - xm) ** 2).sum())
    if den == 0.0:
        return None
    return float(((x - xm) * (y - ym)).sum() / den)


def endpoint_rate(now: float | None, old: float | None,
                  lap_delta: int | None) -> float | None:
    """(now - old) / lap_delta; None unless both finite and delta > 0."""
    if now is None or old is None or lap_delta is None:
        return None
    if not math.isfinite(now) or not math.isfinite(old):
        return None
    if int(lap_delta) <= 0:
        return None
    return float((now - old) / lap_delta)


def iqr(vals) -> float | None:
    """Interquartile range (linear interpolation); None when < 3 finite."""
    v = [float(w) for w in vals if w is not None and math.isfinite(w)]
    if len(v) < 3:
        return None
    q75, q25 = np.percentile(v, [75, 25])
    return float(q75 - q25)


def pctl_range(vals, lo: float = 10.0, hi: float = 90.0,
               min_n: int = 5) -> tuple[float | None, int]:
    """(P(hi) - P(lo), n); (None, n) when fewer than min_n finite."""
    v = [float(w) for w in vals if w is not None and math.isfinite(w)]
    if len(v) < min_n:
        return None, len(v)
    phi, plo = np.percentile(v, [hi, lo])
    return float(phi - plo), len(v)


# ---------------------------------------------------------------------------
# Window engine (one shared causal mechanism)
# ---------------------------------------------------------------------------

def is_usable(p: dict) -> bool:
    """Masked iff pit in/out lap or non-all_clear track (uniform rule)."""
    if p.get("pit_in") or p.get("pit_out"):
        return False
    return p.get("track") == "all_clear"


def collapse_laps(points: list) -> list:
    """One point per lap: latest state_time_s wins (empirically unique)."""
    best: dict = {}
    for p in points:
        lap = int(p["lap"])
        if lap not in best or float(p["t"]) >= float(best[lap]["t"]):
            best[lap] = p
    return [best[k] for k in sorted(best)]


def window(points: list, lap_now: int, horizon: int) -> list:
    """Points with current_lap - H <= lap <= current_lap (inclusive)."""
    return [p for p in points if int(p["lap"]) >= lap_now - horizon
            and int(p["lap"]) <= lap_now]


def anchor(points: list, lap_now: int, horizon: int) -> dict | None:
    """Latest point with lap <= N - H (F8 anchor shape); None if none."""
    cands = [p for p in points if int(p["lap"]) <= lap_now - horizon]
    if not cands:
        return None
    return max(cands, key=lambda p: (int(p["lap"]), float(p["t"])))


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _pos(v):
    try:
        if v is None:
            return None
        f = float(v)
        if not math.isfinite(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def same_ref_run(points: list, key_sec: str, key_valid: str,
                 key_ref: str) -> tuple[list, list] | tuple[None, None]:
    """Trailing same-reference valid usable run ending at current point.

    Walks back from current; stops at the first masked, invalid, or
    different-reference entry (F8 ``gap_rate_from_points`` rule).
    Returns (laps, seconds) or (None, None) when current is unusable.
    """
    if not points:
        return None, None
    cur = points[-1]
    if not is_usable(cur):
        return None, None
    if not cur.get(key_valid) or cur.get(key_ref) is None:
        return None, None
    if _num(cur.get(key_sec)) is None:
        return None, None
    ref = cur[key_ref]
    laps, secs = [], []
    for p in reversed(points):
        if not is_usable(p):
            break
        if not p.get(key_valid) or p.get(key_ref) != ref:
            break
        v = _num(p.get(key_sec))
        if v is None:
            break
        laps.append(int(p["lap"]))
        secs.append(v)
    laps.reverse()
    secs.reverse()
    if len(laps) < 2:
        return None, None
    return laps, secs


# ---------------------------------------------------------------------------
# Level 1: per-race sweep (behind geometry + field spread)
# ---------------------------------------------------------------------------

def _succession(latest: dict, target: str, tpos: int | None):
    """Unique successor (pos+1 holder) at this snapshot; else (None, why)."""
    if tpos is None:
        return None, "ambiguous"
    holders = [d for d, s in latest.items()
               if d != target and s["pos"] == tpos + 1]
    if len(holders) == 1:
        return holders[0], "ok"
    if not holders:
        return None, "none"
    return None, "ambiguous"


def sweep_race(rows: list) -> list:
    """Time-ordered sweep emitting per-row refs, follower provenance, spread.

    ``rows``: dicts with driver, lap, t, pos, track, gL_sec, gL_valid.
    Leader/ahead reference identities reuse the frozen F6
    ``leader_reference`` / ``ahead_reference`` over the causal snapshot
    (latest state per driver with ``state_time_s <= T``) — zero
    divergence risk. Follower provenance (V3.1A-C1): the unique
    successor's latest observation (time F, lap Fl) plus the successor's
    own predecessor recorded at that observation (for the strict
    predecessor check in assembly) plus a red-side flag. No follower
    seconds are computed here: same-lap follower crossings lie in the
    future at T. Spread = P90-P10 over latest valid leader-gap
    seconds (min 5 contributors), null otherwise. Returns a same-order
    list of dicts with gL_ref, gA_ref, b_ref, b_F, b_Fl, b_predF, b_red,
    spread, spread_n.
    """
    order = sorted(range(len(rows)),
                   key=lambda i: (float(rows[i]["t"]),
                                  int(rows[i]["lap"]),
                                  str(rows[i]["driver"])))
    latest: dict = {}
    latest_ahead: dict = {}
    out = [None] * len(rows)
    for i in order:
        r = rows[i]
        d = str(r["driver"])
        latest[d] = {
            "lap": int(r["lap"]), "t": float(r["t"]),
            "pos": _pos(r.get("pos")),
            "track": r.get("track"),
            "gL_sec": _num(r.get("gL_sec")),
            "gL_valid": bool(r.get("gL_valid")),
        }
        entries = {
            m: SimpleNamespace(observable=True,
                               values={"position": s["pos"]},
                               observed_lap=s["lap"],
                               observed_time_s=s["t"])
            for m, s in latest.items()
        }
        tpos = latest[d]["pos"]
        tlap = latest[d]["lap"]
        tt = latest[d]["t"]
        ttrack = latest[d]["track"]
        lead_id, _, _ = leader_reference(entries, d, tpos)
        ahead_id, ahead_status, _ = ahead_reference(entries, d, tpos)
        latest_ahead[d] = ahead_id \
            if ahead_status is not GapStatus.NO_CAR_AHEAD else None
        b = {"gL_ref": lead_id,
             "gA_ref": ahead_id
             if ahead_status is not GapStatus.NO_CAR_AHEAD else None}
        ref_id, why = _succession(latest, d, tpos)
        if ref_id is None:
            b.update({"b_ref": None, "b_F": None, "b_Fl": None,
                       "b_predF": None, "b_red": None})
        else:
            s = latest[ref_id]
            b.update({"b_ref": ref_id, "b_F": float(s["t"]),
                       "b_Fl": int(s["lap"]),
                       "b_predF": latest_ahead.get(ref_id),
                       "b_red": bool(ttrack == "red_flag"
                                     or s["track"] == "red_flag")})
        vals = [s["gL_sec"] for s in latest.values()
                if s["gL_valid"] and s["gL_sec"] is not None
                and math.isfinite(s["gL_sec"])]
        spread, n = pctl_range(vals, min_n=5)
        b["spread"] = spread
        b["spread_n"] = n
        out[i] = b
    return out


# ---------------------------------------------------------------------------
# Level 2: per-driver window assembly (all 29 contracted features)
# ---------------------------------------------------------------------------

def _own_latest_at_or_before(pts: list, idx: int, F: float):
    """Latest own collapsed point with t <= F scanning back from idx."""
    for j in range(idx, -1, -1):
        if float(pts[j]["t"]) <= float(F) + 1e-9:
            return pts[j]
    return None


def _lastgap_of(driver: str, pts: list, idx: int) -> float | None:
    """Last causally observed follower gap for pts[idx] (level, unmasked).

    F = successor's latest observation time <= T (sweep provenance).
    Valid iff successor known, strict predecessor check passes
    (target was the successor's unique predecessor at F), neither side
    red, and the target's latest observation at-or-before F shares the
    follower's observed lap. Returns F - T_at_F (>= 0) else None.
    """
    p = pts[idx]
    ref = p.get("b_ref")
    F = _num(p.get("b_F"))
    Fl = p.get("b_Fl")
    if ref is None or F is None or Fl is None:
        return None
    if p.get("b_predF") != driver:
        return None
    if p.get("b_red"):
        return None
    try:
        Fl = int(Fl)
    except (TypeError, ValueError):
        return None
    q = _own_latest_at_or_before(pts, idx, F)
    if q is None or int(q["lap"]) != Fl:
        return None
    return float(F - float(q["t"]))


def _anchor_delta(points: list, lap_now: int, horizon: int, key: str,
                  rate: bool = True):
    """Endpoint (delta or rate) for a precomputed level over H laps."""
    cur = next((p for p in reversed(points) if int(p["lap"]) == lap_now),
               None)
    if cur is None or not is_usable(cur):
        return None
    a = anchor(points, lap_now, horizon)
    if a is None or not is_usable(a):
        return None
    v_now, v_old = _num(cur.get(key)), _num(a.get(key))
    if v_now is None or v_old is None:
        return None
    if rate:
        return endpoint_rate(v_now, v_old, lap_now - int(a["lap"]))
    return float(v_now - v_old)


def _follower_run(pts: list, lg_levels: list, idx: int,
                  horizon: int) -> tuple[list, list] | tuple[None, None]:
    """Trailing same-follower same-lap-regime usable last-gap run.

    Walks back from pts[idx]; stops at the first masked point, missing
    level, follower-identity change, or lap-regime (own lap minus
    follower observed lap) change. Returns (laps, gaps) or (None, None)
    when the current point is unusable or level-missing.
    """
    cur = pts[idx]
    if not is_usable(cur) or lg_levels[idx] is None:
        return None, None
    ref = cur.get("b_ref")
    try:
        diff_cur = int(cur["lap"]) - int(cur.get("b_Fl"))
    except (TypeError, ValueError):
        return None, None
    n = int(cur["lap"])
    laps, gaps = [], []
    for j in range(idx, -1, -1):
        q = pts[j]
        if int(q["lap"]) < n - horizon:
            break
        if not is_usable(q):
            break
        if q.get("b_ref") != ref:
            break
        if lg_levels[j] is None:
            break
        try:
            if int(q["lap"]) - int(q.get("b_Fl")) != diff_cur:
                break
        except (TypeError, ValueError):
            break
        laps.append(int(q["lap"]))
        gaps.append(lg_levels[j])
    laps.reverse()
    gaps.reverse()
    if len(laps) < 2:
        return None, None
    return laps, gaps


def assemble_driver(points: list, driver: str | None = None) -> list:
    """All 29 contracted values per target lap (ascending lap order).

    ``points``: lap-collapsed ascending dicts with POINT_KEYS schema
    (follower/spread keys filled by :func:`sweep_race`). ``driver``: the
    target driver id for the strict follower-predecessor check (falls
    back to the points' ``driver`` entry when omitted). Returns a list
    of ``(lap, values)`` with ``values`` keyed by the 29 contract names;
    missing evidence is None (never zero-filled); counts are ints.
    """
    pts = collapse_laps(sorted(points,
                               key=lambda p: (float(p["t"]),
                                              int(p["lap"]))))
    if driver is None and pts:
        driver = pts[0].get("driver")
    # Follower last-gap levels first (levels exempt from masking; the
    # slope run below consumes this per-point series).
    lg_levels = [_lastgap_of(driver, pts, i) if driver is not None
                 else None for i in range(len(pts))]
    out = []
    for i, p in enumerate(pts):
        n = int(p["lap"])
        v: dict = {}
        # --- position deltas ---
        for h, name in ((3, "dyn_position_change_l3"),
                        (10, "dyn_position_change_l10")):
            cur = p if is_usable(p) else None
            a = anchor(pts, n, h)
            if cur is None or a is None or not is_usable(a):
                v[name] = None
            else:
                c0, a0 = _pos(cur.get("pos")), _pos(a.get("pos"))
                v[name] = None if c0 is None or a0 is None \
                    else float(a0 - c0)
        # --- gap slopes / shape / volatility ---
        for h, key_s, key_v, key_r, name in (
                (3, "gL_sec", "gL_valid", "gL_ref",
                 "dyn_gap_leader_slope_l3"),
                (10, "gL_sec", "gL_valid", "gL_ref",
                 "dyn_gap_leader_slope_l10"),
                (3, "gA_sec", "gA_valid", "gA_ref",
                 "dyn_gap_ahead_slope_l3"),
                (10, "gA_sec", "gA_valid", "gA_ref",
                 "dyn_gap_ahead_slope_l10")):
            xs, ys = same_ref_run(window(pts, n, h), key_s, key_v, key_r)
            v[name] = None if xs is None else ols_slope(xs, ys)
        xs3, ys3 = same_ref_run(window(pts, n, 3), "gL_sec", "gL_valid",
                                "gL_ref")
        xs10, ys10 = same_ref_run(window(pts, n, 10), "gL_sec", "gL_valid",
                                  "gL_ref")
        s3 = None if xs3 is None else ols_slope(xs3, ys3)
        s10 = None if xs10 is None else ols_slope(xs10, ys10)
        v["dyn_gap_leader_slope_diff_l3_l10"] = \
            None if s3 is None or s10 is None else float(s3 - s10)
        # IQR over the same trailing same-ref run points.
        cur5 = window(pts, n, 5)[-1]
        ref5 = cur5.get("gL_ref")
        vals = []
        for q in reversed(window(pts, n, 5)):
            if not is_usable(q):
                break
            if not q.get("gL_valid") or q.get("gL_ref") != ref5:
                break
            w = _num(q.get("gL_sec"))
            if w is None:
                break
            vals.append(w)
        v["dyn_gap_leader_vol_l5"] = iqr(vals)
        # --- follower levels (last-gap trio + lap regime; levels exempt
        # from masking, each with its own causal gating) ---
        lg = lg_levels[i]
        v["dyn_follower_gap_last_seconds"] = lg
        v["dyn_follower_gap_last_age_s"] = \
            None if lg is None else float(p["t"]) - float(p["b_F"])
        Fl = p.get("b_Fl")
        v["dyn_follower_lap_diff"] = \
            None if p.get("b_ref") is None or Fl is None \
            else int(n - int(Fl))
        # --- follower threat trajectory (uniform masking + same-follower
        # same-regime runs; negative = follower closing) ---
        fxs, fys = _follower_run(pts, lg_levels, i, 5)
        v["dyn_follower_gap_slope_l5"] = \
            None if fxs is None else ols_slope(fxs, fys)
        # --- pace slopes / volatility ---
        v["dyn_pace_slope_l3"] = _anchor_delta(pts, n, 3, "pace_m3")
        v["dyn_pace_slope_l10"] = _anchor_delta(pts, n, 10, "pace_m5")
        pvol = [_num(q.get("lt")) for q in window(pts, n, 5)
                if is_usable(q) and q.get("elig") and _num(q.get("lt"))
                is not None]
        v["dyn_pace_vol_l5"] = iqr(pvol)
        # --- relative trajectories ---
        v["dyn_relpace_field_change_l5"] = _anchor_delta(
            pts, n, 5, "rel_field")
        v["dyn_relpace_ahead_change_l5"] = _anchor_delta(
            pts, n, 5, "rel_ahead")
        # --- field spread (level exempt; change masked uniformly) ---
        v["dyn_field_spread_lap"] = _num(p.get("spread"))
        v["dyn_field_spread_change_l5"] = _anchor_delta(
            pts, n, 5, "spread")
        # --- traffic persistence ---
        tw = [q for q in window(pts, n, 5)
              if is_usable(q) and q.get("traffic") is not None]
        v["dyn_traffic_n_l5"] = int(len(tw))
        if not tw:
            v["dyn_traffic_frac_l5"] = None
        else:
            v["dyn_traffic_frac_l5"] = float(
                sum(1 for q in tw if q.get("traffic")) / len(tw))
        # --- pit flags (levels) ---
        if p.get("pit_in") or p.get("pit_out"):
            v["dyn_pit_inout_flag"] = True
        elif p.get("pit_in") is None and p.get("pit_out") is None:
            v["dyn_pit_inout_flag"] = None
        else:
            v["dyn_pit_inout_flag"] = False
        ls = p.get("laps_since")
        try:
            lsv = None if ls is None else int(ls)
        except (TypeError, ValueError):
            lsv = None
        if lsv is None:
            v["dyn_recent_stop_l3"] = None
        else:
            v["dyn_recent_stop_l3"] = bool(lsv <= 2)
        # --- depths ---
        v["dyn_hist_laps_available"] = int(
            sum(1 for q in pts if int(q["lap"]) < n
                and int(q["lap"]) >= n - 10))
        for h, key_v2, key_r2, name in (
                (10, "gL_valid", "gL_ref", "dyn_gap_n_l10_leader"),
                (10, "gA_valid", "gA_ref", "dyn_gap_n_l10_ahead")):
            wpts = window(pts, n, h)
            if not wpts:
                v[name] = 0
                continue
            ref = wpts[-1].get(key_r2)
            v[name] = int(sum(
                1 for q in wpts if is_usable(q) and q.get(key_v2)
                and q.get(key_r2) is not None and q.get(key_r2) == ref))
        # --- VARIANT_A ---
        v["dyn_stint_pace_resid"] = _stint_resid(pts, p, n)
        v["dyn_gap_leader_slope_gated_clean"] = _gated_slope(pts, n)
        v["dyn_gap_accel_l5"] = _accel(pts, n)
        assert set(v) == set(_ALL_29), sorted(set(_ALL_29) - set(v))
        out.append((n, v))
    return out


def _stint_resid(pts: list, p: dict, n: int) -> float | None:
    """Descriptive stint pace trajectory (VARIANT; never degradation)."""
    if not is_usable(p):
        return None
    med_now = _num(p.get("pace_m5"))
    stint_now = p.get("stint_no")
    age_now = p.get("stint_lap")
    if med_now is None or stint_now is None or age_now is None:
        return None
    try:
        age_now = int(age_now)
    except (TypeError, ValueError):
        return None
    pool = []
    for q in pts:
        if int(q["lap"]) >= n or q.get("stint_no") is None:
            continue
        try:
            if int(q["stint_no"]) >= int(stint_now):
                continue
            age = int(q["stint_lap"]) if q.get("stint_lap") is not None \
                else None
        except (TypeError, ValueError):
            continue
        if age is None or abs(age - age_now) > 1:
            continue
        if not q.get("elig"):
            continue
        w = _num(q.get("lt"))
        if w is not None:
            pool.append(w)
    if len(pool) < 3:
        return None
    return float(med_now - float(np.median(pool)))


def _gated_slope(pts: list, n: int) -> float | None:
    """5-lap leader slope gated on a clean window (VARIANT)."""
    wpts = window(pts, n, 5)
    if not wpts:
        return None
    for q in wpts:
        if q.get("pit_in") or q.get("pit_out"):
            return None
        if q.get("track") != "all_clear":
            return None
    xs, ys = same_ref_run(wpts, "gL_sec", "gL_valid", "gL_ref")
    if xs is None:
        return None
    return ols_slope(xs, ys)


def _accel(pts: list, n: int) -> float | None:
    """Late-half minus early-half slope over 5 laps (VARIANT)."""
    wpts = window(pts, n, 5)
    xs, ys = same_ref_run(wpts, "gL_sec", "gL_valid", "gL_ref")
    if xs is None or len(xs) < 3:
        return None
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    mid = (xs.min() + xs.max()) / 2.0
    early = [(x, y) for x, y in zip(xs, ys) if x <= mid]
    late = [(x, y) for x, y in zip(xs, ys) if x > mid]
    if len(early) < 2 or len(late) < 2:
        return None
    se = ols_slope([e[0] for e in early], [e[1] for e in early])
    sl = ols_slope([e[0] for e in late], [e[1] for e in late])
    if se is None or sl is None:
        return None
    return float(sl - se)
