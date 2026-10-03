"""Probe the P12-4 temporal spatial resolver (developer tool, not an API).

    python scripts/probe_spatial_resolver.py --race 2023-r01-R --time 5145.0
    python scripts/probe_spatial_resolver.py --race 2023-r01-R --time 5145.0 --driver 1
    python scripts/probe_spatial_resolver.py --race 2023-r01-R --time 5145.0 --window 5.0 --driver 1

Prints query time, selected observation time, age, availability, raw
and render coordinates. Reads the local P12-2/P12-3 corpus only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raceintel.spatial.resolver import (
    SpatialStoreCache,
    resolve_frame,
    resolve_window,
)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="P12-4 temporal spatial resolver probe")
    parser.add_argument("--root", default=str(ROOT),
                        help="project root (default: repository root)")
    parser.add_argument("--race", required=True,
                        help="race_id (e.g. 2023-r01-R)")
    parser.add_argument("--time", type=float, required=True,
                        help="replay query time T "
                             "(anchor_state_time_s, seconds)")
    parser.add_argument("--driver", type=int, default=None,
                        help="driver_number for single-driver detail")
    parser.add_argument("--window", type=float, default=0.0,
                        help="causal history window in seconds "
                             "(requires --driver)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    cache = SpatialStoreCache()
    store = cache.get(args.root, args.race)
    print(f"race={store.race_id} query_T={args.time}")
    print(f"observations={store.observation_status} "
          f"rows={store.row_count()} "
          f"geometry_ok={store.geometry_ok} "
          f"geometry_problem={store.geometry_problem}")
    if args.driver is not None:
        from raceintel.spatial.resolver import resolve_driver

        state = resolve_driver(store, args.driver, args.time)
        print(f"driver={state.driver_number} "
              f"obs_time={state.observation_time_s} age={state.age_s} "
              f"availability={state.availability}")
        print(f"raw=({state.raw_x}, {state.raw_y}) "
              f"render=({state.render_x}, {state.render_y}) "
              f"source={state.source} status={state.status} "
              f"outside_viewport={state.outside_viewport}")
        if args.window > 0:
            samples = resolve_window(store, args.driver, args.time,
                                     args.window)
            print(f"window[{args.time - args.window}, {args.time}]: "
                  f"{len(samples)} samples")
            for sample in samples[:5]:
                print(f"  t={sample.observation_time_s} "
                      f"raw=({sample.raw_x}, {sample.raw_y}) "
                      f"render=({sample.render_x}, {sample.render_y})")
            if len(samples) > 5:
                print(f"  ... ({len(samples) - 5} more)")
    else:
        frame = resolve_frame(store, args.time, require_geometry=False)
        print(f"frame: fresh={frame.fresh_count} "
              f"stale={frame.stale_count} "
              f"unavailable={frame.unavailable_count}")
        for entry in frame.drivers:
            print(f"  driver={entry.driver_number} "
                  f"obs_time={entry.observation_time_s} age={entry.age_s} "
                  f"{entry.availability} raw=({entry.raw_x}, "
                  f"{entry.raw_y}) render=({entry.render_x}, "
                  f"{entry.render_y})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
