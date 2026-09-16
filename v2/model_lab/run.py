"""M2/M3 single-experiment CLI (development folds only, no holdout option).

Executes one baseline experiment through the canonical runner path and
persists config.json + result.json via the M1 result infrastructure.
With ``--model`` (M3, LOGREG only) the call is delegated to the model
runner, which evaluates through the same canonical path.
"""

from __future__ import annotations

from v2.model_lab import experiment as EX
from v2.model_lab import runner as RUN


def main(argv: list | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m v2.model_lab.run",
        description="Run one M2 baseline experiment (D1/D2/D3 only)")
    parser.add_argument("--baseline", required=False, default=None,
                        help="frozen baseline name, e.g. CURRENT_LEADER")
    parser.add_argument("--model", required=False, default=None,
                        help="M3 reference model alias, e.g. LOGREG; "
                             "when given, --baseline must be omitted and the "
                             "model runner handles the experiment")
    parser.add_argument("--task", default="winner")
    parser.add_argument("--fold", required=True,
                        help="development fold: D1, D2 or D3")
    parser.add_argument("--feature-set", default="ALL_84")
    parser.add_argument("--seed", type=int, default=EX.PROJECT_SEED)
    parser.add_argument("--root", default=None,
                        help="alternate experiment tree root (debugging)")
    parser.add_argument("--dry-run", action="store_true",
                        help="validate configuration only; run nothing")
    args = parser.parse_args(argv)

    if args.model is not None:
        if args.baseline is not None:
            raise SystemExit("pass exactly one of --baseline or --model")
        import importlib
        module = importlib.import_module("v2.model_lab.run_models")
        return module.main_single(
            task=args.task, model=args.model, fold=args.fold,
            feature_set=args.feature_set, seed=args.seed, root=args.root,
            dry_run=args.dry_run)

    if args.baseline is None:
        raise SystemExit("pass exactly one of --baseline or --model")

    if args.dry_run:
        RUN.resolve_development_fold(args.fold)
        config = EX.build_config(
            args.task, args.feature_set, args.fold,
            model_family=f"baseline:{args.baseline}", seed=args.seed)
        print(f"experiment_id: {config.experiment_id}")
        print("dry-run: configuration valid; nothing executed")
        return 0

    out = RUN.run_experiment(
        task=args.task, baseline=args.baseline, fold=args.fold,
        feature_set=args.feature_set, seed=args.seed, root=args.root)
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


if __name__ == "__main__":
    raise SystemExit(main())
