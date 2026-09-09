"""V2 ingestion CLI — framework + Tier-B commands (D3/D4).

Run: ``python -m v2.cli <command> [options]``.

There is deliberately NO broad-ingestion default: ``plan`` requires an
explicit ``--season`` plus explicit ``--rounds``; ``plan-tierb`` requires
an explicit ``--seasons`` list; ``run`` executes only units present in an
explicitly planned manifest. Live Jolpica ingestion additionally requires
``V2_ALLOW_NETWORK=1``. Commands needing a source adapter fail clearly
when the adapter is unknown (``synthetic`` for the framework, ``jolpica``
for Tier-B; D5 rich adapters do not exist yet).
"""

from __future__ import annotations

import argparse
import os
import sys

from v2 import contracts as C
from v2.config import V2Paths, V2_ROOT_REL
from v2.errors import IngestionError
from v2.ingestion import AdapterFn, run_unit
from v2.jolpica import CLIENT_VERSION as JOLPICA_CLIENT_VERSION
from v2.jolpica import NETWORK_ENV_VAR
from v2.manifests import Manifest, UnitStatus
from v2.retry import RetryPolicy
from v2.runs import RunRecord, start_run
from v2.synthetic import synthetic_adapter
from v2.tiera import tiera_race_adapter
from v2.tierb import tierb_season_adapter


def _adapters() -> dict[str, AdapterFn]:
    return {"synthetic": synthetic_adapter, "jolpica": tierb_season_adapter,
            "fastf1": tiera_race_adapter}


def _load_manifest(paths: V2Paths, name: str) -> Manifest:
    path = paths.manifest_path(name)
    if not path.exists():
        raise IngestionError.config(
            f"no manifest at {paths.relative(path)}; run 'plan' first")
    return Manifest.load(path)


def cmd_status(args, paths: V2Paths) -> int:
    manifest = _load_manifest(paths, args.manifest)
    counts = manifest.status_counts()
    total = sum(counts.values())
    print(f"manifest: {paths.relative(paths.manifest_path(args.manifest))}")
    print(f"units: {total}")
    for status in UnitStatus:
        print(f"  {status.value}: {counts[status.value]}")
    return 0


def cmd_plan(args, paths: V2Paths) -> int:
    if args.season is None or not args.rounds:
        raise IngestionError.config(
            "plan requires explicit scope: --season YYYY --rounds N [N ...]")
    manifest = Manifest()
    unit_ids = manifest.plan_race_scope(
        args.season, [int(r) for r in args.rounds],
        schema_version=C.SCHEMA_VERSION)
    path = manifest.save(paths.manifest_path(args.manifest))
    print(f"planned {len(unit_ids)} units -> {paths.relative(path)}")
    return 0


def cmd_recover_stale(args, paths: V2Paths) -> int:
    """Return crashed DOWNLOADING units to PENDING (explicit only).

    This is the sole path back from a dead process's claim: normal `run`
    never touches a claimed unit (stale claims raise instead of running).
    """
    manifest = _load_manifest(paths, args.manifest)
    try:
        max_age_s = float(args.max_age_s)
    except (TypeError, ValueError):
        raise IngestionError.config(
            f"recover-stale needs a numeric --max-age-s, got "
            f"{args.max_age_s!r}") from None
    if max_age_s < 0:
        raise IngestionError.config("recover-stale --max-age-s must be >= 0")
    recovered = manifest.recover_stale(max_age_s)
    manifest.save(paths.manifest_path(args.manifest))
    print(f"recovered {len(recovered)} stale units to PENDING"
          + (f": {sorted(recovered)}" if recovered else ""))
    return 0


def cmd_retry(args, paths: V2Paths) -> int:
    manifest = _load_manifest(paths, args.manifest)
    wanted = {s.strip().lower() for s in args.status.split(",")}
    mapping = {"failed": UnitStatus.FAILED, "partial": UnitStatus.PARTIAL}
    unknown = wanted - set(mapping)
    if unknown:
        raise IngestionError.config(
            f"retry supports only failed/partial, got: {sorted(unknown)}")
    requeued = 0
    for status in wanted:
        for entry in manifest.by_status(mapping[status]):
            manifest.transition(entry.unit_id, UnitStatus.PENDING)
            requeued += 1
    manifest.save(paths.manifest_path(args.manifest))
    print(f"requeued {requeued} units to PENDING")
    return 0


