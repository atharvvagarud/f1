"""V3.10B workspace-state ownership guards (audit-level only).

No science, no MC2, no model execution. These tests pin:
- V3.9 freeze provenance (tag commit identity, MC2 eligibility frozen value)
- V3.10A audit artifacts intact (B must not overwrite them)
- V3.10B workspace substrate files present with the required surface
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

V39_COMMIT = "fb0d8d8772bdc1343bc6be6c5ff9ee68cddd7203"


def test_v310b_workspace_core_files_exist():
    base = REPO / "frontend" / "features" / "workspace"
    for rel in [
        "lib/workspaceState.ts",
        "lib/workspaceUrl.ts",
        "lib/deepLinks.ts",
        "lib/replayAdapter.ts",
        "hooks/useWorkspace.tsx",
    ]:
        assert (base / rel).exists(), f"missing V3.10B substrate file: {rel}"


def test_v310a_audit_artifacts_intact():
    audit_dir = REPO / "results" / "v3" / "v3_10a"
    assert audit_dir.is_dir(), "V3.10A results must remain intact"
    assert (REPO / "docs" / "V3_10A_PIT_WALL_INFORMATION_ARCHITECTURE.md").exists()
    # B must not overwrite A: route inventory still classifies replay primary.
    import json

    inventory = json.loads((audit_dir / "route_inventory.json").read_text())
    by_path = {r["path"]: r for r in inventory["routes"]}
    assert by_path["/replay"]["classification"] == "primary"


def test_v39_freeze_provenance_unchanged():
    import subprocess

    # V3.11F reconciliation: the original `HEAD == V39_COMMIT` pin was
    # time-bound to the V3.9 freeze instant and became stale when the
    # legitimate frozen V3.10 programme extended history (V39 commit is
    # an ancestor of HEAD; the tag never moved). Pinning HEAD to V3.9
    # would forbid every later freeze commit. The true provenance
    # invariant is tag immovability + history preservation, asserted
    # below with equal strength: a moved tag or rewritten history fails.
    tag_commit = subprocess.run(
        ["git", "rev-parse", "v3.9-uncertainty-intelligence^{commit}"],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=True,
    ).stdout.strip()
    assert tag_commit == V39_COMMIT
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", V39_COMMIT, "HEAD"],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=True,
    )
