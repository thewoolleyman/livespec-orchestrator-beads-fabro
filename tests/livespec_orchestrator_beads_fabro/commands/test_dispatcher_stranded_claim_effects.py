"""Public recovery transitions retain their legacy path before token cutover."""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_stranded_claim_effects as effects
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-legacy-recovery",
        type="task",
        status="active",
        title="A stranded claim awaiting legacy recovery",
        description="Exercise both public recovery transition helpers.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"connection":{"prefix":"bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def test_public_recovery_transitions_use_the_legacy_writer_when_tokens_are_disabled(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())

    assert effects.release_claim_to_ready(repo=repo, work_item_id="bd-ib-legacy-recovery")
    released = next(iter(read_work_items(path=_config())))
    assert (released.status, released.assignee) == ("ready", None)

    assert effects.rest_claim_for_a_human(repo=repo, work_item_id="bd-ib-legacy-recovery")
    rested = next(iter(read_work_items(path=_config())))
    assert (rested.status, rested.blocked_reason) == ("blocked", "needs-human")