def cmd_plan_tierb(args, paths: V2Paths) -> int:
    if not args.seasons:
        raise IngestionError.config(
            "plan-tierb requires explicit scope: "
            "--seasons YYYY [YYYY ...] (no all-history default)")
    seasons = []
    for raw in args.seasons:
        try:
            season = int(raw)
        except (TypeError, ValueError):
            raise IngestionError.config(
                f"plan-tierb: season must be an integer, got {raw!r}") from None
        if season < 1950:
            raise IngestionError.config(
                f"plan-tierb: season {season} predates championship F1 "
                f"(Tier-B starts 1950)")
        seasons.append(season)
    manifest = Manifest()
    unit_ids = manifest.plan_tierb_scope(
        seasons, schema_version=C.SCHEMA_VERSION)
    path = manifest.save(paths.manifest_path(args.manifest))
    print(f"planned {len(unit_ids)} Tier-B units -> {paths.relative(path)}")
    return 0


def _source_version(adapter_name: str) -> str:
    if adapter_name == "synthetic":
        return "synthetic-0"
    if adapter_name == "jolpica":
        return f"jolpica-client-{JOLPICA_CLIENT_VERSION}"
    try:
        import fastf1

        return f"fastf1-{fastf1.__version__}"
    except ImportError:
        return "unknown"


def cmd_run(args, paths: V2Paths) -> int:
    adapters = _adapters()
    if args.adapter not in adapters:
        raise IngestionError.config(
            f"unknown adapter '{args.adapter}' "
            f"(available: {sorted(adapters)})")
    if args.adapter in ("jolpica", "fastf1") and os.environ.get(
            NETWORK_ENV_VAR) != "1":
        # Fail fast before touching any unit: live ingestion is an
        # explicit act (planned manifest + this opt-in), never an accident.
        raise IngestionError.config(
            f"{args.adapter} adapter needs {NETWORK_ENV_VAR}=1 for live "
            f"network ingestion; refusing to run")
    manifest = _load_manifest(paths, args.manifest)
    if args.unit:
        unit_ids = [args.unit]
        for unit_id in unit_ids:
            entry = manifest.get(unit_id)
            if args.adapter == "jolpica" and not unit_id.startswith("tierb-"):
                raise IngestionError.config(
                    f"jolpica adapter needs Tier-B units (tierb-<YYYY>), got "
                    f"'{unit_id}'; plan them with 'plan-tierb'")
            if args.adapter == "synthetic" and entry.season is None:
                raise IngestionError.config(
                    f"synthetic adapter needs a race unit, got '{unit_id}'")
            if args.adapter == "fastf1" and entry.race_id is None:
                raise IngestionError.config(
                    f"fastf1 adapter needs Tier-A race units "
                    f"(e.g. 2023-r01-R), got '{unit_id}'; plan them with "
                    f"'plan --season YYYY --rounds ...'")
    elif args.all_pending:
        unit_ids = [e.unit_id for e in manifest.by_status(UnitStatus.PENDING)]
        if not unit_ids:
            print("nothing pending")
            return 0
        if args.adapter == "jolpica":
            non_tierb = [u for u in unit_ids if not u.startswith("tierb-")]
            if non_tierb:
                raise IngestionError.config(
                    f"jolpica adapter needs Tier-B units; manifest holds "
                    f"non-Tier-B pending units (e.g. {non_tierb[0]}); plan "
                    f"Tier-B scope with 'plan-tierb'")
        if args.adapter == "fastf1":
            non_race = [e.unit_id for e in manifest.by_status(
                UnitStatus.PENDING) if e.race_id is None]
            if non_race:
                raise IngestionError.config(
                    f"fastf1 adapter needs Tier-A race units; manifest holds "
                    f"non-race pending units (e.g. {non_race[0]}); plan "
                    f"race scope with 'plan --season YYYY --rounds ...'")
    else:
        raise IngestionError.config(
            "run requires --unit UNIT_ID or --all-pending")
    run = start_run(
        source=args.adapter, source_lib_version=_source_version(args.adapter),
        schema_version=C.SCHEMA_VERSION,
        scope={"units": unit_ids},
        config_snapshot={"v2_root": V2_ROOT_REL.as_posix()})
    policy = RetryPolicy()
    failed = 0
    manifest_path = paths.manifest_path(args.manifest)

    def _persist_claim(_claimed: Manifest) -> None:
        # Persist the DOWNLOADING claim BEFORE the adapter's blocking
        # network work: live `status` observes it and a crash mid-unit is
        # recoverable via recover_stale instead of silently restarting.
        manifest.save(manifest_path)

    for unit_id in unit_ids:
        outcome = run_unit(manifest, unit_id, adapters[args.adapter],
                           paths, run, policy, force=args.force,
                           on_claim=_persist_claim)
        # Persist after EVERY unit (not just at the end of the loop): a
        # crash/kill mid-run must not lose completed work, and `status`
        # must show progress during long multi-unit runs instead of
        # reporting pending=N until the final save.
        manifest.save(manifest_path)
        print(f"{unit_id}: {outcome.status.value} "
              f"(attempts={outcome.attempts})"
              f"{f' — {outcome.message}' if outcome.message else ''}",
              flush=True)
        if outcome.status == UnitStatus.FAILED:
            failed += 1
    manifest.save(manifest_path)
    run_record = run.finished("failed" if failed else "complete")
    print(f"run {run_record.run_id}: {run_record.status}", flush=True)
    return 1 if failed else 0


