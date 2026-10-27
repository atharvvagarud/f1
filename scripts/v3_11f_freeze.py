#!/usr/bin/env python3
"""V3.11F -- programme freeze records (offline, read-only inputs).

Reads frozen A-E artifacts (never rewrites them) and emits the final
machine-readable programme card under results/v3/v3_11_final/:
  programme_manifest.json, programme_scientific_card.json,
  stage_identity_registry.json, coverage_reconciliation.json,
  terminal_decision.json, validation_manifest.json,
  v39_guard_reconciliation.json

Deterministic. Stdlib only. No production imports. No MC2 execution.
Safe to re-run (same inputs -> identical bytes).

Usage:
    .venv/bin/python scripts/v3_11f_freeze.py
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11_final"

STAGES = ("A", "B", "C", "D", "E")
CARD = {
    "A": "results/v3/v3_11a/scientific_card.json",
    "B": "results/v3/v3_11b/scientific_card.json",
    "C": "results/v3/v3_11c/scientific_card.json",
    "D": "results/v3/v3_11d/scientific_card.json",
    "E": "results/v3/v3_11e/scientific_card.json",
}
DOC = {
    "A": "docs/V3_11A_MC2_COVERAGE_FORENSICS.md",
    "B": "docs/V3_11B_CAUSAL_STATE_RECONSTRUCTION.md",
    "C": "docs/V3_11C_TRACK_SOURCE_REGIME_FORENSICS.md",
    "D": "docs/V3_11D_VSC_REGIME_MODEL.md",
    "E": "docs/V3_11E_VSC_EVIDENCE_RESOLUTION.md",
}
RESULT_ROOT = {
    "A": "results/v3/v3_11a",
    "B": "results/v3/v3_11b",
    "C": "results/v3/v3_11c",
    "D": "results/v3/v3_11d",
    "E": "results/v3/v3_11e",
}
EXPECTED_CLASS = {
    "A": "MC2_COVERAGE_FORENSICS_COMPLETE",
    "B": "CAUSAL_STATE_RECONSTRUCTION_REJECTED",
    "C": "TRACK_SOURCE_REGIME_FORENSICS_COMPLETE",
    "D": "VSC_REGIME_MODEL_INSUFFICIENT_EVIDENCE",
    "E": "VSC_EVIDENCE_STILL_INSUFFICIENT",
}


def _write(name, doc):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / name, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")


def _sha_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.strip()


def main() -> int:
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- frozen parent verification ----
    head = _git("rev-parse", "HEAD")
    parent = _git("rev-parse", "v3.10-pit-wall^{commit}")
    assert head == parent == \
        "2c00e7ea4e61b6477cac3207e8379f087b0ec527", (head, parent)

    # ---- stage identity registry ----
    registry = {}
    for s in STAGES:
        card_p = ROOT / CARD[s]
        doc_p = ROOT / DOC[s]
        res_p = ROOT / RESULT_ROOT[s]
        assert card_p.is_file() and doc_p.is_file() and res_p.is_dir(), s
        card = json.loads(card_p.read_text(encoding="utf-8"))
        assert card["classification"] == EXPECTED_CLASS[s], s
        proto_sha = None
        proto_note = "no predeclared protocol stage"
        if s == "B":
            proto_sha = json.loads((res_p / "reconstruction_protocol.json")
                                   .read_text(
                                       encoding="utf-8"))["protocol_sha256"]
            proto_note = "reconstruction_protocol.json"
        elif s == "D":
            proto_sha = json.loads((res_p / "vsc_validation_protocol.json")
                                   .read_text(
                                       encoding="utf-8"))["protocol_sha256"]
            proto_note = "vsc_validation_protocol.json"
        elif s == "E":
            proto_sha = json.loads(
                (res_p / "evidence_resolution_protocol.json")
                .read_text(encoding="utf-8"))["protocol_sha256"]
            proto_note = "evidence_resolution_protocol.json"
        registry[s] = {
            "stage": f"V3.11{s}",
            "classification": card["classification"],
            "scientific_card": CARD[s],
            "scientific_card_sha256": _sha_file(card_p),
            "protocol_sha256": proto_sha,
            "protocol_source": proto_note,
            "result_root": RESULT_ROOT[s],
            "doc": DOC[s],
            "production_effect": card.get("production_effect"),
        }
    _write("stage_identity_registry.json", {
        "schema_version": "v3.11f-stage-registry-v1",
        "stages": registry,
    })

    # ---- coverage reconciliation (programmatic arithmetic) ----
    cov = json.loads(
        (ROOT / "results" / "v3" / "v3_11b"
         / "coverage_re_evaluation.json").read_text(encoding="utf-8"))
    total = cov["total_candidates"]
    elig = cov["eligible"]
    unsup = cov["unsupported"]
    reasons = cov["reason_counts"]
    assert (total, elig, unsup) == (9644, 3678, 5966)
    assert elig + unsup == total
    assert sum(reasons.values()) == unsup, reasons
    assert reasons == {"MISSING_DRIVER_OBSERVATION": 354,
                       "MISSING_TYRE_STATE": 198,
                       "STALE_ROSTER_OBSERVATION": 3294,
                       "TERMINAL_STATE": 154,
                       "UNSUPPORTED_TRACK_STATE": 1165,
                       "WET_CONDITIONS": 801}, reasons
    pct = round(elig / total * 100, 2)
    assert pct == 38.14, pct
    _write("coverage_reconciliation.json", {
        "schema_version": "v3.11f-coverage-v1",
        "source": "results/v3/v3_11b/coverage_re_evaluation.json "
                  "(frozen B re-affirmation; A-E made zero transitions)",
        "candidate_total": total,
        "eligible_entry": elig,
        "unsupported_entry": unsup,
        "eligible_exit": elig,
        "unsupported_exit": unsup,
        "coverage_entry_pct": pct,
        "coverage_exit_pct": pct,
        "delta_eligible": 0,
        "reason_counts": {
            "STALE": reasons["STALE_ROSTER_OBSERVATION"],
            "TRACK": reasons["UNSUPPORTED_TRACK_STATE"],
            "WET": reasons["WET_CONDITIONS"],
            "MISSING_DRIVER": reasons["MISSING_DRIVER_OBSERVATION"],
            "MISSING_TYRE": reasons["MISSING_TYRE_STATE"],
            "TERMINAL": reasons["TERMINAL_STATE"],
        },
        "arithmetic_verified": True,
    })

    # ---- terminal decision contract ----
    _write("terminal_decision.json", {
        "schema_version": "v3.11f-terminal-v1",
        "programme": "V3.11 MC2 Coverage Expansion",
        "terminal": True,
        "decision": "STOP_V3_11_COVERAGE_EXPANSION",
        "no_further_coverage_stage_authorized": True,
        "vsc_production_integration_authorized": False,
        "sc_research_authorized": False,
        "wet_research_authorized": False,
        "yellow_research_authorized": False,
        "red_restart_research_authorized": False,
        "existing_production_mc2_canonical": True,
        "scientific_reason": "insufficient evidence, not refutation "
                             "(VSC plausible; gap/spread/duration/pit "
                             "underpowered; zero dimensions refuted)",
    })

    # ---- programme manifest + scientific card ----
    prod_diff = _git("diff", "--name-only", "--", "raceintel/", "api/",
                     "frontend/", "ml/")
    prod_status = _git("status", "--short", "--", "raceintel/", "api/",
                       "frontend/", "ml/")
    _write("programme_manifest.json", {
        "schema_version": "v3.11f-manifest-v1",
        "programme": "V3.11 MC2 Coverage Expansion",
        "parent_tag": "v3.10-pit-wall",
        "parent_commit": parent,
        "stages": ["A", "B", "C", "D", "E"],
        "navigation_baseline": ["docs/INDEX.md", "scripts/README.md"],
        "final_synthesis": "docs/V3_11_MC2_COVERAGE_EXPANSION_FINAL.md",
        "production_diff_empty": prod_diff == "",
        "production_status_empty": prod_status == "",
        "eligibility_delta": 0,
    })
    _write("programme_scientific_card.json", {
        "schema_version": "v3.11f-programme-card-v1",
        "programme": "V3.11 MC2 Coverage Expansion",
        "parent": "v3.10-pit-wall / "
                  "2c00e7ea4e61b6477cac3207e8379f087b0ec527",
        "stages": ["A", "B", "C", "D", "E"],
        "stage_classifications": {s: EXPECTED_CLASS[s] for s in STAGES},
        "production_effect": "none",
        "entry_coverage": "3678 / 9644",
        "exit_coverage": "3678 / 9644",
        "final_decision": "STOP_V3_11_COVERAGE_EXPANSION",
        "VSC": "PLAUSIBLE_BUT_INSUFFICIENT_EVIDENCE",
        "SC": "NOT_STARTED",
        "YELLOW": "NOT_STARTED",
        "RED_RESTART": "NOT_STARTED",
        "WET": "NOT_STARTED",
    })

    # ---- validation manifest (pins + guard reviews) ----
    ci_src = (ROOT / "scripts" / "run_ci_tests.py").read_text(
        encoding="utf-8")
    import re
    m = re.search(r"EXPECTED_COLLECTED = (\d+)", ci_src)
    expected = int(m.group(1)) if m else None
    f_tests = 0
    f_path = ROOT / "tests" / "test_v3_11f_freeze.py"
    if f_path.exists():
        tree = ast.parse(f_path.read_text(encoding="utf-8"))
        f_tests = sum(1 for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef)
                      and n.name.startswith("test_"))
    _write("validation_manifest.json", {
        "schema_version": "v3.11f-validation-v1",
        "collection_expected": expected,
        "f_freeze_tests": f_tests,
        "f_pin_formula": "5289 (post-E) + F freeze tests",
        "p0_guard_review": {
            "file": "tests/test_perf_mc2_p0.py",
            "change": "P0-P20 new_prod filter: carve-outs for "
                      "scripts/v3_11* and scripts/README.md",
            "precedent": "V3.10I reconciliation carve-outs in the same "
                         "filter (api/v2_telemetry_, scripts/v3_10)",
            "performance_invariants_changed": False,
            "admitted_paths": "V3.11A-E offline research scripts "
                              "(no production code) + navigation doc",
            "guard_still_strict_for_other_paths": True,
            "verdict": "NOT_WEAKENED",
        },
        "v39_guard_review": {
            "file": "tests/test_v3_10b_workspace_ownership.py",
            "record": "results/v3/v3_11_final/"
                      "v39_guard_reconciliation.json",
            "verdict": "NARROWLY_REPAIRED_EQUAL_STRENGTH",
        },
    })

    # ---- v39 stale-guard reconciliation record ----
    tag_commit = _git("rev-parse",
                      "v3.9-uncertainty-intelligence^{commit}")
    _write("v39_guard_reconciliation.json", {
        "schema_version": "v3.11f-v39-v1",
        "test": "tests/test_v3_10b_workspace_ownership.py::"
                "test_v39_freeze_provenance_unchanged",
        "intended_pin": "V3.9 freeze provenance: tag commit identity",
        "pinned_commit": "fb0d8d8772bdc1343bc6be6c5ff9ee68cddd7203",
        "tag_commit_observed": tag_commit,
        "tag_unmoved": tag_commit ==
        "fb0d8d8772bdc1343bc6be6c5ff9ee68cddd7203",
        "failure_cause": "HEAD == V39_COMMIT half of the assertion: "
                         "time-bound to the V3.9 freeze instant; "
                         "legitimate frozen V3.10 history extended HEAD "
                         "to 2c00e7e (V39 commit is an ancestor)",
        "genuinely_stale": True,
        "repair": "replaced HEAD-equality with merge-base --is-ancestor "
                  "(history preserved + extended, not rewritten); tag "
                  "pin kept verbatim",
        "invariant_preserved": "moved tag or rewritten history still "
                               "fails; legitimate extension passes",
        "weakened": False,
    })
    print(json.dumps({
        "status": "OK", "stages": list(STAGES),
        "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
