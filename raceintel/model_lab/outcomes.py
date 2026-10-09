"""V3.5 canonical outcome-threshold targets + coherence projection.

Research data layer only: no model fitting, no learned parameters, no
predictions. Reads frozen D9 label artifacts (2018-2024 development only;
2025 fails closed) and the frozen canonical state matrix identity.

Target contract v3.5b-target-v1 / status v3.5b-status-v1 /
population v3.5b-population-v1 / projection v3.5b-projection-v1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from raceintel.model_lab.errors import ProtectedHoldoutError
from raceintel.model_lab.protocol import PROTECTED_HOLDOUT_SEASON

TARGET_CONTRACT_VERSION = "v3.5b-target-v1"
STATUS_POLICY_VERSION = "v3.5b-status-v1"
POPULATION_POLICY_VERSION = "v3.5b-population-v1"
PROJECTION_POLICY_VERSION = "v3.5b-projection-v1"

#: Frozen cumulative thresholds (finish position <= K), ascending.
THRESHOLD_ORDER: tuple[int, ...] = (1, 3, 5, 10)

#: Canonical binary target names, same order as THRESHOLD_ORDER.
TARGET_NAMES: tuple[str, ...] = ("is_top1", "is_top3", "is_top5", "is_top10")

#: Product aliases (top1 -> win, top3 -> podium).
TARGET_ALIASES: dict[str, str] = {"is_top1": "p_win", "is_top3": "p_podium",
                                  "is_top5": "p_top5", "is_top10": "p_top10"}

#: Reverse alias lookup.
ALIAS_TARGETS: dict[str, str] = {v: k for k, v in TARGET_ALIASES.items()}

#: Raw vs projected probability semantics (frozen terminology).
RAW_SEMANTICS = "RAW"
PROJECTED_SEMANTICS = "PROJECTED_COHERENT"

#: Outcome semantic tags (metadata only; never predictive features).
SEM_CLASSIFIED = "CLASSIFIED_POSITION"
SEM_UNCLASSIFIED_TAIL = "UNCLASSIFIED_TAIL"
SEM_WITHDRAWN_NO_RESULT = "WITHDRAWN_NO_RESULT"

#: Seasons the V3.5 development layer may touch. Anything else fails closed.
ALLOWED_SEASONS: tuple[int, ...] = (2018, 2019, 2020, 2021, 2022, 2023, 2024)

#: position_text tokens with known handling. Anything else fails closed.
KNOWN_POSITION_TOKENS = frozenset(
    {str(k) for k in range(1, 21)} | {"R", "W", "D"})


def assert_development_seasons(seasons) -> tuple[int, ...]:
    """Fail closed unless every requested season is allowed development."""
    req = tuple(int(s) for s in seasons)
    bad = [s for s in req if s not in ALLOWED_SEASONS]
    if bad:
        raise ProtectedHoldoutError(
            f"V3.5 development seasons {ALLOWED_SEASONS}; refused {sorted(set(bad))} "
            f"(protected holdout {PROTECTED_HOLDOUT_SEASON} sealed)")
    return req


def load_development_labels(seasons=None) -> pd.DataFrame:
    """Concatenated frozen D9 label rows for allowed seasons (read-only)."""
    from raceintel.pipeline import d9 as D9

    seasons = assert_development_seasons(
        ALLOWED_SEASONS if seasons is None else seasons)
    parts = [D9.read_d9_label_season(
        __import__("raceintel.config", fromlist=["V2Paths"]).V2Paths.resolve(),
        int(s)) for s in seasons]
    out = pd.concat(parts, ignore_index=True)
    if (out["season"].astype(int) == PROTECTED_HOLDOUT_SEASON).any():
        raise ProtectedHoldoutError("2025 label rows reached V3.5 loader")
    return out


def classify_outcome_row(position_text, classified_flag,
                         position_final) -> str:
    """Outcome semantic tag for one result row. Fail closed on unknown shape.

    CLASSIFIED_POSITION: earned official slot (threshold labels compare
    position_final <= K). UNCLASSIFIED_TAIL: source back-rank ordering with
    no earned slot (all threshold labels 0 by policy, never by numeric
    comparison). WITHDRAWN_NO_RESULT: null final (never started; 0 laps).
    """
    tok = str(position_text)
    if tok not in KNOWN_POSITION_TOKENS:
        raise ValueError(f"unknown position_text token: {tok!r}")
    pos_null = position_final is None or (
        not isinstance(position_final, str) and pd.isna(position_final))
    if bool(classified_flag):
        if pos_null or tok in ("R", "W", "D"):
            raise ValueError(
                f"classified row with non-earned shape: token={tok!r}")
        return SEM_CLASSIFIED
    if pos_null:
        return SEM_WITHDRAWN_NO_RESULT
    return SEM_UNCLASSIFIED_TAIL


def build_outcome_frame(labels: pd.DataFrame) -> pd.DataFrame:
    """(race_id, driver_id)-grain threshold targets + semantic tags.

    y_topK = classified AND position_final <= K. Unclassified rows are 0 by
    policy (back-rank numerics never interpreted as earned slots); null-final
    withdrawals are 0 (did not finish <= K). Duplicate keys or unknown shapes
    raise (fail closed).
    """
    need = {"race_id", "driver_id", "position_final", "classified_position",
            "position_text", "status_text", "points"}
    missing = [c for c in need if c not in labels.columns]
    if missing:
        raise ValueError(f"label frame missing columns: {sorted(missing)}")
    keys = ["race_id", "driver_id"]
    if bool(labels.duplicated(keys).any()):
        raise ValueError("duplicate (race_id, driver_id) outcome keys")
    frame = labels.sort_values(keys, kind="mergesort").reset_index(drop=True)
    classified = frame["classified_position"].notna().to_numpy()
    pos = pd.to_numeric(frame["position_final"], errors="coerce").to_numpy()
    toks = frame["position_text"].astype(str).to_numpy()
    sems = [classify_outcome_row(t, c, p) for t, c, p in
            zip(toks, classified, pos)]
    out = pd.DataFrame({"race_id": frame["race_id"].astype(str).to_numpy(),
                        "driver_id": frame["driver_id"].astype(str).to_numpy(),
                        "outcome_semantic": sems,
                        "position_final": pos,
                        "points": pd.to_numeric(
                            frame["points"], errors="coerce").to_numpy(float),
                        "status_text": frame["status_text"].astype(str).to_numpy()})
    earn = np.array([s == SEM_CLASSIFIED for s in sems])
    for name, k in zip(TARGET_NAMES, THRESHOLD_ORDER):
        out[name] = (earn & (pos <= k)).astype(np.int8)
    return out


def expand_to_states(outcomes: pd.DataFrame,
                     states: pd.DataFrame) -> pd.DataFrame:
    """Identity-join outcome targets onto state rows. Never positional.

    states must carry state_id/race_id/season/driver_id. Every state must
    match exactly one outcome; outcomes without states (DNS/never-started)
    are reported, never fabricated. Extra states without outcomes raise.
    """
    for col in ("state_id", "race_id", "season", "driver_id"):
        if col not in states.columns:
            raise ValueError(f"states missing identity column: {col}")
    if not states["state_id"].is_unique:
        raise ValueError("duplicate state_id in state population")
    left = states[["state_id", "race_id", "season", "driver_id"]].copy()
    left["race_id"] = left["race_id"].astype(str)
    left["driver_id"] = left["driver_id"].astype(str)
    right = outcomes[["race_id", "driver_id", "outcome_semantic",
                      *TARGET_NAMES]].copy()
    merged = left.merge(right, on=["race_id", "driver_id"],
                        how="left", validate="many_to_one")
    missing = merged[list(TARGET_NAMES)].isna().any(axis=1)
    if bool(missing.any()):
        bad = merged.loc[missing, ["state_id", "race_id", "driver_id"]]
        raise ValueError(
            f"{int(missing.sum())} states without outcomes, e.g. "
            f"{bad.head(3).to_dict('records')}")
    for name in TARGET_NAMES:
        merged[name] = merged[name].astype(np.int8)
    return merged


# ---------------------------------------------------------------------------
# Isotonic coherence projection (v3.5b-projection-v1).
# ---------------------------------------------------------------------------

def _pava_equal_weights(values: np.ndarray) -> np.ndarray:
    """Least-squares nondecreasing fit (Pool Adjacent Violators, equal w)."""
    vals = [float(v) for v in values]
    sol = [[v, 1] for v in vals]  # (block mean, block weight)
    i = 0
    while i < len(sol) - 1:
        if sol[i][0] <= sol[i + 1][0]:
            i += 1
            continue
        m0, w0 = sol[i]
        m1, w1 = sol[i + 1]
        sol[i] = [((m0 * w0) + (m1 * w1)) / (w0 + w1), w0 + w1]
        del sol[i + 1]
        if i > 0:
            i -= 1
    out = []
    for mean, weight in sol:
        out.extend([mean] * weight)
    return np.array(out, dtype=float)


def project_isotonic(prob) -> tuple[np.ndarray, dict]:
    """Project threshold probabilities onto 0 <= q1<=q3<=q5<=q10 <= 1.

    Least-squares isotonic projection (equal weights) over the frozen input
    order [top1, top3, top5, top10]. Inputs must be finite probabilities in
    [0, 1]; NaN/Inf/out-of-bounds raise. Deterministic, no fitting, no state.
    Returns (projected, diagnostics) with violation/adjustment magnitudes.
    Isotonic means of [0,1] values stay in [0,1]; outputs are clipped only as
    a floating-point guard.
    """
    arr = np.asarray(prob, dtype=float)
    single = arr.ndim == 1
    mat = arr.reshape(1, -1) if single else arr
    if mat.shape[1] != len(THRESHOLD_ORDER):
        raise ValueError(
            f"projection needs {len(THRESHOLD_ORDER)} thresholds, got {mat.shape[1]}")
    if not np.all(np.isfinite(mat)):
        raise ValueError("projection rejects NaN/Inf inputs")
    if np.any((mat < 0.0) | (mat > 1.0)):
        raise ValueError("projection rejects probabilities outside [0,1]")
    rows = np.vstack([_pava_equal_weights(row) for row in mat])
    rows = np.clip(rows, 0.0, 1.0)
    violated = np.any(np.diff(mat, axis=1) < 0.0, axis=1)
    abs_adj = np.abs(rows - mat)
    diag = {"n_rows": int(mat.shape[0]),
            "n_violated_before": int(violated.sum()),
            "frac_violated_before": float(violated.mean()),
            "mean_abs_adjustment": float(abs_adj.mean()),
            "max_abs_adjustment": float(abs_adj.max()),
            "per_threshold_mean_abs_adjustment": {
                name: float(abs_adj[:, j].mean())
                for j, name in enumerate(TARGET_NAMES)}}
    return (rows[0] if single else rows), diag


def derived_bands(coherent) -> np.ndarray:
    """Threshold-differenced outcome bands (diagnostic, not P1-P20).

    Bands: P(P1), P(P2-P3), P(P4-P5), P(P6-P10), P(>P10). Requires coherent
    (nondecreasing, [0,1]) inputs; outputs are nonnegative and sum to 1.
    """
    q = np.asarray(coherent, dtype=float)
    if q.ndim == 1:
        q = q.reshape(1, -1)
    if q.shape[1] != len(THRESHOLD_ORDER):
        raise ValueError("bands need 4 coherent thresholds")
    if not np.all(np.isfinite(q)) or np.any((q < 0.0) | (q > 1.0)):
        raise ValueError("bands reject non-probability inputs")
    if np.any(np.diff(q, axis=1) < -1e-12):
        raise ValueError("bands require coherent (nondecreasing) inputs")
    bands = np.zeros((q.shape[0], 5))
    bands[:, 0] = q[:, 0]
    bands[:, 1] = q[:, 1] - q[:, 0]
    bands[:, 2] = q[:, 2] - q[:, 1]
    bands[:, 3] = q[:, 3] - q[:, 2]
    bands[:, 4] = 1.0 - q[:, 3]
    bands = np.clip(bands, 0.0, 1.0)
    if np.any(bands < -1e-12):
        raise ValueError("negative outcome band")
    sums = bands.sum(axis=1)
    if not np.all(np.abs(sums - 1.0) < 1e-9):
        raise ValueError("outcome bands do not sum to 1")
    return bands[0] if np.asarray(coherent).ndim == 1 else bands
