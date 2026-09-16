"""M2 baseline-suite CLI (development folds only; no holdout option).

Runs the frozen non-ML baselines over D1/D2/D3, derives the deterministic
suite summary from the stored experiment results, and optionally renders
the human-readable baseline report from the summary file.
"""

from __future__ import annotations

import json

from v2.model_lab import experiment as EX
from v2.model_lab import results as RES
from v2.model_lab import suite as SUITE


def main(argv: list | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m v2.model_lab.run_baselines",
        description="Run the M2 non-ML development baseline suite")
    parser.add_argument("--task", default="winner")
    parser.add_argument("--folds", default="D1,D2,D3",
                        help="comma-separated development folds "
                             "(D1/D2/D3 only)")
    parser.add_argument("--baselines", default=None,
                        help="comma-separated baseline names; default: all "
                             "valid for the task")
    parser.add_argument("--feature-set", default="ALL_84")
    parser.add_argument("--seed", type=int, default=EX.PROJECT_SEED)
    parser.add_argument("--root", default=None,
                        help="alternate experiment tree root (debugging)")
    parser.add_argument("--out", default=None,
                        help="suite summary path; default: "
                             "data/v2/model_lab/reports/baseline_suite_v1.json")
    parser.add_argument("--render-report", default=None,
                        help="write human-readable markdown rendered from "
                             "the stored suite summary")
    parser.add_argument("--secondary-smoke", action="store_true",
                        help="one GRID_POLE/final_position/D1 smoke run")
    parser.add_argument("--dry-run", action="store_true",
                        help="validate suite configuration only")
    args = parser.parse_args(argv)

    folds = SUITE.parse_folds(args.folds)
    baselines = SUITE.parse_baselines(args.baselines, args.task)

    if args.dry_run:
        for fold in folds:
            for name in baselines:
                config = EX.build_config(
                    args.task, args.feature_set, fold,
                    model_family=f"baseline:{name}", seed=args.seed)
                print(f"{name}/{fold}: {config.experiment_id}")
        print("dry-run: configurations valid; nothing executed")
        return 0

    summary = SUITE.run_suite(
        task=args.task, folds=folds, baselines=baselines,
        feature_set=args.feature_set, seed=args.seed, root=args.root,
        out=args.out, secondary_smoke=args.secondary_smoke)
    print(f"suite summary: {summary['_summary_path']}")
    print(f"experiments: {len(summary['experiments'])}")
    print(f"total_seconds: {summary['runtime']['total_seconds']:.1f}")

    if args.render_report:
        with open(summary["_summary_path"], encoding="utf-8") as fh:
            stored = json.load(fh)
        stored["_summary_path"] = summary["_summary_path"]
        RES.atomic_write_text(args.render_report,
                              SUITE.render_report(stored))
        print(f"report: {args.render_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
