"""V3.8B read-only source adapters (pure constructors, no I/O).

Each adapter maps a frozen source-native structure to immutable
NativePrediction records with zero transformation of the probability
value. No inference, no refit, no calibration, no ranking, no ground
truth. V3.4 ensemble is not representable here by design.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from raceintel.consensus import contracts as C


@dataclass(frozen=True)
class StateMeta:
    driver_id: str
    race_id: str
    year: int
    round: int
    lap: int
    stage: str


def validate_probability(value: float) -> float:
    """Fail closed on non-finite or out-of-range input. Never clamp."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"non-numeric probability: {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"non-finite probability: {value!r}")
    if value < 0.0 or value > 1.0:
        raise ValueError(f"probability outside [0,1]: {value!r}")
    return float(value)


def _check_meta(meta: StateMeta) -> None:
    if not meta.driver_id:
        raise ValueError("empty driver identity")
    if meta.stage not in C.STAGES:
        raise ValueError(f"unknown stage: {meta.stage!r}")


def _forbidden_truth_scan(mapping: dict) -> None:
    hit = [k for k in mapping
           if k in C.FORBIDDEN_GROUND_TRUTH_FIELDS]
    if hit:
        raise ValueError(f"ground-truth field in adapter input: {hit}")


def admit_source(source_id: C.SourceId) -> C.SourceId:
    """Closed registry guard. V3.4 ensemble has no member: unrepresentable."""
    if source_id not in C.SOURCE_FAMILIES:
        raise ValueError(f"source not admitted for alignment: {source_id!r}")
    return source_id


def admit_source_name(name: str) -> C.SourceId:
    """String entry point. Anything V3.4-shaped fails closed here."""
    upper = name.upper()
    if "V3_4" in upper or "ENSEMBLE" in upper:
        raise ValueError(
            f"V3.4 ensemble cannot be admitted as a comparison source: "
            f"{name!r} (convex blend of admitted lineages; would "
            f"double-count model information)")
    try:
        member = C.SourceId[name.upper()]
    except KeyError:
        raise ValueError(
            f"unknown source identifier: {name!r}") from None
    return admit_source(member)


def from_independent_binary(state_id: str, native_value: float,
                            meta: StateMeta, source_id: C.SourceId,
                            provenance: C.Provenance) -> C.NativePrediction:
    """V3.1B Logistic / V3.3 XGBoost WIN adapter (RAW pass-through)."""
    admit_source(source_id)
    if C.SOURCE_FAMILIES[source_id] is not C.SourceFamily.INDEPENDENT_BINARY:
        raise ValueError(f"not an independent-binary source: {source_id}")
    _check_meta(meta)
    return C.NativePrediction(
        state_id=state_id, race_id=meta.race_id, year=meta.year,
        round=meta.round, lap=meta.lap, stage=meta.stage,
        driver_id=meta.driver_id, source_id=source_id,
        source_family=C.SourceFamily.INDEPENDENT_BINARY,
        target=C.Target.WIN,
        native_probability=validate_probability(native_value),
        normalization_semantics=C.SOURCE_NORMALIZATION[source_id],
        support_status=C.SupportStatus.AVAILABLE, support_reason=None,
        provenance=provenance)


def from_prediction_result(result, meta_by_state_id: dict,
                           source_id: C.SourceId,
                           provenance: C.Provenance
                           ) -> tuple:
    """Adapt a frozen PredictionResult via identity-keyed metadata.

    Never positional: every state_id must resolve in meta_by_state_id.
    """
    admit_source(source_id)
    if C.SOURCE_FAMILIES[source_id] is not C.SourceFamily.INDEPENDENT_BINARY:
        raise ValueError(f"not an independent-binary source: {source_id}")
    ids = tuple(result.state_ids)
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate state ids in prediction result")
    values = [float(v) for v in list(result.values)]
    if len(values) != len(ids):
        raise ValueError("state/value length mismatch")
    out = []
    for sid, val in zip(ids, values):
        try:
            meta = meta_by_state_id[sid]
        except KeyError:
            raise ValueError(
                f"state identity without metadata: {sid!r}") from None
        out.append(from_independent_binary(sid, val, meta, source_id,
                                           provenance))
    return tuple(out)


def from_mc2_win(summary, state_id: str, meta: StateMeta,
                 provenance: C.Provenance, valid_trials: int
                 ) -> C.NativePrediction:
    """MC2 WIN adapter: native winner frequency pass-through."""
    admit_source(C.SourceId.MC2_E)
    _check_meta(meta)
    if summary.win_probability is None:
        raise ValueError("MC2 summary carries no native winner frequency")
    if not isinstance(valid_trials, int) or valid_trials <= 0:
        raise ValueError(f"invalid MC2 valid-trial count: {valid_trials!r}")
    return C.NativePrediction(
        state_id=state_id, race_id=meta.race_id, year=meta.year,
        round=meta.round, lap=meta.lap, stage=meta.stage,
        driver_id=meta.driver_id, source_id=C.SourceId.MC2_E,
        source_family=
        C.SourceFamily.MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY,
        target=C.Target.WIN,
        native_probability=validate_probability(
            summary.win_probability),
        normalization_semantics=
        C.SOURCE_NORMALIZATION[C.SourceId.MC2_E],
        support_status=C.SupportStatus.AVAILABLE, support_reason=None,
        provenance=provenance, mc_valid_trials=valid_trials)


