"""F13 canonical label builder + future F15 join contract.

Reads the FROZEN race-driver label artifact (never Phase-1 mutation,
never feature access) and emits the validated canonical contract at
(race_id, driver_id) grain. State-dependent targets exist here ONLY as
pure specified formulas; F13 materializes no lap-level label matrix.

Direction is fixed:

    RESULTS / LABEL SOURCE  ->  LABEL BUILDER  ->  canonical frame

Feature computation never receives label values (pinned by test).
"""

from __future__ import annotations

import pandas as pd

from raceintel.labels.contracts import LABEL_GRAIN, LABEL_SET_VERSION

#: Frozen source column -> canonical contract name. Verbatim
#: passthrough; the derivation lives frozen in v2/d9.py
#: labels_from_results and is referenced, never reimplemented.
CANONICAL_COLUMN_MAP: dict[str, str] = {
    "winner_flag": "is_winner",
    "podium_flag": "is_podium",
    "points_finish_flag": "scored_points",
    "position_final": "final_position",
}

#: Eligibility companion (not a target): classification evidence for
#: conditioning ordinal/ranking use of final_position.
COMPANION_COLUMNS: tuple[str, ...] = ("classified_flag",)


def _is_null(value) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) \
        or (not isinstance(value, (str, bool)) and pd.isna(value))


def ordinal_training_eligible(classified_flag, position_final):
    """SPECIFIED eligibility helper (F14 verification scope).

    Distinguishes factual source ordering from ordinal-training
    eligibility: W/D back-rank numerics (classified_flag False) are
    factual source orderings but NOT valid classified finishes.
    Phase 3 conditions ordinal/ranking use on this, never on
    non-null final_position alone. Does not alter any label value.
    """
    if _is_null(classified_flag):
        return None
    if not bool(classified_flag):
        return False
    return not _is_null(position_final)


def position_change_from_state(current_position, final_position):
    """SPECIFIED state-dependent formula (F15 materializes).

    current_position - final_position; null-propagating; ties -> 0
    (never null when both inputs present). Not an overtake measure.
    """
    if _is_null(current_position) or _is_null(final_position):
        return None
    return int(current_position) - int(final_position)


def gains_position_by_finish(current_position, final_position):
    """SPECIFIED: eventual net gain vs state (difference > 0)."""
    change = position_change_from_state(current_position, final_position)
    if change is None:
        return None
    return bool(change > 0)


def loses_position_by_finish(current_position, final_position):
    """SPECIFIED: eventual net loss vs state (difference < 0)."""
    change = position_change_from_state(current_position, final_position)
    if change is None:
        return None
    return bool(change < 0)


def build_label_frame(labels_df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Validate the frozen label artifact and emit the canonical frame.

    Returns (frame, manifest). Raises on duplicate keys, missing source
    columns, or winner-cardinality violation (exactly one non-null
    winner per race). Deterministic: sorted by (race_id, driver_id).
    """
    missing = [c for c in list(CANONICAL_COLUMN_MAP)
               + ["position_final", "race_id", "driver_id"]
               if c not in labels_df.columns]
    if missing:
        raise ValueError(f"label source missing columns: {sorted(missing)}")
    keys = list(LABEL_GRAIN)
    if bool(labels_df.duplicated(keys).any()):
        raise ValueError("duplicate (race_id, driver_id) label keys")
    frame = labels_df[keys].copy()
    for src, dst in CANONICAL_COLUMN_MAP.items():
        frame[dst] = labels_df[src]
    for companion in COMPANION_COLUMNS:
        if companion in labels_df.columns:
            frame[companion] = labels_df[companion]
    winners = frame[frame["is_winner"] == True]  # noqa: E712
    per_race = winners.groupby("race_id").size()
    bad = per_race[per_race != 1]
    if len(bad):
        raise ValueError(
            f"winner cardinality violation: {bad.to_dict()}")
    frame = frame.sort_values(list(keys), kind="mergesort")
    frame = frame.reset_index(drop=True)
    manifest = {
        "label_set_version": LABEL_SET_VERSION,
        "grain": list(keys),
        "race_driver_rows": int(len(frame)),
        "races": int(frame["race_id"].nunique()),
        "drivers": int(frame["driver_id"].nunique()),
        "winner_true": int((frame["is_winner"] == True).sum()),  # noqa: E712
        "podium_true": int((frame["is_podium"] == True).sum()),  # noqa: E712
        "points_true": int((frame["scored_points"] == True).sum()),  # noqa: E712
        "final_null": int(frame["final_position"].isna().sum()),
    }
    return frame, manifest


def join_labels_for_f15(states_df: pd.DataFrame,
                        label_frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """FUTURE F15 join contract (many feature states -> one label row).

    Left join on (race_id, driver_id); feature identity/row count
    preserved; labels constant within race-driver; missing labels
    explicit (indicator). Presentation-identity joins forbidden by
    construction (keys only).
    """
    keys = list(LABEL_GRAIN)
    if bool(label_frame.duplicated(keys).any()):
        raise ValueError("label key must be unique for many-to-one join")
    before = len(states_df)
    out = states_df.merge(label_frame, on=keys, how="left",
                          indicator="_label_match", validate="many_to_one")
    assert len(out) == before, "left join must preserve feature row count"
    report = {
        "feature_rows": int(before),
        "matched": int((out["_label_match"] == "both").sum()),
        "missing_label": int((out["_label_match"] == "left_only").sum()),
    }
    return out.drop(columns=["_label_match"]), report
