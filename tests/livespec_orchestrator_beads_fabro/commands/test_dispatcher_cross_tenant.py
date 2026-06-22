"""Tests for the Dispatcher's cross-tenant preflight validation (bd-ib-rsexfp).

When --target-repo and --item point at different tenants, the dispatcher
must emit a clear target-tenant mismatch error BEFORE container/FABRO work
starts — not the generic "not in the ready set" message, which does not
help the operator find the root cause.

The fix validates that explicitly requested --item values exist in the
target-tenant before the readiness check (and before any Fabro run).
"""

import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_FLEET_MANIFEST_TEXT = (
    "// fleet-manifest.jsonc — canned test copy\n"
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [\n'
    '    { "repo": "livespec", "class": "core" },\n'
    '    { "repo": "repo", "class": "impl-plugin" }\n'
    "  ]\n"
    "}\n"
)

_COMMITTED_WORKFLOW_TOML = (
    '[workflow]\ngraph = "graph.toml"\n\n[run.environment]\nid = "fabro-sandbox"\n'
)


@pytest.fixture(autouse=True)
def _cross_tenant_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    scratch = tmp_path_factory.mktemp("fabro-cross-tenant")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setenv("GH_TOKEN", "test-github-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands.dispatcher._fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="livespec-impl-beads-t1",
        type="task",
        status="open",
        title="A ready task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        priority=2,
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)


def _repo_with_workflow(*, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    return repo, workflow


def test_loop_with_item_absent_from_tenant_emits_target_tenant_mismatch_error(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """loop --item <id> absent from the target-tenant exits 3 with a target-tenant error.

    When --item names a work-item that does not exist in the target-tenant
    at all (e.g. the operator passed an id from a different repo's tenant),
    the dispatcher must surface a target-tenant mismatch error BEFORE any
    Fabro work starts, not the generic "not in the ready set" message.
    """
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    # Tenant is empty: foreign-item-xyz belongs to a different tenant.
    exit_code = main(
        [
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--mode",
            "autonomous",
            "--item",
            "foreign-item-xyz",
            "--workflow",
            str(workflow),
        ]
    )
    assert exit_code == 3
    err = capsys.readouterr().err
    assert "foreign-item-xyz" in err
    assert "target-tenant" in err


def test_dispatch_with_item_absent_from_tenant_emits_target_tenant_mismatch_error(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """dispatch --item <id> absent from the target-tenant exits 3 with a target-tenant error.

    Same guarantee as the loop case: an item entirely absent from the
    target-tenant must produce the tenant-mismatch diagnosis before Fabro
    starts, not the generic "not in the ready set" message.
    """
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    # Append one legitimate item so the tenant is non-empty: the operator
    # simply got the wrong --item, not an empty tenant.
    append_work_item(path=_config(), item=_item(id="correct-tenant-item"))
    exit_code = main(
        [
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            "foreign-item-xyz",
            "--workflow",
            str(workflow),
        ]
    )
    assert exit_code == 3
    err = capsys.readouterr().err
    assert "foreign-item-xyz" in err
    assert "target-tenant" in err
