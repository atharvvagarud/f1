"""M6 tuning-suite CLI (LogReg + ExtraTrees; development folds only).

Runs {Logistic Regression, ExtraTrees} x winner x D1/D2/D3 through the nested
temporal tuning path, writes the machine-readable tuning artifact and
optionally renders the human-readable report from it. The protected 2025
holdout has no CLI path here.
"""

from __future__ import annotations

import json

from v2.model_lab import experiment as EX
from v2.model_lab import results as RES
from v2.model_lab import tuning as TUNE
from v2.model_lab import tuning_candidates as TC
from v2.model_lab import tuning_suite as TSUITE
from v2.model_lab.errors import ExperimentConfigError

FAMILY_ALIASES = {
    "ALL": TSUITE.SUITE_FAMILIES,
    "LOGREG": (TC.LOGREG_FAMILY,),
    "LOGISTIC_REGRESSION": (TC.LOGREG_FAMILY,),
    "EXTRATREES": (TC.EXTRA_TREES_FAMILY,),
    "ET": (TC.EXTRA_TREES_FAMILY,),
    "EXTRA_TREES": (TC.EXTRA_TREES_FAMILY,),
}


def resolve_families(raw: str) -> tuple:
    key = str(raw).strip().upper()
    if key not in FAMILY_ALIASES:
        raise ExperimentConfigError(
            f"unknown M6 family {raw!r}; known: {sorted(FAMILY_ALIASES)}")
    return FAMILY_ALIASES[key]


def main(argv: list | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m v2.model_lab.run_tuning",
        description="Run the M6 nested temporal tuning suite (D1/D2/D3 only)")
    parser.add_argument("--family", default="ALL",
                        help="ALL, LOGREG, or EXTRATREES")
    parser.add_argument("--task", default="winner")
    parser.add_argument("--folds", default="D1,D2,D3")
    parser.add_argument("--feature-set", default=TUNE.M6_FEATURE_SET)
    parser.add_argument("--seed", type=int, default=EX.PROJECT_SEED)
    parser.add_argument("--root", default=None,
                        help="alternate experiment tree root (debugging)")
    parser.add_argument("--out", default=None,
                        help="tuning artifact path; default "
                             "data/v2/model_lab/reports/tuning_selection_v1.json")
    parser.add_argument("--render-report", default=None,
                        help="write human-readable markdown rendered from the "
                             "stored tuning artifact")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the planned fit budget; execute nothing")
    args = parser.parse_args(argv)

    families = resolve_families(args.family)
    folds = tuple(s.strip() for s in str(args.folds).split(",") if s.strip())
    if args.task != TUNE.M6_TASK:
        raise ExperimentConfigError(
            f"M6 tunes task {TUNE.M6_TASK!r} only; got {args.task!r}")
    if args.feature_set != TUNE.M6_FEATURE_SET:
        raise ExperimentConfigError(
            f"M6 tunes feature set {TUNE.M6_FEATURE_SET!r} only; got "
            f"{args.feature_set!r}")
    if args.seed != TUNE.M6_SEED:
        raise ExperimentConfigError(
            f"M6 uses seed {TUNE.M6_SEED!r} only; got {args.seed!r}")

    if args.dry_run:
        planned = TUNE.planned_fit_count(folds)
        for family in families:
            detail = planned["families"][family]
            for fold, node in detail["per_fold"].items():
                print(f"{family}/{fold}: {node['configs']} configs x "
                      f"{node['inner_folds']} inner folds = "
                      f"{node['estimator_fits']} inner estimator fits")
        print(f"inner estimator fits: {planned['inner_estimator_fits']}")
        print(f"outer selected refits: {planned['outer_selected_refits']}")
        print(f"determinism refits: {planned['determinism_refits']}")
        print(f"total planned estimator fits: "
              f"{planned['total_estimator_fits']}")
        print("dry-run: nothing executed")
        return 0

    if len(families) != len(TSUITE.SUITE_FAMILIES):
        raise ExperimentConfigError(
            "the M6 tuning suite tunes LogReg + ExtraTrees together; "
            "single-family runs are not a supported suite contract")

    summary = TSUITE.run_tuning_suite(
        task=args.task, families=families, folds=folds,
        feature_set=args.feature_set, seed=args.seed, root=args.root,
        out=args.out)
    print(f"tuning artifact: {summary['_summary_path']}")
    print(f"supervised experiments: "
          f"{sum(len(summary['per_candidate'][f]['experiments']) for f in families)}")
    print(f"total_seconds: {summary['runtime']['total_seconds']:.1f}")
    print(f"decision: {summary['recommendation']['decision']}")

    if args.render_report:
        with open(summary["_summary_path"], encoding="utf-8") as fh:
            stored = json.load(fh)
        stored["_summary_path"] = summary["_summary_path"]
        RES.atomic_write_text(args.render_report,
                              TSUITE.render_tuning_report(stored))
        print(f"report: {args.render_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
