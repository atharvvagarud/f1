"""M3 model-suite CLI (LOGREG reference only; development folds only).

Runs LOGREG x winner x D1/D2/D3 through the canonical model runner,
derives the deterministic suite summary from the stored experiment
results, and optionally renders the human-readable report from the
stored summary. The protected 2025 holdout has no CLI path here.
"""

from __future__ import annotations

import json

from v2.model_lab import experiment as EX
from v2.model_lab import model_suite as MSUITE
from v2.model_lab import results as RES


def main_single(*, task: str, model: str, fold: str, feature_set: str,
                seed: int, root, dry_run: bool = False) -> int:
    """Run (or validate) one M3 model experiment; shared with run.py."""
    from v2.model_lab import model_runner as MR
    from v2.model_lab import runner as RUN

    if dry_run:
        RUN.resolve_development_fold(fold)
        MR.resolve_model(model)
        if task != MR.M3_TASK:
            from v2.model_lab.errors import ExperimentConfigError
            raise ExperimentConfigError(
                f"M3 evaluates task {MR.M3_TASK!r} only; got {task!r}")
        config = EX.build_config(
            task, feature_set, fold,
            model_family="logistic_regression", seed=seed,
            model_parameters=__import__(
                "v2.model_lab.logreg", fromlist=["x"]).logreg_model_parameters())
        print(f"experiment_id: {config.experiment_id}")
        print("dry-run: configuration valid; nothing executed")
        return 0
    out = MR.run_model_experiment(
        task=task, model=model, fold=fold,
        feature_set=feature_set, seed=seed, root=root)
    config, result = out["config"], out["result"]
    print(f"experiment_id: {config.experiment_id}")
    print(f"dest: {out['dest']}")
    print(f"status: {result.status.value}")
    for name, payload in result.metrics.items():
        if isinstance(payload, dict) and payload.get("status") == "OK" \
                and "race_macro" in payload:
            print(f"{name}: race_macro={payload['race_macro']['value']!r} "
                  f"state_pooled={payload['state_pooled']['value']!r}")
        elif isinstance(payload, dict):
            print(f"{name}: {payload.get('status')}")
    print(f"total_seconds: {out['timings']['total_seconds']:.2f}")
    return 0


def main(argv: list | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m v2.model_lab.run_models",
        description="Run the M3 LOGREG reference suite (D1/D2/D3 only)")
    parser.add_argument("--model", default="LOGREG",
                        help="M3 candidate model alias (LOGREG only)")
    parser.add_argument("--task", default="winner")
    parser.add_argument("--folds", default="D1,D2,D3",
                        help="comma-separated development folds "
                             "(D1/D2/D3 only)")
    parser.add_argument("--fold", default=None,
                        help="single development fold (alternative to --folds)")
    parser.add_argument("--feature-set", default="ALL_84")
    parser.add_argument("--seed", type=int, default=EX.PROJECT_SEED)
    parser.add_argument("--root", default=None,
                        help="alternate experiment tree root (debugging)")
    parser.add_argument("--out", default=None,
                        help="suite summary path; default: "
                             "data/v2/model_lab/reports/logreg_reference_v1.json")
    parser.add_argument("--render-report", default=None,
                        help="write human-readable markdown rendered from "
                             "the stored suite summary")
    parser.add_argument("--dry-run", action="store_true",
                        help="validate suite configuration only")
    args = parser.parse_args(argv)

    folds = (args.fold,) if args.fold else tuple(
        s.strip() for s in str(args.folds).split(",") if s.strip())

    if args.dry_run and args.fold:
        return main_single(task=args.task, model=args.model, fold=args.fold,
                           feature_set=args.feature_set, seed=args.seed,
                           root=args.root, dry_run=True)
    if args.dry_run:
        from v2.model_lab import model_runner as MR
        from v2.model_lab import runner as RUN
        from v2.model_lab.errors import ExperimentConfigError
        if args.task != MR.M3_TASK:
            raise ExperimentConfigError(
                f"M3 evaluates task {MR.M3_TASK!r} only; got {args.task!r}")
        for fold in folds:
            RUN.resolve_development_fold(fold)
            MR.resolve_model(args.model)
        print(f"folds: {list(folds)}; model: {args.model}")
        print("dry-run: configurations valid; nothing executed")
        return 0

    if args.fold and not args.render_report and args.out is None:
        return main_single(task=args.task, model=args.model, fold=args.fold,
                           feature_set=args.feature_set, seed=args.seed,
                           root=args.root)

    summary = MSUITE.run_model_suite(
        task=args.task, model=args.model, folds=folds,
        feature_set=args.feature_set, seed=args.seed, root=args.root,
        out=args.out)
    print(f"suite summary: {summary['_summary_path']}")
    print(f"experiments: {len(summary['experiments'])}")
    print(f"total_seconds: {summary['runtime']['total_seconds']:.1f}")

    if args.render_report:
        with open(summary["_summary_path"], encoding="utf-8") as fh:
            stored = json.load(fh)
        stored["_summary_path"] = summary["_summary_path"]
        RES.atomic_write_text(args.render_report,
                              MSUITE.render_logreg_report(stored))
        print(f"report: {args.render_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
