"""Deterministic state-level MC2 batch executor (performance P1).

Wraps the frozen MC2 scientific path without changing it: each worker
executes the existing per-exact-state computation (prepare + run_mc2) for
one exact field state. Parallelism is across INDEPENDENT exact states only;
no within-run future chunking, no kernel changes, no threads, no nested
pools, no worker-specific RNG.

Determinism: task identity is scientific (race_id, frame_index, config);
per-simulation RNG streams are keyed by (master_seed, sim_id) inside the
frozen kernel, so worker count, PIDs, scheduling, and completion order
cannot affect results. The parent aggregates in canonical scientific order
and is the SOLE checkpoint writer (atomic tmp+replace, version-stamped
entries). Workers never open the shared checkpoint.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import multiprocessing as mp
import os
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass

#: Executor version stamped into every checkpoint entry and result.
EXECUTOR_VERSION = "mc2-batch-v1"

#: Portable worker bound (see default_workers): never an autotuner.
MAX_WORKERS = 8


class Mc2BatchError(Exception):
    """Typed parent-side failure naming the exact failed task."""


@dataclass(frozen=True)
class Mc2StateTask:
    """Exact scientific task identity for one MC2 field-state evaluation.

    Identity is the exact factual boundary (race_id + frame_index), never
    race+lap alone: driver rows on one lap map to distinct frames. Config
    (arm/seed/count/rho) is part of the identity so a checkpoint entry can
    never be reused across incompatible science.
    """

    race_id: str
    frame_index: int
    fold_through: int
    arm: str = "E_AR1_RESIDUAL"
    master_seed: int = 20240101
    simulation_count: int = 5000
    rho: float = 0.264

    def key(self) -> tuple:
        return (self.race_id, int(self.frame_index))

    def config_key(self) -> tuple:
        return (self.arm, int(self.master_seed),
                int(self.simulation_count), float(self.rho))

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "frame_index": int(self.frame_index),
            "fold_through": int(self.fold_through),
            "arm": self.arm,
            "master_seed": int(self.master_seed),
            "simulation_count": int(self.simulation_count),
            "rho": float(self.rho),
        }

    @classmethod
    def from_dict(cls, blob: dict) -> "Mc2StateTask":
        return cls(
            race_id=str(blob["race_id"]),
            frame_index=int(blob["frame_index"]),
            fold_through=int(blob["fold_through"]),
            arm=str(blob.get("arm", "E_AR1_RESIDUAL")),
            master_seed=int(blob.get("master_seed", 20240101)),
            simulation_count=int(blob.get("simulation_count", 5000)),
            rho=float(blob.get("rho", 0.264)),
        )


def default_workers(n_tasks: int) -> int:
    """Portable default: bounded, task-aware, explainable.

    min(8, cpu_count, n_tasks); always >= 1. Execution-only: worker count
    never enters scientific identity, RNG, or outputs.
    """
    import os as _os

    cpu = _os.cpu_count() or 2
    return max(1, min(MAX_WORKERS, int(cpu), max(1, int(n_tasks))))


# --- worker side (module-level: pickleable under spawn) ---

_WORKER_PARAMS: dict = {}
_WORKER_GRIDS: dict = {}
_WORKER_PATHS_READY = False


def _worker_init(pkg_dir: str, scripts_dir: str) -> None:
    """Spawn-safe path setup: repo locations explicit, no fork inheritance."""
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)


def _ensure_worker_paths() -> None:
    global _WORKER_PATHS_READY
    if _WORKER_PATHS_READY:
        return
    here = os.path.dirname(os.path.abspath(__file__))
    pkg_dir = os.path.dirname(os.path.dirname(here))
    scripts_dir = os.path.join(pkg_dir, "scripts")
    _worker_init(pkg_dir, scripts_dir)
    _WORKER_PATHS_READY = True


def _repo_root() -> str:
    here = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


def _worker_params(through: int):
    if through not in _WORKER_PARAMS:
        from raceintel.simulation.params import (
            load_simulation_parameters,
            parameter_storage_dir,
        )
        _WORKER_PARAMS[through] = load_simulation_parameters(
            parameter_storage_dir(_repo_root(), through))
    return _WORKER_PARAMS[through]


def _worker_grid(race_id: str):
    if race_id not in _WORKER_GRIDS:
        import pandas as pd

        import run_v3_2e_backtest as B2E

        season = int(str(race_id)[:4])
        res = pd.read_parquet(
            os.path.join(_repo_root(), "data", "v2", "processed",
                         "results", f"season={season}",
                         f"results__{race_id}.parquet"))
        _WORKER_GRIDS[race_id] = B2E._grid_map(res)
    return _WORKER_GRIDS[race_id]


def execute_state_task(task_blob: dict) -> dict:
    """Execute one exact state through the frozen scientific path.

    Module-level and pickleable. Replicates the frozen D orchestration
    statements exactly (prepare -> variance/mechanism replacement ->
    run_mc2). Refusals (expected scientific outcomes) return typed refusal
    envelopes; unexpected failures raise (never fabricated).
    """
    from dataclasses import replace

    _ensure_worker_paths()
    task = (task_blob if isinstance(task_blob, Mc2StateTask)
            else Mc2StateTask.from_dict(task_blob))
    from raceintel.simulation.mc2.kernel import kernel_identity, run_mc2
    from raceintel.simulation.mc2.variance import (
        RegimeStat,
        select_variance,
    )

    import run_v3_2e_backtest as B2E

    t_prep0 = time.perf_counter()
    params = _worker_params(task.fold_through)
    grid = _worker_grid(task.race_id)
    try:
        prep = B2E._prepare_state_and_mechanisms(
            task.race_id, task.frame_index, params, grid)
    except Exception as exc:  # noqa: BLE001 - typed refusal, not a result
        return {
            "status": "refused",
            "task": task.to_dict(),
            "reason": "PREP_REFUSAL",
            "detail": f"{type(exc).__name__}: {exc}",
            "kernel_identity": kernel_identity(),
            "executor_version": EXECUTOR_VERSION,
        }
    sim_state, selection, sampler, mechanisms, _ = prep
    resid = params.family("lap_residual_distribution_s")
    era = selection.era
    era_e = resid.entries.get(era)
    g_e = resid.entries.get("global")
    sel = select_variance({
        "era": RegimeStat(float(era_e.std or 1.5), era_e.sample_count)
        if era_e and era_e.std else None,
        "global": RegimeStat(float(g_e.std or 1.5), g_e.sample_count)
        if g_e and g_e.std else None})
    mechs = {did: replace(m, regime_std_s=sel.std_s, rho=task.rho,
                          ar1_enabled=True)
             for did, m in mechanisms.items()}
    prep_s = time.perf_counter() - t_prep0
    t_run0 = time.perf_counter()
    res = run_mc2(sim_state, selection, sampler, mechs,
                  arm=task.arm, master_seed=task.master_seed,
                  simulation_count=task.simulation_count)
    run_s = time.perf_counter() - t_run0
    drivers = sorted(d.driver_id for d in sim_state.drivers)
    n_valid = int(res.get("valid", 0))
    if n_valid <= 0:
        return {
            "status": "refused",
            "task": task.to_dict(),
            "reason": "ZERO_VALID_TRIALS",
            "detail": "run produced no valid trials",
            "kernel_identity": kernel_identity(),
            "executor_version": EXECUTOR_VERSION,
            "prep_s": prep_s,
            "run_s": run_s,
        }
    return {
        "status": "complete",
        "task": task.to_dict(),
        "reason": None,
        "detail": None,
        "kernel_identity": kernel_identity(),
        "executor_version": EXECUTOR_VERSION,
        "prep_s": prep_s,
        "run_s": run_s,
        "valid": n_valid,
        "invalid": int(res.get("invalid", 0)),
        "drivers": drivers,
        "winner_counts": dict(res["winner_counts"]),
        "winner_frequency": dict(res["winner_frequency"]),
        "expected_finish": dict(res["expected_finish"]),
        "position_counts": {d: dict(v) for d, v in
                            res["position_counts"].items()},
        "position_distribution": {d: dict(v) for d, v in
                                  res["position_distribution"].items()},
        "podium_frequency": dict(res["podium_frequency"]),
        "sample_order": list(res["sample_order"]),
    }


# --- parent side ---


def _checkpoint_entry(result: dict) -> dict:
    task = result["task"]
    entry = {
        "state_id": f"{task['race_id']}|{task['frame_index']}",
        "task": task,
        "status": result["status"],
        "executor_version": EXECUTOR_VERSION,
        "kernel_identity": result["kernel_identity"],
        "config_stamp": {
            "arm": task["arm"],
            "master_seed": task["master_seed"],
            "simulation_count": task["simulation_count"],
            "rho": task["rho"],
        },
    }
    if result["status"] == "complete":
        entry.update({
            "prep_s": result.get("prep_s"),
            "run_s": result.get("run_s"),
            "valid": result["valid"],
            "invalid": result["invalid"],
            "drivers": result["drivers"],
            "winner_counts": result["winner_counts"],
            "winner_frequency": result["winner_frequency"],
            "expected_finish": result["expected_finish"],
            "position_counts": {d: {str(k): v for k, v in v.items()}
                                for d, v in
                                result["position_counts"].items()},
            "position_distribution": {d: {str(k): v for k, v in v.items()}
                                      for d, v in result[
                                          "position_distribution"].items()},
            "podium_frequency": result["podium_frequency"],
            "sample_order": result["sample_order"],
        })
    else:
        entry.update({"reason": result["reason"],
                      "detail": result["detail"]})
    return entry


def _stamp_matches(entry: dict, task: Mc2StateTask) -> bool:
    stamp = entry.get("config_stamp", {})
    return (entry.get("executor_version") == EXECUTOR_VERSION
            and stamp.get("arm") == task.arm
            and stamp.get("master_seed") == task.master_seed
            and stamp.get("simulation_count") == task.simulation_count
            and stamp.get("rho") == task.rho)


def _atomic_write_json(path: str, blob: dict) -> None:
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(blob, fh, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def run_batch(tasks: list, *, workers: int | None = None,
              checkpoint_path: str | None = None,
              resume: bool = False) -> dict:
    """Run exact-state tasks across processes with deterministic assembly.

    Single writer: only the parent touches checkpoint_path (atomic
    tmp+replace). Results are ordered canonically by (race_id,
    frame_index), never by completion order. Unexpected worker failures
    raise Mc2BatchError after checkpointing completed states; refusals are
    typed envelopes, never fabricated results.
    """
    task_objs = [t if isinstance(t, Mc2StateTask)
                 else Mc2StateTask.from_dict(t) for t in tasks]
    if not task_objs:
        raise ValueError("run_batch requires at least one task")
    for t in task_objs:
        if not t.race_id or int(t.frame_index) < 0:
            raise ValueError(f"invalid task identity: {t!r}")
        if int(t.simulation_count) < 1 or type(t.master_seed) is not int:
            raise ValueError(f"invalid task config: {t!r}")
    n_workers = int(workers) if workers is not None else default_workers(
        len(task_objs))
    if n_workers < 1:
        raise ValueError("workers must be >= 1")

    store: dict = {}
    if checkpoint_path and resume:
        try:
            with open(checkpoint_path, encoding="utf-8") as fh:
                previous = json.load(fh)
            for entry in previous.get("entries", {}).values():
                task = Mc2StateTask.from_dict(entry["task"])
                if (task.key(), task.config_key()) in {
                        (t.key(), t.config_key()) for t in task_objs} \
                        and _stamp_matches(entry, task):
                    store[task.key()] = entry
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            pass  # corrupt checkpoint never blocks; recompute instead

    pending = [t for t in task_objs if t.key() not in store]
    failed: dict = {}
    ctx = mp.get_context("spawn")
    here = os.path.dirname(os.path.abspath(__file__))
    pkg_dir = os.path.dirname(os.path.dirname(here))
    t_wall0 = time.perf_counter()
    try:
        with concurrent.futures.ProcessPoolExecutor(
                max_workers=n_workers, mp_context=ctx,
                initializer=_worker_init,
                initargs=(pkg_dir,
                          os.path.join(pkg_dir, "scripts"))) as pool:
            future_to_key = {
                pool.submit(execute_state_task, t.to_dict()): t.key()
                for t in pending}
            for future in concurrent.futures.as_completed(future_to_key):
                key = future_to_key[future]
                task = next(t for t in pending if t.key() == key)
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001 - typed below
                    failed[key] = {
                        "task": task.to_dict(),
                        "error": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(),
                    }
                    continue
                store[key] = _checkpoint_entry(result)
                if checkpoint_path:
                    _atomic_write_json(checkpoint_path, {
                        "executor_version": EXECUTOR_VERSION,
                        "entries": {k[0] + "|" + str(k[1]): v
                                    for k, v in store.items()},
                    })
    except KeyboardInterrupt:
        raise Mc2BatchError("interrupted; completed states checkpointed; "
                            "no partial state recorded")
    wall_s = time.perf_counter() - t_wall0

    ordered_keys = sorted(store, key=lambda k: (k[0], k[1]))
    ordered = [store[k] for k in ordered_keys]
    payload_bytes = len(json.dumps(ordered, sort_keys=True).encode())
    summary = {
        "executor_version": EXECUTOR_VERSION,
        "workers_requested": n_workers,
        "n_tasks": len(task_objs),
        "n_complete": sum(1 for e in ordered
                          if e["status"] == "complete"),
        "n_refused": sum(1 for e in ordered
                         if e["status"] == "refused"),
        "n_failed": len(failed),
        "wall_s": wall_s,
        "payload_bytes": payload_bytes,
        "ordered_keys": [k[0] + "|" + str(k[1]) for k in ordered_keys],
        "results": ordered,
    }
    if failed:
        raise Mc2BatchError(
            "worker failures: " + "; ".join(
                f"{k[0]}|{k[1]}: {v['error']}"
                for k, v in sorted(failed.items())))
    if len(ordered) != len(task_objs):
        raise Mc2BatchError(
            f"incomplete batch: {len(ordered)}/{len(task_objs)} "
            "states recorded; nothing fabricated")
    return summary
