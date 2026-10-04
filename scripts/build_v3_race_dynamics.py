"""Build the frozen V3.1 dynamics sidecar (deterministic; no training).

Usage:
    python scripts/build_v3_race_dynamics.py [--root .] [--out-dir DIR]
        [--skip-parent-verify] [--force]

Refuses to overwrite an artifact whose provenance disagrees unless
--force is given. Never trains, never evaluates, never touches 2025
performance. Exit nonzero with the contract/provenance violation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from raceintel.features.dynamics import build as B  # noqa: E402
from raceintel.features.dynamics import validation as V  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--skip-parent-verify", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    dest = Path(args.out_dir) if args.out_dir else B.default_out_dir(
        args.root)
    prov_path = dest / B.PROVENANCE_FILE
    if prov_path.exists() and not args.force:
        try:
            existing = json.loads(prov_path.read_text())
        except Exception as exc:
            print(f"build: existing provenance unreadable: {exc}",
                  file=sys.stderr)
            return 2
        print("build: artifact exists and --force not given; refusing "
              "to overwrite. Inspect provenance or rerun with --force.",
              file=sys.stderr)
        print(f"build: existing logical sha: "
              f"{existing.get('logical_content_sha')}")
        return 2

    try:
        result = B.build(root=args.root,
                         out_dir=str(dest),
                         verify_parent=not args.skip_parent_verify)
    except V.DynamicsValidationError as exc:
        print(f"build: VALIDATION FAILURE: {exc}", file=sys.stderr)
        return 2
    prov = result["provenance_record"]
    print(f"build: rows={prov['row_count']} "
          f"features={prov['feature_count']} "
          f"sha={prov['logical_content_sha']}")
    print(f"build: sidecar={result['sidecar']}")
    print(f"build: timings_s={prov['timings_s']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