def mc2_derived_topk(distribution: tuple, threshold: int) -> float:
    """Mechanical sum over a frozen full-field position distribution.

    DNF bucket (position None) never contributes to a top-k frequency.
    """
    if threshold not in (3, 5, 10):
        raise ValueError(f"unsupported derived threshold: {threshold!r}")
    total = 0.0
    for entry in distribution:
        pos = entry.position
        if pos is not None and 1 <= pos <= threshold:
            total += validate_probability(entry.frequency)
    return total


def from_mc2_topk(summary, state_id: str, meta: StateMeta,
                  provenance: C.Provenance, valid_trials: int,
                  threshold: int) -> C.NativePrediction:
    """MC2 derived top-k adapter, explicitly provenance-labelled."""
    admit_source(C.SourceId.MC2_E)
    _check_meta(meta)
    dist = tuple(summary.finish_position_distribution or ())
    if not dist:
        raise ValueError("MC2 summary carries no position distribution")
    target = {3: C.Target.TOP3, 5: C.Target.TOP5,
              10: C.Target.TOP10}[threshold] if threshold in (3, 5, 10) \
        else None
    if target is None:
        raise ValueError(f"unsupported derived threshold: {threshold!r}")
    if not isinstance(valid_trials, int) or valid_trials <= 0:
        raise ValueError(f"invalid MC2 valid-trial count: {valid_trials!r}")
    return C.NativePrediction(
        state_id=state_id, race_id=meta.race_id, year=meta.year,
        round=meta.round, lap=meta.lap, stage=meta.stage,
        driver_id=meta.driver_id, source_id=C.SourceId.MC2_E,
        source_family=
        C.SourceFamily.MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY,
        target=target,
        native_probability=mc2_derived_topk(dist, threshold),
        normalization_semantics=
        C.SOURCE_NORMALIZATION[C.SourceId.MC2_E],
        support_status=C.SupportStatus.AVAILABLE, support_reason=None,
        provenance=provenance, mc_valid_trials=valid_trials,
        derived_from_mc2_counts=True)


V3_5_COLUMNS = {
    C.Target.WIN: ("raw_top1", "cal_top1", "proj_top1"),
    C.Target.TOP3: ("raw_top3", "cal_top3", "proj_top3"),
    C.Target.TOP5: ("raw_top5", "cal_top5", "proj_top5"),
    C.Target.TOP10: ("raw_top10", "cal_top10", "proj_top10"),
}


def from_v35_row(row: dict, target: C.Target,
                 source_id: C.SourceId = C.SourceId.V3_5_LOGISTIC_CONTROL,
                 provenance: C.Provenance = None,
                 value_column: str = "proj") -> C.NativePrediction:
    """V3.5 marginal adapter over explicit row-dicts (never positional).

    ``value_column`` selects one of raw/cal/proj for the named target;
    the column name is explicit, never inferred from position.
    """
    admit_source(source_id)
    if C.SOURCE_FAMILIES[source_id] is not C.SourceFamily.MARGINAL_THRESHOLD:
        raise ValueError(f"not a marginal-threshold source: {source_id}")
    if target not in V3_5_COLUMNS:
        raise ValueError(f"unsupported V3.5 target: {target!r}")
    if provenance is None:
        raise ValueError("V3.5 adapter requires bound provenance")
    _forbidden_truth_scan(row)
    try:
        state_id = row["state_id"]
        meta = StateMeta(driver_id=row["driver_id"], race_id=row["race_id"],
                         year=int(row["year"]), round=int(row["round"]),
                         lap=int(row["lap"]), stage=row["stage"])
    except KeyError as exc:
        raise ValueError(f"V3.5 row missing identity key: {exc}") from None
    _check_meta(meta)
    stem = {C.Target.WIN: "top1", C.Target.TOP3: "top3",
            C.Target.TOP5: "top5", C.Target.TOP10: "top10"}[target]
    if value_column not in ("raw", "cal", "proj"):
        raise ValueError(f"unknown V3.5 value column: {value_column!r}")
    col = f"{value_column}_{stem}"
    try:
        native = row[col]
    except KeyError:
        raise ValueError(
            f"V3.5 row missing column {col!r} for {target}") from None
    return C.NativePrediction(
        state_id=state_id, race_id=meta.race_id, year=meta.year,
        round=meta.round, lap=meta.lap, stage=meta.stage,
        driver_id=meta.driver_id, source_id=source_id,
        source_family=C.SourceFamily.MARGINAL_THRESHOLD, target=target,
        native_probability=validate_probability(native),
        normalization_semantics=C.SOURCE_NORMALIZATION[source_id],
        support_status=C.SupportStatus.AVAILABLE, support_reason=None,
        provenance=provenance)


def missing_record(state_id: str, driver_id: str, source_id: C.SourceId,
                   reason: C.ReasonCode) -> dict:
    """Explicit missing-support entry. Never a zero, never a NaN."""
    admit_source(source_id)
    if not isinstance(reason, C.ReasonCode):
        raise ValueError(f"unstable reason code: {reason!r}")
    return {"state_id": state_id, "driver_id": driver_id,
            "source_id": source_id,
            "support_status": C.SupportStatus.UNAVAILABLE,
            "reason": reason}
