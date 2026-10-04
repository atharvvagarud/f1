"""Shared synthetic fixtures for V3.1B dynamics tests (no corpus).

Builders produce label-blind trajectory point dicts (POINT_KEYS schema)
and sweep rows. Mutations after T must never change feature(T).
"""

from raceintel.features.dynamics import calculators as C


def blank_point(**over):
    """One trajectory point; usable green default, all values settable.

    Follower default is causally coherent for driver "T": the follower's
    latest observation is one lap back (b_Fl = lap - 1) at b_F = t - 85,
    with "T" recorded as the follower's predecessor at F, so the
    last-gap level defaults to 5.0 s with staleness 85 s.
    """
    p = {
        "lap": 1, "t": 90.0, "pos": 5, "track": "all_clear",
        "driver": "T",
        "pit_in": False, "pit_out": False, "elig": True, "lt": 100.0,
        "gL_sec": 10.0, "gL_valid": True, "gL_ref": "L",
        "gA_sec": 2.0, "gA_valid": True, "gA_ref": "X",
        "b_ref": "Y", "b_F": 5.0, "b_Fl": 0, "b_predF": "T",
        "b_red": False,
        "pace_m3": 100.0, "pace_m5": 100.0,
        "rel_field": -0.5, "rel_ahead": 0.1, "traffic": False,
        "laps_since": 0, "stint_no": 1, "stint_lap": 1,
        "spread": 8.0, "spread_n": 12,
    }
    p.update(over)
    return p


def green_run(n_laps=12, t0=90.0, dt=90.0, **over):
    """Ascending usable lap series, lap numbers 1..n_laps."""
    pts = []
    for k in range(1, n_laps + 1):
        t = t0 + (k - 1) * dt
        kw = {"lap": k, "t": t, "stint_lap": k, "laps_since": k - 1,
              "b_F": t - 85.0, "b_Fl": k - 1}
        kw.update(over)
        pts.append(blank_point(**kw))
    # lap-1 edge falls out naturally: b_F = t0 - 85 precedes the first
    # own observation, so the strict at-or-before lookup misses -> null.
    return pts


def sweep_row(driver="A", lap=1, t=90.0, pos=5, track="all_clear",
              gL_sec=10.0, gL_valid=True):
    """One sweep input row."""
    return {"driver": driver, "lap": lap, "t": t, "pos": pos,
            "track": track, "gL_sec": gL_sec, "gL_valid": gL_valid}


def values_at(points, lap, driver=None):
    """Assembled feature dict for one target lap."""
    for n, v in C.assemble_driver(points, driver=driver):
        if n == lap:
            return v
    raise AssertionError(f"lap {lap} not assembled")
