"""Phase-4 R6 reproducible benchmark harness (descriptive timings only).

Measures the frozen Phase-4 prediction path without asserting any latency
gate:

- service initialization (corpus load + history + artifact)
- RaceIndex construction
- anchor resolution (resolve_target)
- RaceState reconstruction (cold/warm)
- FeatureRequest construction (bridge.requests_for)
- features_for_batch total (bridge.features_for_state)
- model inference (FrozenWinnerPredictor.predict_proba)
- prediction merge/domain (engine._assemble via engine.predict)
- full service prediction (reconstruct + predict)

Two corpus contexts are compared for the same anchor where possible:

A. per-race slice (the R3/R4 context)
B. full 2018-2024 V2Service corpus (the R5 context)

Fixtures are DEVELOPMENT-era only (2018-2024, never 2025). Usage:

    python3.11 scripts/benchmark_phase4.py --mode quick
    python3.11 scripts/benchmark_phase4.py --mode full --reps 5
    python3.11 scripts/benchmark_phase4.py --mode profile --fixture primary

Results print as a table and are saved as JSON to --out (default
/tmp/r6_bench.json). No timing assertions; percentiles are descriptive.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import sys
import time

sys.path.insert(0, ".")

# ---------------------------------------------------------------------------
# Fixtures (R6-A): (label, season, race_id, anchor_driver, anchor_lap, kind).
# T is resolved from the canonical frame at runtime (exact D9 row).
# ---------------------------------------------------------------------------
FIXTURES = (
    ("primary-fullfield", 2023, "2023-r01-R", "alonso", 28, "mid-race full field"),
    ("early-ordinary", 2023, "2023-r01-R", "alonso", 2, "early ordinary"),
    ("stale-rival", 2022, "2022-r07-R", "norris", 30, "stale-rival"),
    ("partial-race", 2021, "2021-r12-R", "hamilton", 2, "partial race"),
    ("red-flag", 2022, "2022-r18-R", "ocon", 2, "red flag"),
)


def _load_frame(entity, seasons):
    import glob as _glob

    from v2.config import V2Paths

    paths = V2Paths.resolve()
    frames = []
    for season in seasons:
        pattern = str(
            paths.processed_dir / entity / f"season={season}" / "*.parquet"
        )
        for path in sorted(_glob.glob(pattern)):
            import pandas as pd

            frames.append(pd.read_parquet(path))
    import pandas as pd

    return pd.concat(frames, ignore_index=True)


def _resolve_anchor(states, race_id, driver, lap):
    sub = states[states["race_id"] == race_id]
    hit = sub[(sub["driver_id"] == driver) & (sub["lap_number"] == lap)]
    if not len(hit):
        raise RuntimeError(f"no anchor row for {(race_id, driver, lap)}")
    row = hit.iloc[0]
    return {
        "race_id": race_id,
        "anchor_driver_id": str(row["driver_id"]),
        "anchor_lap_number": int(row["lap_number"]),
        "anchor_state_time_s": float(row["state_time_s"]),
    }


def _time(fn, reps=1):
    outs = []
    t0 = time.perf_counter()
    last = None
    for _ in range(reps):
        s = time.perf_counter()
        last = fn()
        outs.append(time.perf_counter() - s)
    return last, outs, time.perf_counter() - t0


def _pct(samples, q):
    if not samples:
        return None
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def _summarize(samples):
    return {
        "n": len(samples),
        "min": min(samples),
        "max": max(samples),
        "mean": sum(samples) / len(samples),
        "p50": _pct(samples, 0.50),
        "p95": _pct(samples, 0.95) if len(samples) >= 5 else None,
        "p99": _pct(samples, 0.99) if len(samples) >= 20 else None,
    }


def run_context(label, states, frame_desc, anchor, history, reps, predictor):
    from v2 import race_state as RS
    from v2.race_state_features import RaceStateFeatureBridge
    from v2.race_state_reconstruction import RaceStateReconstructor
    from v2.prediction import RacePredictionEngine

    out = {"context": label, "frame": frame_desc, "anchor": anchor}

    # Roster from the states frame identity columns (identity-only, same
    # universe extract_roster would produce for this race).
    roster = {
        str(r): sorted(g["driver_id"].astype(str).unique().tolist())
        for r, g in states[states["race_id"] == anchor["race_id"]].groupby(
            "race_id"
        )
    }
    t0 = time.perf_counter()
    reconstructor = RaceStateReconstructor(states, roster, race_meta=None)
    out["reconstructor_build_s"] = time.perf_counter() - t0

    obs = RS.AnchorObservation(
        race_id=anchor["race_id"],
        anchor_driver_id=anchor["anchor_driver_id"],
        anchor_lap_number=anchor["anchor_lap_number"],
        anchor_state_time_s=anchor["anchor_state_time_s"],
    )

    # Cold reconstruction (fresh index already built above counts as warm
    # for the index; cold here = first reconstruct call).
    state, s, _ = _time(lambda: reconstructor.reconstruct(obs), reps=1)
    out["reconstruct_cold_s"] = s[0]
    _, s, _ = _time(lambda: reconstructor.reconstruct(obs), reps=reps)
    out["reconstruct_warm_s"] = _summarize(s)

    t0 = time.perf_counter()
    bridge = RaceStateFeatureBridge(states, history)
    out["bridge_build_s"] = time.perf_counter() - t0

    _, s, _ = _time(lambda: bridge.requests_for(state), reps=reps)
    out["requests_for_s"] = _summarize(s)

    batch, s, _ = _time(lambda: bridge.features_for_state(state), reps=1)
    out["features_cold_s"] = s[0]
    if reps > 1:
        _, s, _ = _time(lambda: bridge.features_for_state(state), reps=reps)
        out["features_warm_s"] = _summarize(s)
    else:
        out["features_warm_s"] = {"n": 1, "min": s[0], "max": s[0],
                                  "mean": s[0], "p50": s[0],
                                  "p95": None, "p99": None}

    _, s, _ = _time(lambda: predictor.predict_proba(batch.features),
                    reps=max(reps, 3))
    out["inference_s"] = _summarize(s)

    engine = RacePredictionEngine(bridge, predictor)
    snap, s, _ = _time(lambda: engine.predict(state), reps=1)
    out["predict_cold_s"] = s[0]
    out["observable"] = snap.observable_count
    out["roster"] = snap.roster_size
    return out, reconstructor, bridge, state


def _rss_mb():
    try:
        import resource
        import sys as _sys

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports kilobytes; Darwin reports bytes.
        return peak / 1024.0 / 1024.0 if _sys.platform == "darwin" \
            else peak / 1024.0
    except Exception:  # noqa: BLE001 - informational only
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="quick",
                    choices=["quick", "full", "profile", "memory"])
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--fixture", default="primary-fullfield")
    ap.add_argument("--out", default="/tmp/r6_bench.json")
    args = ap.parse_args()

    import pandas as pd  # noqa: F401  (ensures pandas import timed separately)

    results = {"fixtures": [], "notes": []}

    # Full-corpus load (timed = service-init analogue without artifact).
    t0 = time.perf_counter()
    full_states = _load_frame("driver_lap_state_d9", range(2018, 2025))
    results["corpus_load_s"] = time.perf_counter() - t0
    results["corpus_rows"] = len(full_states)
    results["corpus_races"] = int(full_states["race_id"].nunique())

    t0 = time.perf_counter()
    from v2.features.build_matrix import load_history

    from v2.config import V2Paths

    history = load_history(V2Paths.resolve())
    results["history_load_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    from v2.model_lab.serving import load_frozen_winner_model

    predictor = load_frozen_winner_model()
    results["artifact_load_s"] = time.perf_counter() - t0

    if args.mode == "memory":
        mem = {"rss_after_init_mb": _rss_mb()}
        mem["corpus_rows"] = len(full_states)
        from v2 import race_state as RS
        from v2.prediction import RacePredictionEngine
        from v2.race_state_features import RaceStateFeatureBridge
        from v2.race_state_reconstruction import RaceStateReconstructor

        label, season, race_id, driver, lap, kind = next(
            f for f in FIXTURES if f[0] == args.fixture)
        anchor = _resolve_anchor(full_states, race_id, driver, lap)
        roster = {race_id: sorted(
            full_states[full_states["race_id"] == race_id]["driver_id"]
            .astype(str).unique().tolist())}
        recon = RaceStateReconstructor(full_states, roster)
        bridge = RaceStateFeatureBridge(full_states, history)
        engine = RacePredictionEngine(bridge, predictor)
        mem["rss_after_wiring_mb"] = _rss_mb()
        obs = RS.AnchorObservation(
            race_id=anchor["race_id"],
            anchor_driver_id=anchor["anchor_driver_id"],
            anchor_lap_number=anchor["anchor_lap_number"],
            anchor_state_time_s=anchor["anchor_state_time_s"])
        state = recon.reconstruct(obs)
        snap = engine.predict(state)
        mem["rss_after_first_prediction_mb"] = _rss_mb()
        for _ in range(max(args.reps, 3)):
            engine.predict(recon.reconstruct(obs))
        mem["rss_after_repeated_mb"] = _rss_mb()
        mem["bridge_slice_cache_races"] = list(bridge._slices)
        mem["observable"] = snap.observable_count
        results = {"mode": "memory", "memory": mem, "anchor": anchor}
        with open(args.out, "w") as fh:
            json.dump(results, fh, indent=2, default=str)
        print(json.dumps(mem, indent=2))
        print(f"saved {args.out}")
        return

    if args.mode == "profile":
        wanted = [f for f in FIXTURES if f[0] == args.fixture]
    elif args.mode == "quick":
        wanted = [f for f in FIXTURES if f[0] == args.fixture]
    else:
        wanted = list(FIXTURES)

    for label, season, race_id, driver, lap, kind in wanted:
        anchor = _resolve_anchor(full_states, race_id, driver, lap)
        per_race = full_states[full_states["race_id"] == race_id].reset_index(
            drop=True
        )
        entry = {"label": label, "kind": kind, "anchor": anchor,
                 "per_race_rows": len(per_race)}
        if args.mode == "profile":
            from v2 import race_state as RS
            from v2.race_state_features import RaceStateFeatureBridge
            from v2.race_state_reconstruction import RaceStateReconstructor

            roster = {race_id: sorted(
                per_race["driver_id"].astype(str).unique().tolist())}
            # Profile the FULL-corpus path (the slow one needing explanation).
            recon = RaceStateReconstructor(full_states, roster)
            obs = RS.AnchorObservation(
                race_id=anchor["race_id"],
                anchor_driver_id=anchor["anchor_driver_id"],
                anchor_lap_number=anchor["anchor_lap_number"],
                anchor_state_time_s=anchor["anchor_state_time_s"],
            )
            state = recon.reconstruct(obs)
            bridge = RaceStateFeatureBridge(full_states, history)
            pr = cProfile.Profile()
            pr.enable()
            batch = bridge.features_for_state(state)
            pr.disable()
            buf = io.StringIO()
            ps = pstats.Stats(pr, stream=buf).sort_stats("cumulative")
            ps.print_stats(40)
            entry["profile_full_corpus"] = buf.getvalue()
            entry["profile_rows"] = len(batch)
            results["fixtures"].append(entry)
            continue
        reps = args.reps if args.mode == "full" else 1
        # Context A: per-race slice.
        out_a, _, _, _ = run_context(
            "per-race", per_race,
            f"race slice {race_id} ({len(per_race)} rows)",
            anchor, history, max(reps, 3) if label.startswith("primary")
            else 1, predictor,
        )
        entry["per_race"] = out_a
        # Context B: full corpus (primary fixture always; others 1 rep).
        b_reps = reps if label.startswith("primary") else 1
        out_b, _, _, _ = run_context(
            "full-corpus", full_states,
            f"2018-2024 ({len(full_states)} rows)",
            anchor, history, b_reps, predictor,
        )
        entry["full_corpus"] = out_b
        entry["ratio_features_full_over_race"] = (
            out_b["features_warm_s"]["mean"]
            / max(out_a["features_warm_s"]["mean"], 1e-9)
        )
        results["fixtures"].append(entry)

    with open(args.out, "w") as fh:
        json.dump(results, fh, indent=2, default=str)

    for entry in results["fixtures"]:
        print(f"== {entry['label']} ({entry['kind']}) ==")
        if "profile_full_corpus" in entry:
            print(entry["profile_full_corpus"])
            continue
        for key in ("per_race", "full_corpus"):
            ctx = entry[key]
            fw = ctx["features_warm_s"]
            rw = ctx["reconstruct_warm_s"]
            print(
                f"  {key}: rows(frame)={ctx['frame']} "
                f"recon_warm_p50={rw['p50']*1000:.1f}ms "
                f"features_mean={fw['mean']:.2f}s "
                f"(n={fw['n']}) "
                f"infer_p50={ctx['inference_s']['p50']*1000:.2f}ms "
                f"predict_cold={ctx['predict_cold_s']:.2f}s "
                f"roster={ctx['roster']}/{ctx['observable']}"
            )
        print(f"  ratio full/per-race features: "
              f"{entry['ratio_features_full_over_race']:.1f}x")
    print(f"corpus_load={results['corpus_load_s']:.2f}s "
          f"history_load={results['history_load_s']:.2f}s "
          f"artifact_load={results['artifact_load_s']:.2f}s "
          f"rows={results['corpus_rows']}")
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
