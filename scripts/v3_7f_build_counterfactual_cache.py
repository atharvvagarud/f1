"""V3.7F deterministic counterfactual cache generator.

Builds cache artifacts with the validated V3.7C engine through the F
runtime service live path (no science is duplicated here). The service
writes validated artifacts itself on every supported live run; this
script drives a small deterministic fixture set and records a manifest.

Usage:
    .venv/bin/python scripts/v3_7f_build_counterfactual_cache.py --fixture
    .venv/bin/python scripts/v3_7f_build_counterfactual_cache.py \\
        --comparisons-json path/to/comparisons.json --cache-dir <dir>

Fixture (V3.6F-validated dry-green anchor 2022-r01-R / perez / lap 30):
reference-vs-N1, reference-vs-N2, reference-vs-N>2, multi-stop,
plan-vs-plan, rival outcome, multi-driver. Comparisons JSON: list of
{race_id, anchor_driver_id, anchor_lap_number, anchor_state_time_s,
comparison_form, base_plan, alternative_plan, rival_driver_id|"nearest"}.

Properties: deterministic ordering, resume-safe (valid existing artifacts
are reused, never recomputed blindly), atomic writes via the service,
provenance validation on every read, explicit unsupported records are
reported but never cached, progress reporting and a failure summary
(nonzero exit on failures; unsupported is not failure).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.v2_counterfactual_service import build_counterfactual_service
from api.v2_service import load_v2_service
from raceintel.counterfactual import runtime as R
from raceintel.simulation.adapter import from_race_state

ROOT = Path(__file__).resolve().parents[1]

FIXTURE_ANCHOR = {
    "race_id": "2022-r01-R", "anchor_driver_id": "perez",
    "anchor_lap_number": 30, "anchor_state_time_s": 6745.686,
    "target_driver_id": "perez",
}


def _nearest_rival(sim_state, target: str) -> str | None:
    tpos = next(e.position for e in sim_state.drivers
                if e.driver_id == target)
    best, best_key = None, None
    for e in sim_state.drivers:
        if e.driver_id == target or e.position is None or tpos is None:
            continue
        key = (abs(e.position - tpos), e.driver_id)
        if best_key is None or key < best_key:
            best_key, best = key, e.driver_id
    return best


def _plan(targets, specs):
    return {
        "target_driver_ids": list(targets),
        "interventions": [
            {"target_driver_id": t, "kind": "PIT_IN_N_LAPS",
             "lap_offset_n": n, "requested_compound": c}
            for (t, n, c) in specs],
    }


def _fixture_comparisons(v2) -> list:
    race_state = v2.get_state(
        race_id=FIXTURE_ANCHOR["race_id"],
        anchor_driver_id=FIXTURE_ANCHOR["anchor_driver_id"],
        anchor_lap_number=FIXTURE_ANCHOR["anchor_lap_number"],
        anchor_state_time_s=FIXTURE_ANCHOR["anchor_state_time_s"])
    sim_state = from_race_state(race_state)
    target = FIXTURE_ANCHOR["target_driver_id"]
    rival = _nearest_rival(sim_state, target)
    lap = next(e.lap_number for e in sim_state.drivers
               if e.driver_id == target)
    remaining = sim_state.scheduled_laps - lap
    n_long = 5 if remaining - 1 >= 5 else remaining - 1
    second = 8 if remaining - 1 >= 8 else remaining - 1
    co = rival if rival is not None else target
    cases = [
        {"name": "reference-vs-N1",
         "form": "REFERENCE_VS_PLAN", "base": None,
         "alt": _plan([target], [(target, 1, "MEDIUM")]),
         "rival": None},
        {"name": "reference-vs-N2",
         "form": "REFERENCE_VS_PLAN", "base": None,
         "alt": _plan([target], [(target, 2, "MEDIUM")]),
         "rival": None},
        {"name": "reference-vs-N-long",
         "form": "REFERENCE_VS_PLAN", "base": None,
         "alt": _plan([target], [(target, n_long, "MEDIUM")]),
         "rival": None},
        {"name": "reference-vs-multi-stop",
         "form": "REFERENCE_VS_PLAN", "base": None,
         "alt": _plan([target], [(target, 2, "MEDIUM"),
                                 (target, second, "HARD")]),
         "rival": None},
        {"name": "plan-vs-plan",
         "form": "PLAN_VS_PLAN",
         "base": _plan([target], [(target, 2, "MEDIUM")]),
         "alt": _plan([target], [(target, n_long, "MEDIUM")]),
         "rival": None},
        {"name": "reference-vs-N2-rival",
         "form": "REFERENCE_VS_PLAN", "base": None,
         "alt": _plan([target], [(target, 2, "MEDIUM")]),
         "rival": rival},
        {"name": "reference-vs-multi-driver",
         "form": "REFERENCE_VS_PLAN", "base": None,
         "alt": _plan([target, co], [(target, 2, "MEDIUM"),
                                     (co, 2, "MEDIUM")]),
         "rival": None},
    ]
    comparisons = []
    for case in cases:
        comparisons.append({
            "name": case["name"],
            **{k: FIXTURE_ANCHOR[k] for k in (
                "race_id", "anchor_driver_id", "anchor_lap_number",
                "anchor_state_time_s")},
            "comparison_form": case["form"],
            "base_plan": case["base"],
            "alternative_plan": case["alt"],
            "rival_driver_id": case["rival"],
        })
    return comparisons


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic counterfactual cache artifacts.")
    parser.add_argument("--fixture", action="store_true",
                        help="use the built-in representative fixture")
    parser.add_argument("--comparisons-json", default=None,
                        help="JSON list of comparison dicts")
    parser.add_argument("--cache-dir", default=None,
                        help="cache directory (default: production path)")
    parser.add_argument("--manifest-out", default=None,
                        help="manifest JSON path (default: "
                             "results/v3/v3_7f/cache_manifest.json)")
    args = parser.parse_args()

    v2 = load_v2_service()
    if args.fixture:
        comparisons = _fixture_comparisons(v2)
    elif args.comparisons_json:
        comparisons = json.loads(Path(args.comparisons_json).read_text())
        if not isinstance(comparisons, list):
            raise ValueError("comparisons JSON must be a list")
    else:
        print("specify --fixture or --comparisons-json", file=sys.stderr)
        return 2
    comparisons = sorted(
        comparisons,
        key=lambda c: (c["race_id"], c["anchor_lap_number"],
                       str(c["anchor_state_time_s"]),
                       c.get("comparison_form", ""),
                       json.dumps(c.get("alternative_plan") or {},
                                  sort_keys=True)))

    kwargs: dict = {"allow_live": True}
    if args.cache_dir:
        kwargs["cache_dir"] = Path(args.cache_dir)
    service = build_counterfactual_service(v2, **kwargs)
    cache_dir = service.cache_dir

    manifest_out = (Path(args.manifest_out) if args.manifest_out
                    else ROOT / "results" / "v3" / "v3_7f"
                    / "cache_manifest.json")

    entries, failures = [], []
    t0 = time.perf_counter()
    for i, comp in enumerate(comparisons, 1):
        label = comp.get("name") or (
            f"{comp['race_id']}/{comp.get('comparison_form')}")
        print(f"[{i}/{len(comparisons)}] {label} ...", flush=True)
        try:
            payload = service.run_comparison(
                race_id=comp["race_id"],
                anchor_driver_id=comp["anchor_driver_id"],
                anchor_lap_number=comp["anchor_lap_number"],
                anchor_state_time_s=comp["anchor_state_time_s"],
                comparison_form=comp.get("comparison_form",
                                         "REFERENCE_VS_PLAN"),
                base_plan=comp.get("base_plan"),
                alternative_plan=comp["alternative_plan"],
                rival_driver_id=comp.get("rival_driver_id"))
        except Exception as exc:  # noqa: BLE001 - record, never guess
            failures.append({"comparison": comp,
                             "error": f"{type(exc).__name__}: {exc}"})
            print(f"  FAILED: {type(exc).__name__}: {exc}", flush=True)
            continue
        print(f"  supported={payload['supported']} "
              f"source={payload['execution_source']} "
              f"key={str(payload['cache_key'])[:12]}...", flush=True)
        entries.append({
            "name": label,
            "race_id": comp["race_id"],
            "anchor_driver_id": comp["anchor_driver_id"],
            "anchor_lap_number": comp["anchor_lap_number"],
            "anchor_state_time_s": comp["anchor_state_time_s"],
            "comparison_form": payload.get("comparison_form"),
            "comparison_identity": payload.get("comparison_identity"),
            "base_identity": payload.get("base_identity"),
            "alternative_identity": payload.get("alternative_identity"),
            "rival_driver_id": payload.get("rival_driver_id"),
            "supported": payload["supported"],
            "reason_code": payload.get("reason_code"),
            "complete_pairs": payload.get("complete_pairs"),
            "cache_key": payload.get("cache_key"),
            "artifact_hash": (
                R.artifact_hash(R.read_cache_artifact(
                    cache_dir, payload["cache_key"]))
                if payload.get("supported") and payload.get("cache_key")
                else None),
            "status": "ok",
        })

    manifest = R.build_manifest(entries, status="fixture"
                                if args.fixture else "build")
    manifest["generation"] = {
        "comparison_count": len(comparisons),
        "artifact_count": sum(1 for e in entries if e["supported"]),
        "failures": failures,
        "wall_s": time.perf_counter() - t0,
    }
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    tmp = manifest_out.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, sort_keys=True, indent=2))
    tmp.replace(manifest_out)
    print(f"comparisons={len(comparisons)} entries={len(entries)} "
          f"failures={len(failures)} "
          f"wall_s={manifest['generation']['wall_s']:.1f}")
    for failure in failures:
        print(f"FAILURE {failure['comparison']}: {failure['error']}",
              file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
