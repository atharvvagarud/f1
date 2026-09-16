"""M9 final-fit + protected 2025 holdout CLI.

Explicit, auditable entry points for the Model Lab freeze stage:

- ``--gate``                 run the pre-unlock gate only (never touches 2025);
- ``--write-declaration``    write the immutable PRE-UNLOCK declaration;
- ``--allow-holdout``        run the one-shot M9 final fit + 2025 evaluation;
- ``--write-docs``           render the model card / final report / freeze
                             manifest from the stored protected artifact.

The holdout is only unlocked when ``--allow-holdout`` is passed; it always
evaluates exactly once.
"""

from __future__ import annotations

import json
from pathlib import Path

from v2.model_lab import data as DATA
from v2.model_lab import final_fit as FF


def main(argv: list | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m v2.model_lab.run_final",
        description="M9 final fit + one-shot protected 2025 holdout")
    parser.add_argument("--allow-holdout", action="store_true",
                        help="explicitly unlock the protected 2025 holdout "
                             "exactly once")
    parser.add_argument("--gate", action="store_true",
                        help="run the pre-unlock gate only")
    parser.add_argument("--write-declaration", action="store_true",
                        help="write the immutable pre-unlock declaration")
    parser.add_argument("--write-docs", action="store_true",
                        help="render model card / final report / freeze "
                             "manifest from the stored artifact")
    parser.add_argument("--no-bootstrap", action="store_true",
                        help="skip the optional whole-race bootstrap")
    parser.add_argument("--test-evidence", default=None,
                        help="JSON file with recorded FULL-gate test results "
                             "embedded in the freeze manifest")
    parser.add_argument("--root", default=None,
                        help="alternate repository root (debugging)")
    parser.add_argument("--out", default=None,
                        help="holdout artifact path override")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the frozen specification; execute nothing")
    args = parser.parse_args(argv)

    if args.dry_run:
        print(json.dumps(FF.frozen_specification(), indent=2, sort_keys=True))
        print(f"specification_fingerprint: "
              f"{FF.specification_fingerprint()}")
        print(f"FINAL_FIT seasons: {list(FF.FINAL_FIT_SEASONS)}")
        print(f"HOLDOUT season: {FF.HOLDOUT_SEASON}")
        print("dry-run: nothing executed")
        return 0

    if args.gate:
        canonical = DATA.load_canonical()
        checks = FF.run_preunlock_gate(canonical, root=args.root)
        print(json.dumps(checks, indent=2, sort_keys=True, default=str))
        print("pre-unlock gate: PASS")
        return 0

    if args.write_declaration:
        canonical = DATA.load_canonical()
        FF.run_preunlock_gate(canonical, root=args.root)
        path = FF.write_preunlock_declaration(canonical, root=args.root)
        print(f"pre-unlock declaration: {path}")
        return 0

    if args.allow_holdout:
        summary = FF.run_m9(
            root=args.root, allow_protected_holdout=True, out=args.out,
            bootstrap=not args.no_bootstrap)
        print(f"pre-unlock: {summary['preunlock']['path']}")
        print(f"holdout artifact: {summary['_summary_path']}")
        print(f"final model metadata: {summary['_metadata_path']}")
        print(f"protected experiment: {summary['_dest']}")
        print(f"race-macro log loss: "
              f"{summary['metrics']['race_macro']['log_loss']}")
        print(f"race-macro Brier: "
              f"{summary['metrics']['race_macro']['brier']}")

    if args.write_docs:
        artifact_path = (Path(args.out) if args.out is not None
                         else FF.default_out(root=args.root))
        if not artifact_path.exists():
            raise SystemExit(
                f"holdout artifact missing at {artifact_path}; run with "
                "--allow-holdout first")
        artifact = json.loads(artifact_path.read_text())
        test_results = None
        if args.test_evidence:
            test_results = json.loads(
                Path(args.test_evidence).read_text())
        written = FF.write_documents(
            artifact, root=args.root, test_results=test_results)
        print(f"model card: {written['model_card']}")
        print(f"final report: {written['final_report']}")
        print(f"freeze manifest: {written['freeze_manifest']}")

    if not (args.gate or args.write_declaration or args.allow_holdout
            or args.write_docs):
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
