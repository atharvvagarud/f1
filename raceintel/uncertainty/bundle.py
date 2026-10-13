"""V3.9C runtime uncertainty bundle builder (pure function of resolved evidence).

Thin product layer: consumes ALREADY-RESOLVED model/simulator natives
(probabilities + valid trial counts) and returns a typed vector bundle
{disagreement, monte_carlo_sampling, simulator_sensitivity}. It never
executes MC2, never runs inference, never fuses sources, never scores
confidence, never selects a source winner.

Disagreement definitions and the Wilson/SE implementation are reused from
the frozen V3.8C module (imported, never redefined). U3 is explicitly
unavailable (V3.9B gate); its absence is product information, not a zero.
"""

from __future__ import annotations

from raceintel.consensus import contracts as C
from raceintel.consensus import metrics as M

CALCULATION_VERSION = "v3.9c-uncertainty-bundle-v1"

MODEL_FAMILY = C.SourceFamily.INDEPENDENT_BINARY.value
SIMULATOR_FAMILY = (
    C.SourceFamily.MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY.value)

DIAGNOSTIC_LABEL = "DESCRIPTIVE_ONLY_NOT_A_TEST"

U3_BLOCK = {
    "status": "PROVENANCE_UNAVAILABLE",
    "executable": False,
    "reason": ("no scientifically defensible perturbation range is "
               "registered (V3.9B gate U3_NOT_EXECUTABLE)"),
    "gate": "U3_NOT_EXECUTABLE",
    "gate_version": "v3.9b-u3-gate-v1",
}


def _missing_entry(driver_id: str, *, source: str) -> dict:
    """Explicit missing-source entry: nulls with status, never zeros."""
    return {
        "driver_id": driver_id,
        "status": "MISSING_SOURCE",
        "missing_arm": source,
        "disagreement": None,
        "monte_carlo_sampling": None,
    }


def build_bundle(*, race_id: str, lap_number: int,
                 state_time_s: float | None, stage: str | None,
                 season: int, model_probs: dict, sim_probs: dict,
                 valid_trials: dict | int) -> dict:
    """Build the uncertainty bundle over the exact common driver universe.

    Drivers present in only one arm get explicit MISSING_SOURCE entries
    (never silent drops, never zero-filled). Trial counts <= 0 yield
    INSUFFICIENT_SIMULATIONS (never a fabricated interval).
    """
    common = sorted(set(model_probs) & set(sim_probs))
    model_ranks = M.average_ranks(
        {d: model_probs[d] for d in common}) if common else {}
    sim_ranks = M.average_ranks(
        {d: sim_probs[d] for d in common}) if common else {}
    drivers = []
    for driver in sorted(set(model_probs) | set(sim_probs)):
        if driver not in common:
            drivers.append(_missing_entry(
                driver, source="model"
                if driver not in model_probs else "simulation"))
            continue
        pm = float(model_probs[driver])
        ps = float(sim_probs[driver])
        n = valid_trials[driver] if isinstance(valid_trials, dict) \
            else int(valid_trials)
        if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
            drivers.append({
                "driver_id": driver, "status": "INSUFFICIENT_SIMULATIONS",
                "disagreement": None, "monte_carlo_sampling": None})
            continue
        k = int(round(ps * n))
        p_hat = k / n
        se = M.mc_sampling_se(p_hat, n)
        lo, hi = M.wilson_interval(p_hat, n)
        gap = M.signed_gap(pm, ps)
        drivers.append({
            "driver_id": driver,
            "status": "AVAILABLE",
            "disagreement": {
                "status": "AVAILABLE",
                "p_model": pm,
                "p_model_family": MODEL_FAMILY,
                "p_simulation": ps,
                "p_simulation_family": SIMULATOR_FAMILY,
                "signed_gap": gap,
                "absolute_gap": M.absolute_gap(pm, ps),
                "model_rank": model_ranks[driver],
                "simulation_rank": sim_ranks[driver],
                "model_inside_simulation_wilson": M.value_inside_interval(
                    pm, (lo, hi)),
            },
            "monte_carlo_sampling": {
                "status": "AVAILABLE",
                "success_count_k": k,
                "valid_futures_n": n,
                "p_hat": p_hat,
                "standard_error": se,
                "wilson_95_lower": lo,
                "wilson_95_upper": hi,
                "precision_label": "FINITE_MC_SAMPLING_CONTEXT_ONLY",
            },
            "diagnostic": {
                "gap_to_sampling_ratio":
                    (abs(gap) / se) if se > 0 else None,
                "label": DIAGNOSTIC_LABEL,
            },
        })
    spearman = M.spearman(model_ranks, sim_ranks) if common else None
    lead_m = max(common, key=lambda d: model_probs[d]) if common else None
    lead_s = max(common, key=lambda d: sim_probs[d]) if common else None
    top_m = set(
        sorted(common, key=lambda d: model_probs[d], reverse=True)[:3])
    top_s = set(sorted(common, key=lambda d: sim_probs[d], reverse=True)[:3])
    return {
        "schema_version": CALCULATION_VERSION,
        "metric_implementation": M.METRICS_IMPLEMENTATION_IDENTITY,
        "state": {"state_id": f"{race_id}|lap{lap_number}",
                  "race_id": race_id, "lap_number": lap_number,
                  "state_time_s": state_time_s, "stage": stage,
                  "season": season},
        "sources": {
            "model": {"source": C.SourceId.V3_1B_LOGISTIC.value,
                      "probability_family": MODEL_FAMILY},
            "simulation": {"source": C.SourceId.MC2_E.value,
                           "probability_family": SIMULATOR_FAMILY},
        },
        "drivers": drivers,
        "field": {
            "n_common_drivers": len(common),
            "rank_correlation_spearman": spearman,
            "leader_model": lead_m,
            "leader_simulation": lead_s,
            "leader_agree": (lead_m == lead_s) if common else None,
            "top3_jaccard": (len(top_m & top_s) / len(top_m | top_s)
                             if top_m | top_s else None),
        },
        "simulator_sensitivity": dict(U3_BLOCK),
    }
