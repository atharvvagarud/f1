"""Tier-3 release-command contract (P11-1). Source-safe: stdlib only, reads
tracked files, runs the science preflight against an empty tmp dir. Needs
no corpus, bundle, network, or Docker."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_ci_tests.py"
CORPUS_MANIFEST = ROOT / "scripts" / "ci_corpus_dependent.txt"
PREFLIGHT = ROOT / "scripts" / "check_science_environment.py"
MAKEFILE = ROOT / "Makefile"

RESOLVED_STALE_NODE_IDS = (
    "tests/test_v2_phase4_freeze.py::test_frozen_module_hashes_match",
    "tests/test_v2_phase5_freeze.py::test_freeze_manifest_file_hashes_match",
    "tests/test_v2_phase5_freeze.py::"
    "test_freeze_manifest_generated_cache_not_required",
    "tests/test_v2_phase5_freeze.py::"
    "test_freeze_manifest_documents_authorized_api_main_drift",
    "tests/test_v2_phase5_r7.py::test_head_and_phase4_tag_intact",
    "tests/test_v2_phase6_r6.py::test_pit_disabled_reproduces_r5_result_identity",
    "tests/test_v2_phase6_r71.py::"
    "test_accepted_state_matches_pre_fix_result_identity",
)

CORPUS_COVERED_AFTER_P111 = (
    "tests/test_v2_phase5_freeze.py::"
    "test_generated_cache_required_in_bundle_era",
    "tests/test_v2_phase6_r6.py::test_pit_disabled_reproduces_r5_result_identity",
    "tests/test_v2_phase6_r71.py::"
    "test_accepted_state_matches_pre_fix_result_identity",
)

STDLIB_ALLOW = {"__future__", "argparse", "json", "sys", "pathlib"}


def _makefile_science_block() -> str:
    lines = MAKEFILE.read_text().splitlines()
    start = next(i for i, ln in enumerate(lines)
                 if ln.startswith("science:"))
    block = []
    for ln in lines[start:]:
        block.append(ln)
        if ln and not ln.startswith(("\t", "#", "science:")) \
                and not ln.startswith(" ") and len(block) > 1:
            break
    return "\n".join(block)


def test_science_target_exists():
    assert any(ln.startswith("science:") for ln in
               MAKEFILE.read_text().splitlines())


def test_science_runs_preflight_first():
    block = _makefile_science_block()
    assert "scripts/check_science_environment.py" in block
    preflight_pos = block.index("scripts/check_science_environment.py")
    pytest_pos = block.index("pytest")
    assert preflight_pos < pytest_pos


def test_science_runs_full_suite_without_tier1_selector():
    import re

    block = _makefile_science_block()
    assert "pytest tests/" in block
    for token in ("--deselect", "-k ", "run_ci_tests.py",
                  "ci_corpus_dependent"):
        assert token not in block, token
    # "-m pytest" (module invocation) is legitimate; "-m <marker>" test
    # selection would silently narrow Tier-3 and is forbidden.
    assert not re.search(r"-m (?!pytest\b)", block), block


def test_preflight_missing_corpus_fails_early(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(PREFLIGHT), "--root", str(tmp_path)],
        capture_output=True, text=True, cwd=str(ROOT))
    assert proc.returncode == 2
    combined = proc.stdout + proc.stderr
    assert "MISSING_CORPUS" in combined
    assert ("requires the canonical local scientific corpus" in combined)


def test_preflight_is_stdlib_only():
    tree = ast.parse(PREFLIGHT.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= STDLIB_ALLOW, imported - STDLIB_ALLOW


def test_preflight_has_no_network_or_generation_fallback():
    # Behavioral check over the AST: no risky call targets anywhere
    # (imports are already pinned stdlib-only above, so urllib/socket/
    # subprocess/fastf1/sklearn/pandas cannot even be referenced), and no
    # URL/shell-like string literals. Narration strings (docstring, refusal
    # messages) legitimately name what the preflight refuses to do.
    tree = ast.parse(PREFLIGHT.read_text())
    called: set[str] = set()
    strings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                called.add(func.attr)
            elif isinstance(func, ast.Name):
                called.add(func.id)
        elif isinstance(node, ast.Constant) and isinstance(
                node.value, str):
            strings.append(node.value)
    risky_calls = {"urlopen", "urlretrieve", "socket", "fit",
                   "to_parquet", "download", "retrain", "Popen",
                   "check_output", "check_call"}
    assert not (called & risky_calls), called & risky_calls
    blob = "\n".join(strings).lower()
    for token in ("http://", "https://", "s3://", "pip install",
                  "curl ", "wget "):
        assert token not in blob, token


def test_tier1_selector_mechanism_intact():
    text = RUNNER.read_text()
    for marker in ("EXPECTED_COLLECTED", "CORPUS_MANIFEST",
                   "KNOWN_STALE_NODE_IDS", "SystemExit(2)"):
        assert marker in text, marker


def test_resolved_stale_debt_removed_from_tier1():
    text = RUNNER.read_text()
    for node in RESOLVED_STALE_NODE_IDS:
        assert node not in text, node


def test_corrected_corpus_nodes_classified_corpus_dependent():
    lines = CORPUS_MANIFEST.read_text().splitlines()
    nodes = [ln.strip() for ln in lines
             if ln.strip() and not ln.strip().startswith("#")]
    for node in CORPUS_COVERED_AFTER_P111:
        assert node in nodes, node


def test_python311_contract_preserved():
    text = PREFLIGHT.read_text()
    assert "SUPPORTED_PYTHON_MINOR = 11" in text
    assert "SUPPORTED_PYTHON_MAJOR = 3" in text


def test_science_scope_targets_tests_directory():
    block = _makefile_science_block()
    assert "pytest tests/" in block
    assert "frontend" not in block.split("pytest tests/")[1].split("\n")[0]
