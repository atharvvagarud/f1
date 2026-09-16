"""M7 boundary-resolution CLI (LogReg only; development folds only).

Runs the one-time Logistic Regression regularization boundary study over
D1/D2/D3, writes the machine-readable M7 artifact
(``logreg_boundary_resolution_v1.json``) and optionally renders the
human-readable report from it. The protected 2025 holdout has no CLI path
here, ExtraTrees/other families cannot be selected, and the C grid is fixed.
"""

from __future__ import annotations

import json

from v2.model_lab import experiment as EX
from v2.model_lab import logreg_boundary as BOUND
from v2.model_lab import results as RES
from v2.model_lab.errors import ExperimentConfigError


def main(argv: list | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m v2.model_lab.run_boundary",
        description="Run the M7 LogReg boundary resolution (D1/D2/D3 only)")
    parser.add_argument("--task", default=BOUND.M7_TASK)
    parser.add_argument("--folds", default="D1,D2,D3")
    parser.add_argument("--feature-set", default=BOUND.M7_FEATURE_SET)
    parser.add_argument("--seed", type=int, default=EX.PROJECT_SEED)
    parser.add_argument("--root", default=None,
                        help="alternate experiment tree root (debugging)")
    parser.add_argument("--out", default=None,
                        help="M7 artifact path; default "
                             "data/v2/model_lab/reports/"
                             "logreg_boundary_resolution_v1.json")
    parser.add_argument("--render-report", default=None,
                        help="write human-readable markdown rendered from the "
                             "stored M7 artifact")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the planned fit budget; execute nothing")
    args = parser.parse_args(argv)

    folds = tuple(s.strip() for s in str(args.folds).split(",") if s.strip())
    if args.task != BOUND.M7_TASK:
        raise ExperimentConfigError(
            f"M7 resolves task {BOUND.M7_TASK!r} only; got {args.task!r}")
    if args.feature_set != BOUND.M7_FEATURE_SET:
        raise ExperimentConfigError(
            f"M7 uses feature set {BOUND.M7_FEATURE_SET!r} only; got "
            f"{args.feature_set!r}")
    if args.seed != BOUND.M7_SEED:
        raise ExperimentConfigError(
            f"M7 uses seed {BOUND.M7_SEED!r} only; got {args.seed!r}")

    if args.dry_run:
        planned = BOUND.planned_fit_count(folds)
        for fold, node in planned["per_fold"].items():
            print(f"{fold}: {node['configs']} C values x "
                  f"{node['inner_folds']} inner folds = "
                  f"{node['estimator_fits']} inner estimator fits")
        print(f"inner estimator fits: {planned['inner_estimator_fits']}")
        print(f"inner preprocessor fits: {planned['inner_preprocessor_fits']}")
        print(f"outer selected refits: {planned['outer_selected_refits']}")
        print(f"determinism refits: {planned['determinism_refits']}")
        print(f"total planned estimator fits: "
              f"{planned['total_estimator_fits']}")
        print("dry-run: nothing executed")
        return 0

    summary = BOUND.run_boundary_suite(
        task=args.task, folds=folds, feature_set=args.feature_set,
        seed=args.seed, root=args.root, out=args.out)
    print(f"M7 artifact: {summary['_summary_path']}")
    print(f"selected C per fold: {summary['selected_c_per_fold']}")
    print(f"boundary status: {summary['boundary_status']['status']}")
    print(f"global C: "
          f"{summary['global_configuration']['decision']['global_c']}")
    print(f"total_seconds: {summary['runtime']['total_seconds']:.1f}")

    if args.render_report:
        with open(summary["_summary_path"], encoding="utf-8") as fh:
            stored = json.load(fh)
        stored["_summary_path"] = summary["_summary_path"]
        RES.atomic_write_text(args.render_report,
                              BOUND.render_boundary_report(stored))
        print(f"report: {args.render_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
