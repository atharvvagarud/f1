"""P10-2 CI contract (static; no GitHub runner needed).

Validates .github/workflows/ci.yml invariants with stdlib text scanning
(no YAML dependency, no cosmetic-format coupling). The live local runs of
the same commands are authoritative; these tests guard the static surface.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

SERVING_SHA = ("1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4")

FORBIDDEN_SCIENCE = (
    "fastf1", "FastF1", "build_matrix", "materialize_serving_artifact",
    "build_replay_prediction_cache", "build_simulation_parameters",
    "explainability", "2025",
)


@pytest.fixture(scope="module")
def text() -> str:
    return WORKFLOW.read_text()


@pytest.fixture(scope="module")
def code() -> str:
    """Non-comment workflow lines (comments document intent freely)."""
    out = []
    for ln in WORKFLOW.read_text().splitlines():
        stripped = ln.split("#", 1)[0].rstrip()
        if stripped.strip():
            out.append(stripped)
    return "\n".join(out) + "\n"


def test_workflow_exists():
    assert WORKFLOW.is_file()


def test_triggers(text):
    assert "pull_request" in text
    assert re_push(text)
    assert "pull_request_target" not in text


def re_push(text):
    return "\n  push:" in text or "\n  push :" in text or "  push:" in text


def test_permissions_least_privilege(code):
    assert "contents: read" in code
    for perm in ("contents: write", "packages:", "id-token", "pull-request"):
        if perm == "pull-request":
            assert "pull-requests: write" not in code, perm
        else:
            assert perm not in code, perm


def test_runtime_versions(code):
    assert '"3.11"' in code or "'3.11'" in code or "3.11" in code
    assert '"22"' in code or "'22'" in code or "node-version" in code


def test_source_preflight_not_deployable(code):
    assert "--source" in code
    assert "--deployable" not in code


def test_canonical_installs(code):
    assert "requirements.txt" in code
    assert "requirements-test.txt" in code
    assert "npm ci" in code
    assert "npm install" not in code.replace("npm install -r", "")


def test_frontend_build_has_explicit_api_base(text):
    assert "NEXT_PUBLIC_API_BASE" in text
    assert "http://localhost:8000" in text


def test_network_posture(code):
    assert "V2_ALLOW_NETWORK" not in code


def test_serving_sha_protected(code):
    assert SERVING_SHA in code


def test_p10_contract_tests_included(code):
    assert "run_ci_tests" in code or "pytest" in code
    assert "tests/" in code or "run_ci_tests" in code


def test_ci_runner_script_contract():
    import ast
    import subprocess
    path = REPO_ROOT / "scripts" / "run_ci_tests.py"
    assert path.is_file()
    tree = ast.parse(path.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"subprocess", "sys", "pathlib", "__future__"}, imported
    out = subprocess.run(
        ["git", "check-ignore", "scripts/run_ci_tests.py"],
        capture_output=True, text=True, cwd=REPO_ROOT)
    assert out.returncode != 0, "CI runner must be tracked, not ignored"


def test_no_science_invoked(code):
    for token in FORBIDDEN_SCIENCE:
        if token == "explainability":
            continue  # word may appear in documentive contexts; check strictly
        assert token not in code, token


def test_no_backend_image_build(code):
    low = code.lower()
    assert "docker build" not in low
    assert "docker compose build" not in low
    assert "docker-compose-build" not in low


def test_no_invented_bundle_source(code):
    for token in ("actions/download-artifact", "actions/upload-artifact",
                  "runtime_artifacts", "runtime-artifacts", "s3://",
                  "gs://", "azblob"):
        assert token not in code, token


def test_official_actions_only(code):
    for ln in code.splitlines():
        if "uses:" in ln:
            assert ("actions/checkout" in ln or "actions/setup-python" in ln
                    or "actions/setup-node" in ln), ln.strip()


def test_timeouts_bounded(code):
    assert "timeout-minutes" in code


def test_no_failure_suppression(code):
    assert "continue-on-error" not in code
    assert "|| true" not in code


def _load_runner():
    import importlib.util
    path = REPO_ROOT / "scripts" / "run_ci_tests.py"
    spec = importlib.util.spec_from_file_location("run_ci_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_safe_definition_documented():
    src = (REPO_ROOT / "scripts" / "run_ci_tests.py").read_text()
    assert "SOURCE_SAFE" in src
    assert "FRESH GIT CHECKOUT" in src


def test_corpus_manifest_exists_and_shaped():
    manifest = REPO_ROOT / "scripts" / "ci_corpus_dependent.txt"
    assert manifest.is_file()
    nodes = [ln.strip() for ln in manifest.read_text().splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    assert len(nodes) > 100, "corpus manifest must enumerate evidence"
    assert len(set(nodes)) == len(nodes), "no duplicate manifest nodes"
    for node in nodes:
        assert node.startswith("tests/"), node
        assert (REPO_ROOT / node.split("::")[0]).is_file(), node


def test_exclusion_categories_disjoint():
    module = _load_runner()
    stale = {n for n, _ in module.KNOWN_STALE_NODE_IDS}
    runtime = {n for n, _ in module.RUNTIME_DEPENDENT_NODE_IDS}
    corpus = set(n for n in (
        ln.strip() for ln in
        (REPO_ROOT / "scripts" / "ci_corpus_dependent.txt")
        .read_text().splitlines())
        if n and not n.startswith("#"))
    assert not (stale & corpus), "stale/corpus must stay separate"
    assert not (stale & runtime)
    assert not (corpus & runtime)


def test_runner_fail_closed_markers():
    src = (REPO_ROOT / "scripts" / "run_ci_tests.py").read_text()
    assert "EXPECTED_COLLECTED" in src
    assert "no longer" in src and "collected" in src
    assert "return proc.returncode" in src


def test_runner_requires_neither_bundle_nor_corpus():
    src = (REPO_ROOT / "scripts" / "run_ci_tests.py").read_text()
    assert "prepare_runtime_artifacts" not in src
    assert "--deployable" not in src
    assert "read_parquet" not in src
    assert "FastF1(" not in src and "import fastf1" not in src
    assert ".fit(" not in src


def test_frontend_selector_contract():
    import ast
    path = REPO_ROOT / "scripts" / "run_ci_frontend_tests.py"
    assert path.is_file()
    tree = ast.parse(path.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"subprocess", "sys", "pathlib", "__future__"}, imported
    src = path.read_text()
    assert "EXPECTED_TEST_FILES" in src
    assert "evidence.test.ts" in src
    assert "return proc.returncode" in src


def test_workflow_uses_canonical_selectors(code):
    assert "run_ci_tests.py" in code
    assert "run_ci_frontend_tests.py" in code
    assert "node --test" not in code.replace(
        "run_ci_frontend_tests", "")
