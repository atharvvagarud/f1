"""M8 calibration-selection CLI (LogReg base; development folds only).

Runs the three-fold development calibration evaluation, writes the
machine-readable M8 artifact (``calibration_selection_v1.json``) and
optionally renders the human-readable report from it. There is no path to the
protected 2025 holdout, the base model is the frozen M7 ``C=0.01`` LogReg, and
no base-model retuning is possible here.
"""

from __future__ import annotations

import json

from v2.model_lab import calibration_selection as CS
from v2.model_lab import results as RES
from v2.model_lab.errors import ExperimentConfigError


def main(argv: list | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m v2.model_lab.run_calibration",
        description="Run the M8 calibration evaluation (D1/D2/D3 only)")
    parser.add_argument("--task", default=CS.M8_TASK)
    parser.add_argument("--folds", default="D1,D2,D3")
    parser.add_argument("--feature-set", default=CS.M8_FEATURE_SET)
    parser.add_argument("--seed", type=int, default=CS.M8_SEED)
    parser.add_argument("--root", default=None,
                        help="alternate experiment tree root (debugging)")
    parser.add_argument("--out", default=None,
                        help="M8 artifact path; default "
                             "data/v2/model_lab/reports/"
                             "calibration_selection_v1.json")
    parser.add_argument("--render-report", default=None,
                        help="write markdown rendered from the stored artifact")
    parser.add_argument("--no-bootstrap", action="store_true",
                        help="skip the optional race-level bootstrap")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the temporal design; execute nothing")
    args = parser.parse_args(argv)

    folds = tuple(s.strip() for s in str(args.folds).split(",") if s.strip())
    if args.task != CS.M8_TASK:
        raise ExperimentConfigError(
            f"M8 evaluates task {CS.M8_TASK!r} only; got {args.task!r}")
    if args.feature_set != CS.M8_FEATURE_SET:
        raise ExperimentConfigError(
            f"M8 uses feature set {CS.M8_FEATURE_SET!r} only; got "
            f"{args.feature_set!r}")
    if args.seed != CS.M8_SEED:
        raise ExperimentConfigError(
            f"M8 uses seed {CS.M8_SEED!r} only; got {args.seed!r}")

    if args.dry_run:
        for fold in folds:
            split = CS.resolve_calibration_split(fold)
            print(f"{fold}: base {split.base_seasons} | calibration "
                  f"{split.calibration_seasons} | evaluation "
                  f"{split.evaluation_seasons}")
        print(f"base C={CS.FROZEN_C}; methods={list(CS.METHODS)}; "
              f"platt_epsilon={CS.PLATT_EPSILON}")
        print("dry-run: nothing executed")
        return 0

    summary = CS.run_calibration_suite(
        task=args.task, folds=folds, feature_set=args.feature_set,
        seed=args.seed, root=args.root, out=args.out,
        bootstrap=not args.no_bootstrap)
    print(f"M8 artifact: {summary['_summary_path']}")
    print(f"selected method: "
          f"{summary['method_comparison']['selection']['selected_method']}")
    for method in CS.METHODS:
        mean = summary["aggregate"][method]["race_macro_log_loss"]["mean"]
        print(f"  {method}: mean race-macro log loss = {mean}")
    print(f"total_seconds: {summary['runtime']['total_seconds']:.1f}")

    if args.render_report:
        with open(summary["_summary_path"], encoding="utf-8") as fh:
            stored = json.load(fh)
        stored["_summary_path"] = summary["_summary_path"]
        RES.atomic_write_text(args.render_report,
                              CS.render_calibration_report(stored))
        print(f"report: {args.render_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
