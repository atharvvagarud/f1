"""V3.8F product composer: MODEL / SIMULATION / DISAGREEMENT payloads.

Pure functions over already-aligned per-driver natives. No I/O, no inference,
no simulation, no ground truth, no fusion, no source-winner logic. Reuses the
frozen V3.8B contract vocabulary (SourceId, families, SupportStatus,
ReasonCode) and V3.8C metric implementations verbatim.

There is NO fourth "consensus probability" anywhere in this module.
"""

from __future__ import annotations

import math

from raceintel.consensus import contracts as C
from raceintel.consensus import metrics as M

PRODUCT_SOURCES = (C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)
PRODUCT_TARGET = C.Target.WIN

#: V3.8 research policy: 2025 is REVEALED_HOLDOUT / NON_PRISTINE /
#: PRODUCT_EXCLUDED. The runtime refuses it explicitly.
PRODUCT_EXCLUDED_SEASONS = frozenset({2025})

SAMPLING_CONTEXT_LABEL = "FINITE_MC_SAMPLING_CONTEXT_ONLY"
SIGNED_GAP_DEFINITION = "simulation_minus_model"


def assess_availability(*, season: int,
                        model_status: C.SupportStatus,
                        simulation_status: C.SupportStatus,
                        model_reason: C.ReasonCode | None = None,
                        simulation_reason: C.ReasonCode | None = None,
                        ) -> dict:
    """Availability triple. 2025 forces both sources UNAVAILABLE."""
    if season in PRODUCT_EXCLUDED_SEASONS:
        model_status = C.SupportStatus.UNAVAILABLE
        simulation_status = C.SupportStatus.UNAVAILABLE
        model_reason = C.ReasonCode.STATE_NOT_AVAILABLE
        simulation_reason = C.ReasonCode.STATE_NOT_AVAILABLE
    comparable = (model_status == C.SupportStatus.AVAILABLE
                  and simulation_status == C.SupportStatus.AVAILABLE)
    return {
        "model": model_status.value,
        "model_reason": model_reason.value if model_reason else None,
        "simulation": simulation_status.value,
        "simulation_reason": (simulation_reason.value
                              if simulation_reason else None),
        "comparison": ("COMPARABLE" if comparable else "NOT_COMPARABLE"),
    }


def _check_native(name: str, probs: dict) -> None:
    for driver, p in probs.items():
        if not isinstance(p, float) or not math.isfinite(p):
            raise ValueError(f"{name} probability for {driver!r} "
                             f"must be a finite float")
        if p < 0.0 or p > 1.0:
            raise ValueError(f"{name} probability for {driver!r} "
                             f"outside [0,1]")


def compose(*, race_id: str, lap_number: int,
            state_time_s: float | None,
            stage: str | None,
            season: int,
            model_probs: dict,
            simulation_probs: dict,
            valid_trials: dict | int,
            top_k: int = 3) -> dict:
    """Compose the strict MODEL/SIMULATION/DISAGREEMENT comparison payload.

    Inputs are already-aligned natives over identical (race, lap, driver)
    identities (B exact-identity semantics enforced by the caller supplying
    one dict per source). Values pass through verbatim: Logistic is never
    race-normalized, MC2 is never renormalized, supported MC2 zeros stay
    numeric 0.0, and no fourth-probability or winner field is produced.
    """
    if season in PRODUCT_EXCLUDED_SEASONS:
        raise ValueError("2025 is PRODUCT_EXCLUDED")
    if top_k < 1:
        raise ValueError(f"invalid top_k: {top_k!r}")
    _check_native("model", model_probs)
    _check_native("simulation", simulation_probs)

    common = sorted(set(model_probs) & set(simulation_probs))
    drivers = []
    for driver in common:
        pm = model_probs[driver]
        ps = simulation_probs[driver]
        n = valid_trials[driver] if isinstance(valid_trials, dict) \
            else valid_trials
        se = M.mc_sampling_se(ps, n)
        lo, hi = M.wilson_interval(ps, n)
        drivers.append({
            "driver_id": driver,
            "p_model": pm,
            "p_simulation": ps,
            "signed_gap": M.signed_gap(pm, ps),
            "absolute_gap": M.absolute_gap(pm, ps),
            "model_inside_simulation_interval": M.value_inside_interval(
                pm, (lo, hi)),
            "sampling": {"valid_trials": n,
                         "sampling_se": se,
                         "wilson_95": [lo, hi],
                         "label": SAMPLING_CONTEXT_LABEL},
        })

    ranks = M.state_ranks({C.SourceId.V3_1B_LOGISTIC.value:
                           {d: model_probs[d] for d in common},
                           C.SourceId.MC2_E.value:
                           {d: simulation_probs[d] for d in common}}) \
        if len(common) >= 2 else {}
    if ranks:
        rank_m = ranks[C.SourceId.V3_1B_LOGISTIC.value]
        rank_s = ranks[C.SourceId.MC2_E.value]
        leader_m = sorted(M.leader_set(rank_m))
        leader_s = sorted(M.leader_set(rank_s))
        top_m, size_m = M.topk_set(rank_m, top_k)
        top_s, size_s = M.topk_set(rank_s, top_k)
        rank_block = {
            "model_rank": {d: rank_m[d] for d in common},
            "simulation_rank": {d: rank_s[d] for d in common},
            "rank_displacement": {
                d: M.rank_displacement(rank_m[d], rank_s[d])
                for d in common},
            "rank_displacement_definition": "simulation_rank_minus_model_"
            "rank",
        }
        leader_block = {"model_leader": leader_m,
                        "simulation_leader": leader_s,
                        "exact_leader_match": leader_m == leader_s}
        topk_block = {f"top_{top_k}": {
            "model": sorted(top_m), "model_size": size_m,
            "simulation": sorted(top_s), "simulation_size": size_s,
            "jaccard": M.jaccard(top_m, top_s),
            "note": "overlap among drivers ranked by WIN probability; "
            "NOT P(finish<=k)"}}
    else:
        rank_block = {"note": "INSUFFICIENT_COMMON_DRIVERS"}
        leader_block = {"note": "INSUFFICIENT_COMMON_DRIVERS"}
        topk_block = {"note": "INSUFFICIENT_COMMON_DRIVERS"}

    return {
        "state": {"race_id": race_id, "lap_number": lap_number,
                  "state_time_s": state_time_s, "stage": stage,
                  "season": season},
        "model": {"source": C.SourceId.V3_1B_LOGISTIC.value,
                  "probability_family":
                      C.SourceFamily.INDEPENDENT_BINARY.value,
                  "target": PRODUCT_TARGET.value},
        "simulation": {"source": C.SourceId.MC2_E.value,
                       "probability_family":
                           C.SourceFamily.MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY.value,  # noqa: E501
                       "target": PRODUCT_TARGET.value},
        "disagreement": {
            "signed_gap_definition": SIGNED_GAP_DEFINITION,
            "drivers": drivers,
            "rank": rank_block,
            "leader": leader_block,
            "top_k": topk_block,
        },
    }
