"""D3 CLI tests: framework commands only, tmp roots, offline."""

from raceintel.cli import main


def test_status_without_manifest_fails_clearly(tmp_path):
    assert main(["--root", str(tmp_path), "status"]) == 2


def test_plan_requires_explicit_scope(tmp_path):
    assert main(["--root", str(tmp_path), "plan"]) == 2
    assert main(["--root", str(tmp_path), "plan",
                 "--season", "2023"]) == 2


def test_unknown_adapter_fails_clearly(tmp_path):
    assert main(["--root", str(tmp_path), "plan", "--season", "2023",
                 "--rounds", "1"]) == 0
    assert main(["--root", str(tmp_path), "run", "--adapter", "jolpica-bulk",
                 "--all-pending"]) == 2


def test_full_framework_loop_in_tmp_root(tmp_path, capsys):
    root = str(tmp_path)
    assert main(["--root", root, "validate-config"]) == 0
    assert main(["--root", root, "plan", "--season", "2023",
                 "--rounds", "1", "2"]) == 0
    assert main(["--root", root, "run", "--adapter", "synthetic",
                 "--all-pending"]) == 0
    assert main(["--root", root, "status"]) == 0
    out = capsys.readouterr().out
    assert "complete: 2" in out
    # Second run skips COMPLETE units without new work.
    assert main(["--root", root, "run", "--adapter", "synthetic",
                 "--all-pending"]) == 0
    assert "nothing pending" in capsys.readouterr().out


def test_run_persists_manifest_after_each_unit(tmp_path, monkeypatch):
    """Crash-safety: the on-disk manifest must reflect unit N as COMPLETE
    before unit N+1 starts (previously it stayed PENDING on disk until the
    final save, so `status` showed no progress and a kill lost all work)."""
    import json

    import raceintel.cli as cli_mod
    from raceintel.config import V2Paths
    from raceintel.data.synthetic import synthetic_adapter

    root = str(tmp_path)
    assert main(["--root", root, "plan", "--season", "2023",
                 "--rounds", "1", "2"]) == 0
    paths = V2Paths.from_root(tmp_path)
    manifest_path = paths.manifest_path("manifest.json")
    observed: dict = {}

    def probing_adapter(ctx):
        if ctx.entry.unit_id.endswith("r02-R"):
            on_disk = json.loads(manifest_path.read_text())
            first_id = "2023-r01-R"
            observed["first_on_disk"] = on_disk["units"][first_id]["status"]
        return synthetic_adapter(ctx)

    monkeypatch.setattr(cli_mod, "_adapters",
                        lambda _orig=cli_mod._adapters: {
                            **_orig(),
                            "synthetic": probing_adapter})
    assert main(["--root", root, "run", "--adapter", "synthetic",
                 "--all-pending"]) == 0
    assert observed.get("first_on_disk") == "complete"


def test_run_persists_downloading_claim_before_network(tmp_path,
                                                         monkeypatch):
    """The DOWNLOADING claim must be on disk BEFORE the adapter's blocking
    network work, so a live `status` observes it mid-unit (previously the
    claim lived only in memory until the unit finished)."""
    import json

    import raceintel.cli as cli_mod
    from raceintel.config import V2Paths
    from raceintel.data.synthetic import synthetic_adapter

    root = str(tmp_path)
    assert main(["--root", root, "plan", "--season", "2023",
                 "--rounds", "1"]) == 0
    paths = V2Paths.from_root(tmp_path)
    manifest_path = paths.manifest_path("manifest.json")
    observed: dict = {}

    def claiming_adapter(ctx):
        on_disk = json.loads(manifest_path.read_text())
        observed["status_on_disk"] = (
            on_disk["units"][ctx.entry.unit_id]["status"])
        observed["claimed_by"] = (
            on_disk["units"][ctx.entry.unit_id]["claimed_by"])
        return synthetic_adapter(ctx)

    monkeypatch.setattr(
        cli_mod, "_adapters",
        lambda _orig=cli_mod._adapters: {
            **_orig(), "synthetic": claiming_adapter})
    assert main(["--root", root, "run", "--adapter", "synthetic",
                 "--all-pending"]) == 0
    assert observed.get("status_on_disk") == "downloading"
    assert observed.get("claimed_by")  # run id persisted with the claim


def test_recover_stale_returns_crashed_claims_only(tmp_path):
    from raceintel.config import V2Paths
    from raceintel.manifests import Manifest, UnitStatus

    root = str(tmp_path)
    assert main(["--root", root, "plan", "--season", "2023",
                 "--rounds", "1", "2"]) == 0
    paths = V2Paths.from_root(tmp_path)
    manifest_path = paths.manifest_path("manifest.json")
    manifest = Manifest.load(manifest_path)
    manifest.transition("2023-r01-R", UnitStatus.DOWNLOADING, run_id="dead")
    manifest.get("2023-r01-R").claimed_at = "2020-01-01T00:00:00+00:00"
    manifest.transition("2023-r02-R", UnitStatus.DOWNLOADING, run_id="live")
    manifest.save(manifest_path)
    assert main(["--root", root, "recover-stale",
                 "--max-age-s", "60"]) == 0
    reloaded = Manifest.load(manifest_path)
    assert reloaded.get("2023-r01-R").status == UnitStatus.PENDING
    assert reloaded.get("2023-r02-R").status == UnitStatus.DOWNLOADING


def test_retry_requeues_failed(tmp_path):
    from raceintel.manifests import Manifest, UnitStatus
    from raceintel.config import V2Paths

    root = str(tmp_path)
    assert main(["--root", root, "plan", "--season", "2023",
                 "--rounds", "5"]) == 0
    paths = V2Paths.from_root(tmp_path)
    manifest = Manifest.load(paths.manifest_path("manifest.json"))
    manifest.transition("2023-r05-R", UnitStatus.DOWNLOADING, run_id="x")
    manifest.transition("2023-r05-R", UnitStatus.FAILED,
                        error_category="transient", error_message="x")
    manifest.save(paths.manifest_path("manifest.json"))
    assert main(["--root", root, "retry", "--status", "failed"]) == 0
    reloaded = Manifest.load(paths.manifest_path("manifest.json"))
    assert reloaded.get("2023-r05-R").status == UnitStatus.PENDING
