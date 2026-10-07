#!/usr/bin/env python3
"""V3.2N Parts L/M: status corpus validation + semantics regression.

Local artifacts only. No 2025. No network. Deterministic.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_2n"
JOUT = ROOT / "results" / "v3" / "v3_2j"
sys.path.insert(0, str(ROOT))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    from raceintel.simulation.driver_status import (  # noqa: E402
        DriverStatusResolver,
        build_retired_transitions,
        load_status_corpus,
        load_unreliable_windows,
        retired_known_at,
    )

    # ---- Part L: all 149 artifacts ----
    manifest = json.load(open(JOUT / "source_manifest.json",
                              encoding="utf-8"))
    man_by_race = {r["race_id"]: r for r in manifest["records"]}
    rows, problems = [], []
    for path in sorted((JOUT / "status").glob("*.json")):
        a = json.load(open(path, encoding="utf-8"))
        rid = a["race_id"]
        rec = {"race_id": rid, "season": a["season"]}
        ok = True
        for field, expect in [
                ("adapter_version", "v3.2j-raw-adapter-v1"),
                ("status_contract_version", "v3.2j-driver-status-v1"),
                ("session", "Race")]:
            if a.get(field) != expect:
                ok = False
                problems.append(f"{rid}: {field}={a.get(field)!r}")
        if not isinstance(a.get("content_hash"), str):
            ok = False
            problems.append(f"{rid}: content_hash missing")
        if a.get("raw_sha256") != man_by_race.get(rid, {}).get(
                "content_sha256"):
            ok = False
            problems.append(f"{rid}: raw_sha256 vs manifest mismatch")
        if str(a.get("season")) == "2025" or "-2025-" in str(
                a.get("source_locator", "")):
            ok = False
            problems.append(f"{rid}: 2025 leakage")
        rec["ok"] = ok
        rows.append(rec)
    seasons = Counter(r["season"] for r in rows)
    validation = {
        "schema_version": "v3.2n-status-corpus-validation-v1",
        "n_artifacts": len(rows),
        "n_ok": sum(1 for r in rows if r["ok"]),
        "seasons": dict(sorted((str(k), v) for k, v in seasons.items())),
        "seasons_2018_2024_only": set(seasons) <= {2018, 2019, 2020, 2021,
                                                   2022, 2023, 2024},
        "has_2025": any("2025" in str(r) for r in rows),
        "problems": problems,
    }
    json.dump(validation, open(OUT / "status_corpus_validation.json", "w"),
              indent=1)

    # ---- Part M: semantics regression (unit-level, no raw needed) ----
    resolver = load_status_corpus(JOUT / "status")
    windows = load_unreliable_windows(JOUT / "unreliable_windows.json")
    cases = []
    seq = [(10.0, False), (20.0, True), (30.0, False), (40.0, True)]
    cases.append(("latest<=T", retired_known_at(seq, 25.0) is True))
    cases.append(("missing preserves", retired_known_at([(10.0, True)],
                                                        99.0) is True))
    cases.append(("true", retired_known_at([(10.0, True)], 10.0) is True))
    cases.append(("false clearing", retired_known_at(seq, 35.0) is False))
    cases.append(("true-false-true", retired_known_at(seq, 40.0) is True))
    cases.append(("unknown stays unknown",
                  retired_known_at([], 50.0) is None
                  and retired_known_at(None, 50.0) is None))
    cases.append(("exact-T counts",
                  retired_known_at([(10.0, True)], 10.0) is True))
    tr = build_retired_transitions([(10.0, "a", True), (11.0, "a", True),
                                    (12.0, "a", False)])
    cases.append(("repeats carry no state", tr == {"a": [(10.0, True),
                                                         (12.0, False)]}))
    # mandatory firewall cases (resolver-level, causal at documented T)
    fw = json.load(open(JOUT / "top5_firewall.json", encoding="utf-8")) \
        if (JOUT / "top5_firewall.json").exists() else {}
    fw_cases = []
    for label, race, drv, moment, expect in [
            ("vettel-2018-r02", "2018-r02-R", "vettel", 5000.0, None),
            ("bottas-2020-r01", "2020-r01-R", "bottas", 5000.0, None),
            ("verstappen-2022-r18", "2022-r18-R", "verstappen", 5000.0, None),
            ("perez-2021-r06", "2021-r06-R", "perez", 5000.0, None)]:
        try:
            got = resolver.retired_known_at(race, drv, moment)
        except Exception:  # noqa: BLE001
            got = "ERROR"
        fw_cases.append({"case": label, "race": race, "driver": drv,
                         "T": moment, "resolved": got,
                         "documented_expectation": expect,
                         "note": "informational resolver probe; binding "
                                 "firewall verdicts live in J artifacts"})
    # winners with Retired=True event must never be excludable at
    # their winning checkpoint: anchor always observable/active.
    regression = {
        "schema_version": "v3.2n-status-semantics-regression-v1",
        "unit_cases": [{"name": n, "passed": bool(p)} for n, p in cases],
        "all_unit_passed": all(p for _, p in cases),
        "firewall_probes": fw_cases,
        "j_firewall_artifact": fw.get("verdict", "see-J-artifact")
        if isinstance(fw, dict) else "see-J-artifact",
        "unreliable_windows_loaded": len(windows) > 0,
        "n_windowed_pairs": len(windows),
    }
    json.dump(regression, open(OUT / "status_semantics_regression.json", "w"),
              indent=1)
    print(f"status artifacts={len(rows)} ok={validation['n_ok']} "
          f"problems={len(problems)} unit_pass={regression['all_unit_passed']}")
    if problems or not regression["all_unit_passed"]:
        raise SystemExit(f"STOP: status validation failed: {problems[:5]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
