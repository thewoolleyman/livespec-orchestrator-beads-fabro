"""The arms of the `release-spec-tier` valve the end-to-end journeys cannot reach.

`tests/integration/test_spec_tier_release_valve_scenario206.py` drives the valve
through the real intake route, which is where every refusal and every routing
belongs. What is left here are the three arms that route cannot produce without
sabotaging the thing it drives: an unreadable specification tree, a
classification that cannot clear the hold it was asked to clear, and an intake
route that fails after the release. Each is staged by recording the held state
directly in the ledger, which is exactly what a prior filing leaves behind.

EACH ARM IS ASSERTED TOGETHER WITH WHAT IT LEAVES BEHIND, because a refusal
payload is the same dictionary whether or not anything was written. The
unreadable-tree refusal must leave no attestation (it precedes the first write);
the two later arms must leave the attestation standing, since the comment is
append-only and the valve says so in its own refusal.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import (
    append_work_item_comment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro.commands import _drive_release_spec_tier_valve as valve
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    SpecChangeTierDecision,
    behaviour_digest,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_outcome import (
    SpecChangeTierOutcome,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_FILING,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.errors import WorkItemNotFoundError
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.spec_stated import SpecStatedVerdict
from returns.io import IOFailure

_ITEM = "bd-ib-arms"
_HEADING = "## A governing clause"
_ACTOR = InvokerIdentity(invoker="human:chad", invoker_source="flag")


@dataclass(frozen=True, kw_only=True)
class _Run:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _runner(*, argv: tuple[str, ...], cwd: Path | None = None) -> _Run:
    _ = (argv, cwd)
    return _Run(returncode=0, stdout="[]")


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
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
        id=_ITEM,
        type="feature",
        status="pending-approval",
        title="An arm of the valve",
        description=f"## Definition of Done\n\n- It does the thing.\n\nReferences: {_HEADING}\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-28T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _held_repo(*, tmp_path: Path) -> Path:
    """A repository whose ledger already records the item as held, as a filing leaves it."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    (spec / "history" / "v001").mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nBody.\n", encoding="utf-8"
    )
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"tenant": "livespec-impl-beads",'
        ' "prefix": "bd-ib", "server_user": "livespec-impl-beads",'
        ' "database": "livespec-impl-beads", "bd_path": "bd", "fake": true}}}',
        encoding="utf-8",
    )
    append_work_item(path=_config(), item=_item())
    held = SpecChangeTierDecision(
        tier="spec-change",
        classification="feature",
        verdict=SpecStatedVerdict(
            kind="unstated", stated_by=(), generalization_target=_HEADING, rationale="not stated"
        ),
        linked_proposal_topic="an-arm-of-the-valve",
    )
    append_work_item_comment(
        path=_config(),
        work_item_id=_ITEM,
        body=spec_change_tier_comment(
            item_id=_ITEM,
            stage=STAGE_FILING,
            decision=held,
            spec_version="1",
            digest=behaviour_digest(item=_item()),
        ),
    )
    return repo


def _release(*, repo: Path) -> dict[str, object]:
    return run_human_valve_action(
        repo=repo,
        action_id=f"release-spec-tier:{_ITEM}:{_HEADING}",
        runner=_runner,
        identity=_ACTOR,
    )


def _attested() -> bool:
    return any(
        comment.text.startswith("livespec-spec-tier-attestation")
        for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM)
    )


def test_an_unreadable_specification_tree_refuses_before_anything_is_written(
    tmp_path: Path,
) -> None:
    repo = _held_repo(tmp_path=tmp_path)
    _ = (repo / "SPECIFICATION" / "contracts.md").write_bytes(b"\xff\xfe not utf-8")

    result = _release(repo=repo)

    assert result["status"] == "failed"
    assert result["domain_error"] == "unresolved-heading"
    assert not _attested()


def test_a_classification_that_cannot_clear_the_hold_leaves_the_attestation_standing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _held_repo(tmp_path=tmp_path)
    monkeypatch.setattr(
        valve,
        "classify_item_spec_change_tier",
        lambda **_kwargs: SpecChangeTierOutcome(
            work_item_id=_ITEM, recorded=None, cause="spec-tree-unreadable"
        ),
    )

    result = _release(repo=repo)

    assert result["status"] == "failed"
    assert result["domain_error"] == "hold-not-cleared"
    assert "spec-tree-unreadable" in str(result["summary"])
    assert "the attestation stands" in str(result["summary"])
    assert _attested()


def test_an_intake_route_that_fails_after_the_release_is_reported_with_the_journal_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _held_repo(tmp_path=tmp_path)
    monkeypatch.setattr(
        valve,
        "apply_intake_dor",
        lambda **_kwargs: IOFailure(WorkItemNotFoundError(item_id=_ITEM)),
    )

    result = _release(repo=repo)

    assert result["status"] == "failed"
    assert result["domain_error"] == "intake-routing-failed"
    assert _ITEM in str(result["summary"])
    journal = result["journal"]
    assert isinstance(journal, dict)
    assert journal["heading"] == _HEADING
    assert _attested()
