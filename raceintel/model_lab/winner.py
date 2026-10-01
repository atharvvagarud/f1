"""Synchronized race-level winner top-k evaluation.

Reuses the Phase-2 ``RaceIndex`` synchronization semantics (latest rival
state with ``state_time_s <= T``) — never naive same-lap comparison. This is
the smallest read-only adapter required to evaluate winner top-1/top-3 at
synchronized race states. Development folds run without opt-in; the
protected 2025 holdout was evaluated exactly once by the sanctioned M9 run
and is now mechanically sealed against re-evaluation.
"""

from __future__ import annotations

import numpy as np

from raceintel.features.temporal import RaceIndex
from raceintel.model_lab.data import CanonicalMatrix
from raceintel.model_lab.errors import (
    InvalidPredictionError,
    ProtectedHoldoutError,
)
from raceintel.model_lab.predictions import PredictionKind, PredictionResult
from raceintel.model_lab.protocol import PROTECTED_HOLDOUT_SEASON

_WINNER_COLUMNS = ("race_id", "season", "driver_id", "lap_number",
                   "state_time_s", "state_id", "is_winner")


def synchronized_winner_top_k(predictions: PredictionResult,
                               canonical: CanonicalMatrix, *,
                               race_ids=None, top_k=(1, 3),
                               max_eval_per_race: int | None = None,
                               allow_protected_holdout: bool = False) -> dict:
    """Winner top-k at synchronized race states (development by default).

    Eligibility contract (M1.1): a synchronized snapshot at time ``T``
    (latest state per driver with ``state_time_s <= T`` — unchanged
    RaceIndex semantics, no same-lap fallback, no future state, no
    retirement inference, lapped/stale drivers kept) is *eligible* only
    when (a) the eventual winner has an observable state with a prediction
    at ``T`` AND (b) at least 2 drivers are observable with predictions
    (a ranking needs a field; a single observable driver makes top-1
    trivial). Snapshots with no predictions, an unobservable winner, or a
    1-driver field are skipped and counted separately
    (``n_skipped_no_predictions`` / ``n_skipped_winner_unobservable`` /
    ``n_skipped_degenerate``). Observable field size and the factual roster
    size are reported so coverage (observable / roster) is explicit.

    Caveat for M2: headline top-k accuracies share the eligible denominator;
    a strict k-way discrimination claim additionally requires
    observable_field_size >= k — check ``min_observable_field_size``
    (a 2-driver field cannot discriminate top-3).
    """
    if predictions.kind is not PredictionKind.BINARY_PROBABILITY:
        raise InvalidPredictionError(
            "winner top-k requires BINARY_PROBABILITY predictions; got "
            f"{predictions.kind.value}")

    base = canonical.frame[list(_WINNER_COLUMNS)].copy()
    if race_ids is not None:
        allowed = set(str(r) for r in race_ids)
        base = base.loc[base["race_id"].astype(str).isin(allowed)]

    seasons = base["season"].astype(int)
    if not allow_protected_holdout and \
            (seasons == PROTECTED_HOLDOUT_SEASON).any():
        raise ProtectedHoldoutError(
            "winner top-k would touch the protected 2025 holdout; pass "
            "allow_protected_holdout=True only for the final locked run")

    prob_by_state = dict(zip(predictions.state_ids,
                             (float(v) for v in predictions.values)))

    max_k = max(top_k)
    hits = {f"top{k}": 0 for k in top_k}
    n_states = 0
    n_skipped_no_predictions = 0
    n_skipped_winner_unobservable = 0
    n_skipped_degenerate = 0
    observable_sizes: list = []
    per_race = {}
    race_list = sorted(base["race_id"].astype(str).unique())

    for race_id in race_list:
        sub = base.loc[base["race_id"].astype(str) == race_id]
        if sub.empty:
            continue
        winners = set(sub.loc[
            sub["is_winner"].astype("boolean").fillna(False).astype(bool),
            "driver_id"].astype(str))
        roster = sorted(sub["driver_id"].astype(str).unique())
        index = RaceIndex(sub[list(("race_id", "driver_id", "lap_number",
                                    "state_time_s", "state_id"))])
        rows = sub.sort_values(["state_time_s", "lap_number", "driver_id"],
                               kind="mergesort")
        if max_eval_per_race is not None and \
                len(rows) > max_eval_per_race:
            stride = int(np.ceil(len(rows) / max_eval_per_race))
            rows = rows.iloc[::stride]
        race_hits = {f"top{k}": 0 for k in top_k}
        race_n = 0
        race_skipped_no_predictions = 0
        race_skipped_winner_unobservable = 0
        race_skipped_degenerate = 0
        race_observable_sizes: list = []
        for row in rows.itertuples(index=False):
            T = float(row.state_time_s)
            scored = []
            for driver in roster:
                state = index.sync_lookup(race_id, driver, T)
                if not state.observable:
                    continue
                state_id = state.values.get("state_id")
                probability = prob_by_state.get(state_id)
                if probability is None:
                    continue
                scored.append((probability, driver))
            if not scored:
                race_skipped_no_predictions += 1
                continue
            observable_drivers = {driver for _, driver in scored}
            if not (observable_drivers & winners):
                race_skipped_winner_unobservable += 1
                continue
            if len(scored) < 2:
                race_skipped_degenerate += 1
                continue
            scored.sort(key=lambda item: (-item[0], item[1]))
            ranked = [driver for _, driver in scored]
            race_n += 1
            race_observable_sizes.append(len(scored))
            for k in top_k:
                if any(w in ranked[:k] for w in winners):
                    race_hits[f"top{k}"] += 1
                    hits[f"top{k}"] += 1
        n_states += race_n
        n_skipped_no_predictions += race_skipped_no_predictions
        n_skipped_winner_unobservable += race_skipped_winner_unobservable
        n_skipped_degenerate += race_skipped_degenerate
        observable_sizes.extend(race_observable_sizes)
        per_race[race_id] = {
            "n_evaluation_states": race_n,
            "hits": race_hits,
            "accuracy": {key: (race_hits[key] / race_n if race_n else None)
                         for key in race_hits},
            "winner": sorted(winners),
            "roster_size": len(roster),
            "n_skipped_no_predictions": race_skipped_no_predictions,
            "n_skipped_winner_unobservable":
                race_skipped_winner_unobservable,
            "n_skipped_degenerate": race_skipped_degenerate,
            "min_observable_field_size": (
                min(race_observable_sizes) if race_observable_sizes else None),
        }

    return {
        "top_k": list(top_k),
        "n_evaluation_states": n_states,
        "n_races": len(per_race),
        "hits": hits,
        "accuracy": {key: (hits[key] / n_states if n_states else None)
                     for key in hits},
        "per_race": per_race,
        "max_k": max_k,
        "n_skipped_no_predictions": n_skipped_no_predictions,
        "n_skipped_winner_unobservable": n_skipped_winner_unobservable,
        "n_skipped_degenerate": n_skipped_degenerate,
        "min_observable_field_size": (
            min(observable_sizes) if observable_sizes else None),
        "mean_observable_field_size": (
            float(sum(observable_sizes) / len(observable_sizes))
            if observable_sizes else None),
    }
