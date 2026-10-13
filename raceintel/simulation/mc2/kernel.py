"""MC2 simulation kernel (V3.2D Part AF-AH).

Explicit component pipeline (no monolith):

    eligible SimulationState (V3.2C)
      -> driver anchor (per-driver offset vs R3 expectation)
      -> bounded decaying dynamics (short-horizon drift)
      -> context variance (regime std for residual scale)
      -> correlated residual evolution (AR(1) over empirical draws)
      -> [traffic context: GATED OFF in V3.2D]
      -> R4 deterministic base + R6 pit boundary (unchanged semantics)

The kernel never edits R3 modules, never calls the winner model, never
normalizes ML probabilities, and never simulates DNFs/weather/SC. Output
semantics preserve the existing concepts (winner/podium frequency,
expected finish, position distributions, sample orders, valid counts);
unsupported DNF/event-trajectory claims are never added.

RNG: pace uniforms come from the caller's stream; the AR(1) innovation
path uses the dedicated MC2 domain (residuals.mc2_stream) so R3 streams
are never perturbed. Same seed -> same trajectory; chunk invariance holds
because one stream is consumed per simulation in event order.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

import numpy as np

from raceintel.simulation.mc2.anchor import (
    ANCHOR_PRIMARY_WINDOW,
    compute_anchor,
)
from raceintel.simulation.mc2.contract import (
    MC2_KERNEL_SCHEMA,
    MC2_RESEARCH_VERSION,
    MC2_RNG_SCHEMA,
)
from raceintel.simulation.mc2.dynamics import (
    DYNAMICS_DECAY_CANDIDATES,
    DYNAMICS_DRIFT_BOUND_S,
    DYNAMICS_PRIMARY_DECAY,
    DynamicsInput,
    combined_drift,
)
from raceintel.simulation.mc2.residuals import (
    ar1_step,
    innovation_scale,
    validate_rho,
)
from raceintel.simulation.mc2.variance import select_variance

__all__ = [
    "MC2_KERNEL_VERSION",
    "ARM_MECHANISMS",
    "DriverMechanism",
    "mc2_expected_pace_s",
    "mc2_residual_step",
    "kernel_identity",
    "run_mc2",
]

#: Kernel version pinned into the research identity.
MC2_KERNEL_VERSION = MC2_KERNEL_SCHEMA

#: Arm -> mechanism switches (F traffic stays False: gate NOT_RUN).
ARM_MECHANISMS = {
    "A_R3_BASELINE": {"anchor": False, "dynamics": False,
                      "variance": False, "ar1": False, "traffic": False},
    "B_DRIVER_ANCHOR": {"anchor": True, "dynamics": False,
                        "variance": False, "ar1": False, "traffic": False},
    "C_DRIVER_ANCHOR_PLUS_DYNAMICS": {"anchor": True, "dynamics": True,
                                      "variance": False, "ar1": False,
                                      "traffic": False},
    "D_CONDITIONED_VARIANCE": {"anchor": True, "dynamics": True,
                               "variance": True, "ar1": False,
                               "traffic": False},
    "E_AR1_RESIDUAL": {"anchor": True, "dynamics": True,
                       "variance": True, "ar1": True, "traffic": False},
    "F_TRAFFIC_CONTEXT": {"anchor": True, "dynamics": True,
                          "variance": True, "ar1": True, "traffic": False},
}


@dataclass(frozen=True)
class DriverMechanism:
    """Per-driver causal mechanism state at T (all inputs <= T)."""

    anchor_offset_s: float = 0.0
    slope_l3: float | None = None
    slope_l10: float | None = None
    regime_std_s: float = 1.5
    rho: float = 0.0
    ar1_enabled: bool = False
    previous_eps: float = 0.0

    def __post_init__(self) -> None:
        for name in ("anchor_offset_s", "regime_std_s", "previous_eps"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        if self.regime_std_s <= 0:
            raise ValueError("regime_std_s must be positive")
        validate_rho(self.rho)


def mc2_expected_pace_s(r3_mu_s: float, mechanism: DriverMechanism,
                        laps_ahead: int, *,
                        arm: str = "E_AR1_RESIDUAL") -> float:
    """MC2 expected pace: R3 mu + anchor + bounded drift (no residual)."""
    switches = ARM_MECHANISMS.get(arm)
    if switches is None:
        raise ValueError(f"unknown arm {arm!r}")
    if not math.isfinite(r3_mu_s):
        raise ValueError("r3_mu_s must be finite")
    mu = float(r3_mu_s)
    if switches["anchor"]:
        mu += mechanism.anchor_offset_s
    if switches["dynamics"]:
        mu += combined_drift(
            DynamicsInput(slope_l3_s_per_lap=mechanism.slope_l3,
                          slope_l10_s_per_lap=mechanism.slope_l10),
            max(1, int(laps_ahead)), decay=DYNAMICS_PRIMARY_DECAY)
    if not math.isfinite(mu):
        raise ValueError("MC2 pace overflowed")
    return float(mu)


def mc2_residual_step(empirical_draw: float, mechanism: DriverMechanism, *,
                      arm: str = "E_AR1_RESIDUAL") -> tuple:
    """Next residual + updated mechanism (AR(1) or independent)."""
    switches = ARM_MECHANISMS.get(arm)
    if switches is None:
        raise ValueError(f"unknown arm {arm!r}")
    if not math.isfinite(empirical_draw):
        raise ValueError("empirical_draw must be finite")
    if switches["ar1"] and mechanism.ar1_enabled:
        eps = ar1_step(mechanism.previous_eps, empirical_draw,
                       mechanism.rho)
    else:
        eps = float(empirical_draw)
    updated = DriverMechanism(
        anchor_offset_s=mechanism.anchor_offset_s,
        slope_l3=mechanism.slope_l3, slope_l10=mechanism.slope_l10,
        regime_std_s=mechanism.regime_std_s, rho=mechanism.rho,
        ar1_enabled=mechanism.ar1_enabled, previous_eps=eps)
    return eps, updated


def kernel_identity() -> str:
    """Research version identity string (encodes state/kernel/RNG schema)."""
    return (f"{MC2_RESEARCH_VERSION}+{MC2_KERNEL_SCHEMA}+{MC2_RNG_SCHEMA}"
            f"+state:mc2-field-v1+presence:v3.2c-presence-v1")


def _finite_or_zero_once(value) -> float:
    """P2A: run-once version of dynamics._finite_or_zero (identical rules)."""
    if value is None:
        return 0.0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0


def _drift_pure(s3: float, s10: float, ahead: int,
                decay_pow: tuple) -> float:
    """P2A: kernel-internal combined drift replicating combined_drift
    (exponential primary) with byte-identical arithmetic.

    Mirrors drift_exponential per slope (clip(slope*h, BOUND) * decay**h
    with the same max(-B, min(B, .)) clip and float value semantics) and
    combined_drift's clip(short + 0.5*long, BOUND) mix. decay_pow[h] holds
    the identical float DYNAMICS_PRIMARY_DECAY**h. Public drift functions
    are untouched; this exists only to avoid per-event dataclass builds,
    dispatch, and pow recomputation inside run_mc2.
    """
    h = ahead if ahead >= 1 else 1
    bound = DYNAMICS_DRIFT_BOUND_S
    short = max(-bound, min(bound, s3 * h)) * decay_pow[h]
    long = max(-bound, min(bound, s10 * h)) * decay_pow[h]
    return max(-bound, min(bound, short + 0.5 * long))


def run_mc2(initial_state, selection, sampler, mechanisms: dict, *,
            arm: str = "E_AR1_RESIDUAL",
            master_seed: int = 20240101, simulation_count: int = 100,
            empirical_std_s: float | None = None,
            chunk_size: int = 512) -> dict:
    """Run MC2 research trajectories (pits-off, dry-green) for one state.

    Research-only event loop mirroring R4 ordering semantics (earliest
    next-completion first, ``driver_id`` tie-break; final order by
    ``(-laps, race_time, driver_id)``). Per-driver pace is the R3 mu plus
    the armed MC2 mechanisms; residuals are empirical draws (scaled by
    ``regime/empirical`` when the variance switch is armed) evolved through
    the AR(1) step when armed. One dedicated MC2 stream per simulation is
    consumed in event order, so results are seed-deterministic and chunk
    invariant. ``chunk_size`` is accepted for API symmetry and ignored:
    trajectories are independent by construction.

    Returns winner counts, position distributions, expected finish,
    valid/invalid counts, and the request identity. Raises nothing for
    numerical failures: failed trajectories count as invalid.
    """
    from raceintel.simulation.engine import (
        expected_lap_time_s,
        max_lap_events,
    )
    from raceintel.simulation.mc2.residuals import mc2_stream

    switches = ARM_MECHANISMS.get(arm)
    if switches is None:
        raise ValueError(f"unknown arm {arm!r}")
    if type(master_seed) is not int or type(simulation_count) is not int:
        raise ValueError("master_seed/simulation_count must be plain ints")
    if simulation_count < 1:
        raise ValueError("simulation_count must be >= 1")
    if DYNAMICS_PRIMARY_DECAY not in DYNAMICS_DECAY_CANDIDATES:
        raise ValueError("primary decay outside admitted candidates")

    roster = list(initial_state.drivers)
    scheduled = int(initial_state.scheduled_laps)
    bound = max_lap_events(len(roster), scheduled)
    base_pace = {
        d.driver_id: (selection.base.value
                      + selection.offset_for(d.constructor_id).value)
        for d in roster
    }
    start_lap = {d.driver_id: int(d.lap_number) for d in roster}

    # P2A per-run hoisting (all inputs run-fixed; values identical to the
    # per-event derivations they replace; proven by fixture parity):
    # - distinct rhos validated once (was: 3 validations per step);
    # - innovation scales precomputed per rho (was: sqrt per step);
    # - decay powers memoized (was: pow per drift call);
    # - sampler grids as numpy arrays (was: 2 asarray per draw);
    # - per-driver mechanism scalars precomputed (was: dataclass rebuild
    #   + DynamicsInput build per event).
    for _m in mechanisms.values():
        validate_rho(_m.rho)
    validate_rho(0.0)
    _rhos = {m.rho for m in mechanisms.values()} | {0.0}
    _scale = {r: innovation_scale(r) for r in _rhos}
    _max_ahead = max(1, scheduled - min(start_lap.values()))
    _decay_pow = tuple(DYNAMICS_PRIMARY_DECAY ** h
                       for h in range(_max_ahead + 1))
    _xp = np.asarray(sampler._xp, dtype=np.float64)
    _fp = np.asarray(sampler._fp, dtype=np.float64)
    _anchor = {}
    _s3 = {}
    _s10 = {}
    _ar1_on = {}
    _rho = {}
    _vscale = {}
    _prev0 = {}
    for did in base_pace:
        _m = mechanisms.get(did)
        if _m is None:
            _m = DriverMechanism()
        _anchor[did] = _m.anchor_offset_s
        _s3[did] = _finite_or_zero_once(_m.slope_l3)
        _s10[did] = _finite_or_zero_once(_m.slope_l10)
        _ar1_on[did] = bool(_m.ar1_enabled)
        _rho[did] = _m.rho
        _prev0[did] = _m.previous_eps
        if switches["variance"] and empirical_std_s:
            _vscale[did] = _m.regime_std_s / empirical_std_s
        else:
            _vscale[did] = None
    _use_anchor = bool(switches["anchor"])
    _use_dynamics = bool(switches["dynamics"])
    _use_ar1 = bool(switches["ar1"])

    winner_counts: dict[str, int] = {}
    pos_lists: dict[str, list] = {d.driver_id: [] for d in roster}
    valid = 0
    invalid = 0
    first_order: list | None = None

    for sim_id in range(simulation_count):
        rng = mc2_stream(master_seed, sim_id)
        pool = rng.random(bound)
        cursor = 0
        # P2A: fixed mechanism scalars hoisted per run; only the AR1
        # previous-epsilon evolves (same local-mutable pattern as the
        # lap/time/age dicts below). Values and update order identical.
        prev = dict(_prev0)
        # Local trajectory state: [lap, time, age, anchor_age, sim_laps_done].
        lap = dict(start_lap)
        time_s = {d.driver_id: float(d.race_time_s) for d in roster}
        age = {d.driver_id: int(d.tyre_age) for d in roster}
        anchor_age = dict(age)
        done_sim_laps = dict.fromkeys(base_pace, 0)
        # Schedule every driver's next lap, then advance earliest-first.
        # P2B: binary heap of (event_time, driver_id, next_lap, next_age)
        # replacing the per-iteration min/sorted/dictcomp scan. Ordering is
        # identical to the legacy queue by construction (order contract in
        # results/v3/performance_mc2/p2b/event_order_contract.json):
        # earliest time first, ties in ascending driver_id order, each
        # same-stamp batch drained before any of its events is processed,
        # and at most one live entry per driver (pop-then-push, as the
        # legacy dict), so no stale entry can exist and none may execute.
        # Tuple comparison never reaches the payload: driver_id is unique
        # among live entries, so only (event_time, driver_id) decides.
        heap: list[tuple] = []

        def schedule(did: str) -> bool:
            nonlocal cursor
            next_lap = lap[did] + 1
            if next_lap > scheduled:
                return False
            next_age = age[did] + 1
            mu_r3, _, _ = expected_lap_time_s(
                selection, base_pace[did], next_lap, next_age,
                anchor_age[did])
            # P2A: inline of mc2_expected_pace_s with identical operation
            # order (r3 finite check, anchor add, drift add, overflow
            # check). Public function untouched for external callers.
            if not math.isfinite(mu_r3):
                raise ValueError("r3_mu_s must be finite")
            mu = float(mu_r3)
            if _use_anchor:
                mu += _anchor[did]
            if _use_dynamics:
                ahead = done_sim_laps[did] + 1
                mu += _drift_pure(_s3[did], _s10[did], ahead, _decay_pow)
            if not math.isfinite(mu):
                raise ValueError("MC2 pace overflowed")
            # P2A: scalar interp over hoisted grid arrays (identical
            # values to sample_unit's per-call asarray path).
            draw = float(np.interp(float(pool[cursor]), _xp, _fp))
            cursor += 1
            vscale = _vscale[did]
            if vscale is not None:
                draw *= vscale
            # P2A: internal AR1 evolution replicating mc2_residual_step
            # exactly (rho*prev + scale*draw when armed+enabled, else the
            # draw; previous-epsilon always carried like the original's
            # updated mechanism). Public function untouched.
            if _use_ar1 and _ar1_on[did]:
                eps = _rho[did] * prev[did] + _scale[_rho[did]] * draw
            else:
                eps = draw
            prev[did] = eps
            lap_time = mu + eps
            if not math.isfinite(lap_time) or lap_time <= 0:
                return False
            heapq.heappush(
                heap, (time_s[did] + lap_time, did, next_lap, next_age))
            return True

        ok = True
        for did in base_pace:
            if lap[did] < scheduled and not schedule(did):
                ok = False
        finished: dict[str, float] = {}
        steps = 0
        while ok and len(finished) < len(base_pace) and steps <= bound:
            steps += 1
            if not heap:
                break
            event_t = heap[0][0]
            batch: list[tuple] = []
            while heap and heap[0][0] == event_t:
                batch.append(heapq.heappop(heap))
            for t, did, nl, na in batch:
                lap[did], age[did], time_s[did] = nl, na, t
                done_sim_laps[did] += 1
                if nl >= scheduled:
                    finished[did] = t
                elif not schedule(did):
                    ok = False
                    break
        if not ok or len(finished) != len(base_pace):
            invalid += 1
            continue
        valid += 1
        order = sorted(finished, key=lambda did: (finished[did], did))
        if first_order is None:
            first_order = list(order)
        winner_counts[order[0]] = winner_counts.get(order[0], 0) + 1
        for pos, did in enumerate(order, start=1):
            pos_lists[did].append(pos)

    n = valid if valid else 1
    position_counts: dict[str, dict[int, int]] = {}
    position_distribution: dict[str, dict[int, float]] = {}
    podium_frequency: dict[str, float] = {}
    field = len(roster)
    for did in sorted(pos_lists):
        counts: dict[int, int] = {}
        for pos in pos_lists[did]:
            counts[pos] = counts.get(pos, 0) + 1
        position_counts[did] = dict(sorted(counts.items()))
        position_distribution[did] = {
            pos: c / n for pos, c in sorted(counts.items())}
        podium_frequency[did] = sum(
            c for pos, c in counts.items() if pos <= min(3, field)) / n
    return {
        "arm": arm,
        "kernel": MC2_KERNEL_VERSION,
        "master_seed": master_seed,
        "simulation_count": simulation_count,
        "valid": valid,
        "invalid": invalid,
        "winner_counts": dict(sorted(winner_counts.items())),
        "winner_frequency": {did: c / n
                             for did, c in sorted(winner_counts.items())},
        "expected_finish": {did: sum(v) / n
                            for did, v in sorted(pos_lists.items())},
        "position_counts": position_counts,
        "position_distribution": position_distribution,
        "podium_frequency": dict(sorted(podium_frequency.items())),
        "sample_order": first_order or [],
    }
