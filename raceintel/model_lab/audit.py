"""M0 split/task count audit (counts only, no model, no metrics).

Reads the frozen canonical matrix and reports race/state/eligibility counts
for every development fold and for the final-fit / protected-holdout
boundaries. This is dataset/protocol accounting, not model evaluation:
no prediction is produced and no metric is computed.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd

from raceintel.config import V2Paths
from raceintel.features.build_matrix import TASKS, load_matrix
from raceintel.model_lab.protocol import (
    CHRONOLOGY_KEY,
    DEVELOPMENT_FOLDS,
    EXPECTED_BINARY_ELIGIBLE,
    EXPECTED_GAIN_LOSS_ELIGIBLE,
    EXPECTED_ORDINAL_ELIGIBLE,
    EXPECTED_RACE_COUNT,
    FINAL_FIT_SEASONS,
    FULL_SEASON_RANGE,
    PROTECTED_HOLDOUT_SEASON,
    STAGE_BUCKETS,
    TASK_SPECS,
    TaskKind,
    verify_phase2_artifacts,
)


def build_race_chronology(matrix: pd.DataFrame) -> pd.DataFrame:
    """Deterministic race chronology from factual metadata only."""
    key = list(CHRONOLOGY_KEY)
    chronology = matrix[key].drop_duplicates().sort_values(key).reset_index(
        drop=True)
    if len(chronology) != EXPECTED_RACE_COUNT:
        raise ValueError(
            f"chronology has {len(chronology)} races != {EXPECTED_RACE_COUNT}")
    seasons = sorted(chronology["season"].astype(int).unique().tolist())
    if seasons != list(range(FULL_SEASON_RANGE[0], FULL_SEASON_RANGE[1] + 1)):
        raise ValueError(f"chronology seasons {seasons} != expected rich era")
    ordered = chronology.sort_values(key, kind="mergesort")
    if not ordered.equals(chronology):
        raise ValueError("chronology is not in canonical key order")
    return chronology


def _season_frame(matrix: pd.DataFrame, seasons) -> pd.DataFrame:
    return matrix[matrix["season"].astype(int).isin(list(seasons))]


def _races(frame: pd.DataFrame) -> int:
    return int(frame["race_id"].nunique())


def _task_counts(frame: pd.DataFrame, task: str) -> dict:
    spec = TASK_SPECS[task]
    mask = frame[spec.eligibility_mask].astype("boolean")
    eligible = int(mask.sum())
    out = {"eligible": eligible}
    if spec.kind is TaskKind.BINARY:
        target = frame.loc[mask.fillna(False).astype(bool), spec.label_column]
        target = target.astype("boolean")
        out["positives"] = int(target.sum())
        out["negatives"] = eligible - out["positives"]
        out["positive_rate"] = (round(out["positives"] / eligible, 6)
                                if eligible else None)
    else:
        target = frame.loc[mask.fillna(False).astype(bool), spec.label_column]
        out["coverage"] = int(target.notna().sum())
        if out["coverage"]:
            out["min"] = int(target.min())
            out["max"] = int(target.max())
        else:
            out["min"] = None
            out["max"] = None
    return out


def _split_record(name: str, train: pd.DataFrame, validation: pd.DataFrame,
                  train_seasons, validation_season) -> dict:
    return {
        "fold_id": name,
        "train_seasons": list(train_seasons),
        "validation_season": validation_season,
        "train_races": _races(train),
        "validation_races": _races(validation),
        "train_states": int(len(train)),
        "validation_states": int(len(validation)),
        "train_tasks": {task: _task_counts(train, task) for task in TASKS},
        "validation_tasks": {
            task: _task_counts(validation, task) for task in TASKS},
    }


def audit_development_folds(matrix: pd.DataFrame) -> list:
    folds = []
    for fold in DEVELOPMENT_FOLDS:
        train = _season_frame(matrix, fold.train_seasons)
        validation = _season_frame(matrix, [fold.validation_season])
        record = _split_record(
            fold.fold_id, train, validation, fold.train_seasons,
            fold.validation_season)
        # Programmatic no-future-leakage assertion (race chronology).
        train_max = train["season"].astype(int).max()
        if train_max >= fold.validation_season:
            raise ValueError(
                f"{fold.fold_id}: max train season {train_max} >= validation "
                f"{fold.validation_season}")
        if PROTECTED_HOLDOUT_SEASON in set(train["season"].astype(int)):
            raise ValueError(f"{fold.fold_id}: holdout leaked into training")
        if PROTECTED_HOLDOUT_SEASON in set(
                validation["season"].astype(int)):
            raise ValueError(f"{fold.fold_id}: holdout used as validation")
        folds.append(record)
    return folds


def audit_final_boundaries(matrix: pd.DataFrame) -> dict:
    final_fit = _season_frame(matrix, FINAL_FIT_SEASONS)
    holdout = _season_frame(matrix, [PROTECTED_HOLDOUT_SEASON])
    return {
        "final_fit_seasons": list(FINAL_FIT_SEASONS),
        "final_fit_races": _races(final_fit),
        "final_fit_states": int(len(final_fit)),
        "holdout_season": PROTECTED_HOLDOUT_SEASON,
        "holdout_races": _races(holdout),
        "holdout_states": int(len(holdout)),
    }


def audit_stage_buckets(matrix: pd.DataFrame) -> dict:
    frac = matrix["race_progress_frac"]
    if frac.isna().any():
        raise ValueError("race_progress_frac contains nulls")
    counts = {}
    for name, lo, hi in STAGE_BUCKETS:
        if name == "LATE":
            sel = (frac >= lo) & (frac <= hi)
        else:
            sel = (frac >= lo) & (frac < hi)
        counts[name] = int(sel.sum())
    counts["total"] = int(sum(counts.values()))
    return counts


def audit_task_eligibility(matrix: pd.DataFrame) -> dict:
    out = {}
    for task, spec in TASK_SPECS.items():
        if spec.tier.value == "DEFERRED":
            continue
        out[task] = _task_counts(matrix, task)
    return out


def dependency_availability() -> dict:
    """Record whether a candidate dependency is importable (no import run)."""
    from raceintel.model_lab.protocol import CANDIDATES
    modules = sorted({c.dependency.split(" ")[0].split("/")[0]
                      for c in CANDIDATES})
    return {m: bool(importlib.util.find_spec(m)) for m in modules}


def run_audit(paths: V2Paths | None = None, *,
              verify_content_hash: bool = False) -> dict:
    """Full M0 audit: Phase-2 freeze + chronology + split/task counts."""
    paths = paths or V2Paths.resolve()
    freeze = verify_phase2_artifacts(
        paths, verify_content_hash=verify_content_hash)
    matrix, manifest = load_matrix(paths)
    chronology = build_race_chronology(matrix)
    total_states = int(len(matrix))
    # Sanity: expected masks overall (independent of any fold).
    ordinal = int(matrix["eligible_ordinal_final_position"].astype(
        "boolean").sum())
    gain_loss = int(matrix["eligible_gain_loss"].astype("boolean").sum())
    binary = int(matrix["eligible_is_winner"].astype("boolean").sum())
    if ordinal != EXPECTED_ORDINAL_ELIGIBLE:
        raise ValueError(f"ordinal eligible {ordinal} != {EXPECTED_ORDINAL_ELIGIBLE}")
    if gain_loss != EXPECTED_GAIN_LOSS_ELIGIBLE:
        raise ValueError(
            f"gain/loss eligible {gain_loss} != {EXPECTED_GAIN_LOSS_ELIGIBLE}")
    if binary != EXPECTED_BINARY_ELIGIBLE:
        raise ValueError(
            f"binary eligible {binary} != {EXPECTED_BINARY_ELIGIBLE}")
    return {
        "protocol": "MODEL_LAB_PROTOCOL_v1",
        "phase2_freeze": freeze,
        "chronology": {
            "key": list(CHRONOLOGY_KEY),
            "races": int(len(chronology)),
            "seasons": sorted(
                chronology["season"].astype(int).unique().tolist()),
        },
        "totals": {
            "states": total_states,
            "races": int(matrix["race_id"].nunique()),
            "ordinal_eligible": ordinal,
            "gain_loss_eligible": gain_loss,
            "binary_eligible": binary,
        },
        "development_folds": audit_development_folds(matrix),
        "final_boundaries": audit_final_boundaries(matrix),
        "stage_buckets": audit_stage_buckets(matrix),
        "task_eligibility_total": audit_task_eligibility(matrix),
        "dependency_availability": dependency_availability(),
        "note": "counts only; no model and no metric",
    }


def render_audit(audit: dict) -> str:
    return json.dumps(audit, indent=2, sort_keys=True) + "\n"


def write_audit(audit: dict, path: str | Path) -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_audit(audit))
    return dest


def main(argv: list | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m raceintel.model_lab.audit",
        description="M0 split/task count audit (counts only, no model)")
    parser.add_argument("--root", default=None)
    parser.add_argument("--json", default=None)
    parser.add_argument("--verify-content-hash", action="store_true")
    args = parser.parse_args(argv)
    paths = V2Paths.resolve(args.root) if args.root else V2Paths.resolve()
    audit = run_audit(paths, verify_content_hash=args.verify_content_hash)
    if args.json:
        write_audit(audit, args.json)
        print(f"wrote {args.json}")
    else:
        print(render_audit(audit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