def cmd_validate_config(args, paths: V2Paths) -> int:
    problems = []
    for label, directory in (("manifests", paths.manifests_dir),
                             ("processed", paths.processed_dir),
                             ("cache", paths.cache_dir)):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            problems.append(f"{label} dir not writable: {exc}")
    try:
        import pyarrow  # noqa: F401

        print(f"pyarrow {pyarrow.__version__} ok")
    except ImportError:
        problems.append("pyarrow is not installed (need "
                        + C.RECOMMENDED_PYARROW_PIN + ")")
    print(f"schema version: {C.SCHEMA_VERSION}")
    print(f"v2 root: {paths.v2_root}")
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 2
    print("config ok")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m v2.cli",
                                     description="V2 ingestion framework CLI")
    parser.add_argument("--root", default=None,
                        help="project root (default: V2_PROJECT_ROOT or cwd)")
    parser.add_argument("--manifest", default="manifest.json",
                        help="manifest file name")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show manifest unit counts")
    plan = sub.add_parser("plan", help="plan an explicit bounded scope")
    plan.add_argument("--season", type=int, default=None)
    plan.add_argument("--rounds", nargs="*", default=[])
    plan_tierb = sub.add_parser(
        "plan-tierb", help="plan explicit Tier-B season units (tierb-<YYYY>)")
    plan_tierb.add_argument("--seasons", nargs="*", default=[])
    retry = sub.add_parser("retry", help="requeue failed/partial units")
    retry.add_argument("--status", default="failed,partial")
    recover = sub.add_parser(
        "recover-stale",
        help="return crashed DOWNLOADING units to PENDING "
             "(only this command may do so)")
    recover.add_argument("--max-age-s", default="3600",
                         help="claims older than this (seconds) count as "
                              "stale (default: 3600)")
    run = sub.add_parser("run", help="execute planned units")
    run.add_argument("--adapter", default="synthetic")
    run.add_argument("--unit", default=None)
    run.add_argument("--all-pending", action="store_true")
    run.add_argument("--force", action="store_true",
                     help="deterministically rebuild COMPLETE units")
    sub.add_parser("validate-config", help="check paths + dependencies")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = V2Paths.resolve(args.root)
        if args.command == "status":
            return cmd_status(args, paths)
        if args.command == "plan":
            return cmd_plan(args, paths)
        if args.command == "plan-tierb":
            return cmd_plan_tierb(args, paths)
        if args.command == "retry":
            return cmd_retry(args, paths)
        if args.command == "recover-stale":
            return cmd_recover_stale(args, paths)
        if args.command == "run":
            return cmd_run(args, paths)
        if args.command == "validate-config":
            return cmd_validate_config(args, paths)
    except IngestionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError("unreachable")  # subparsers(required=True)


if __name__ == "__main__":
    sys.exit(main())
