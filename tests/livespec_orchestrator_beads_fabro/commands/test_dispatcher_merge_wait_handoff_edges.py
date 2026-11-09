"""The edges of a handed-off merge wait that the headline cases cannot reach.

Sits beside `test_dispatcher_merge_wait_handoff.py` for the same reason a Red's
test bytes are fixed across its Red-to-Green pair: each of these arms was found by
a coverage measurement taken after that module's Red was authored.

THE SECOND READ IS THE ONE WORTH GUARDING. The handoff is decided on a view that
carries the status-check rollup, which is a separate read from the one that found
the pull request open, so the pull request can change between the two. Every case
here is a way that second read disagrees with the first, and each must rest the
item (or proceed on a merge) rather than hand off a pull request the forge is no
longer known to be about to merge.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import _dispatcher_engine_merge as merge_module
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_merge_wait_handoff_record as record_module,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_merge import (
    outcome_after_await,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_status import parse_pr_view
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-handoff-edge"
_RUN_ID = "01M6VNKFXRA85Q8WF0JV23204B"
_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'
_TENANT_CONFIG = json.dumps(
    {
        "livespec-orchestrator-beads-fabro": {
            "connection": {
                "tenant": "livespec-impl-beads",
                "prefix": "bd",
                "server_user": "livespec-impl-beads",
                "database": "livespec-impl-beads",
                "bd_path": "bd",
                "fake": True,
            }
        }
    }
)


@pytest.fixture(autouse=True)
def _fresh_tenant() -> None:
    reset_fake_singleton()


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text=_DECLARED_CONFIG,
        default_branch="master",
        fabro_factory_name="petri",
    )


def _view(
    *, state: str = "OPEN", armed: bool = True, merge_state: str = "BLOCKED"
) -> CommandResult:
    return CommandResult(
        exit_code=0,
        stdout=json.dumps(
            {
                "number": 4615,
                "state": state,
                "autoMergeRequest": {"enabledAt": "now"} if armed else None,
                "mergeStateStatus": merge_state,
                "mergeCommit": {"oid": "cafe05"} if state == "MERGED" else None,
                "headRefOid": "head1111",
                "baseRefOid": "base2222",
                "statusCheckRollup": [],
            }
        ),
        stderr="",
    )


@dataclass(kw_only=True)
class _Scripted:
    queue: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return self.queue.pop(0)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)
    path: Path | None = None

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _after(*, repo: Path, queue: list[CommandResult]) -> tuple[DispatchOutcome, _Scripted]:
    runner = _Scripted(queue=queue)
    outcome = outcome_after_await(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=repo),
        runner=runner,
        journal=_Journal(),
        merged=None,
        pr_number=4615,
        run_id=_RUN_ID,
        waited_seconds=2400,
    )
    return outcome, runner


@pytest.mark.parametrize(
    "second_read",
    [
        CommandResult(exit_code=1, stdout="", stderr="gh failed"),
        _view(armed=False),
        _view(merge_state="DIRTY"),
        _view(state="CLOSED"),
    ],
    ids=[
        "unreadable",
        "disarmed-between-reads",
        "conflicting-between-reads",
        "closed-between-reads",
    ],
)
def test_a_second_read_that_disagrees_with_the_first_rests_the_item(
    tmp_path: Path, second_read: CommandResult
) -> None:
    outcome, runner = _after(repo=tmp_path, queue=[_view(), second_read])

    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    assert "merge-poll-budget-exhausted" in outcome.detail
    assert outcome.merge_wait_handed_off is None
    assert [argv[:3] for argv in runner.calls] == [["gh", "pr", "view"], ["gh", "pr", "view"]]


def test_a_pull_request_that_merged_between_the_two_reads_proceeds_as_a_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="green",
        stage="done",
        pr_number=4615,
        merge_sha="cafe05",
        detail="merged",
    )
    seen: list[str] = []

    def _post_merge(**kwargs: object) -> DispatchOutcome:
        seen.append(getattr(kwargs["merged"], "state", "?"))
        return sentinel

    monkeypatch.setattr(merge_module, "post_merge", _post_merge)
    monkeypatch.setattr(merge_module, "pr_view_for_merge_sha", lambda **kwargs: kwargs["merged"])

    outcome, _ = _after(repo=tmp_path, queue=[_view(), _view(state="MERGED")])

    assert outcome is sentinel
    assert seen == ["MERGED"]


@pytest.mark.parametrize(
    ("rollup", "expected"),
    [
        ([{"name": "a", "status": "COMPLETED", "conclusion": "success"}], ()),
        ([{"name": "a", "status": "waiting", "conclusion": None}], ("a",)),
        ([{"context": "ci/legacy", "state": "PENDING"}], ("ci/legacy",)),
        ([{"context": "ci/legacy", "state": "expected"}], ("ci/legacy",)),
        ([{"context": "ci/legacy", "state": "SUCCESS"}], ()),
        ([{"context": "ci/legacy", "state": "FAILURE"}], ()),
        ([{"status": "IN_PROGRESS"}], ("unknown",)),
        ([{"name": "a"}], ()),
        ([], ()),
    ],
    ids=[
        "completed",
        "waiting-lower-case",
        "pending-status",
        "expected-status",
        "successful-status",
        "failed-status",
        "unnamed-running-check",
        "entry-with-neither-status-nor-state",
        "empty-rollup",
    ],
)
def test_the_view_names_every_rollup_entry_that_has_not_concluded(
    rollup: list[dict[str, object]], expected: tuple[str, ...]
) -> None:
    payload = {
        "number": 4615,
        "state": "OPEN",
        "autoMergeRequest": None,
        "mergeStateStatus": "BLOCKED",
        "statusCheckRollup": rollup,
    }

    view = parse_pr_view(stdout=json.dumps(payload))

    assert view is not None
    assert view.running_checks == expected


def _store() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="A handed-off item",
        description="Its merge wait was handed off.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-08T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason=None,
    )


def _handed_off(*, repo: Path) -> DispatchOutcome:
    outcome, _ = _after(repo=repo, queue=[_view(), _view(), _required_answer()])
    return outcome


def _required_answer() -> CommandResult:
    return CommandResult(
        exit_code=0,
        stdout=json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "commits": {
                                "nodes": [
                                    {"commit": {"statusCheckRollup": {"contexts": {"nodes": []}}}}
                                ]
                            }
                        }
                    }
                }
            }
        ),
        stderr="",
    )


def test_a_comment_that_fails_the_opener_detector_is_journaled_and_not_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(_TENANT_CONFIG, encoding="utf-8")
    append_work_item(path=_store(), item=_item())

    class _Finding:
        opener = "{{"

    monkeypatch.setattr(record_module, "minijinja_openers_in_text", lambda **_: [_Finding()])
    journal = _Journal()

    record_module.record_merge_wait_handed_off(
        repo=tmp_path,
        item=_item(),
        outcome=_handed_off(repo=tmp_path),
        journal=journal,  # type: ignore[arg-type]
    )

    assert [r["stage"] for r in journal.records] == ["merge-wait-handed-off-refused"]
    assert read_work_item_comments(path=_store(), work_item_id=_ITEM_ID) == ()


def test_a_comment_that_cannot_be_written_is_journaled_and_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(_TENANT_CONFIG, encoding="utf-8")
    journal = _Journal()

    record_module.record_merge_wait_handed_off(
        repo=tmp_path,
        item=_item(),
        outcome=_handed_off(repo=tmp_path),
        journal=journal,  # type: ignore[arg-type]
    )

    assert [r["stage"] for r in journal.records] == ["merge-wait-handed-off-error"]
    assert journal.records[0]["reason"] == "BeadsMappingError"


def test_the_body_states_a_reading_the_forge_never_gave_as_unreported_and_does_not_count_it() -> (
    None
):
    body = record_module.merge_wait_handed_off_comment_body(
        work_item_id=_ITEM_ID,
        run_id=None,
        factory="petri",
        pr_number=None,
        pr_head=None,
        waited_seconds=7,
        running_checks=(),
    )

    assert body.splitlines()[0] == "livespec-merge-wait-handed-off"
    assert body.count("(not reported by the forge view)") == 3
    assert "required checks still running: none" in body
    assert "0 names were left out" in body


def test_a_factory_name_that_is_not_identifier_shaped_is_left_out_and_counted() -> None:
    body = record_module.merge_wait_handed_off_comment_body(
        work_item_id=_ITEM_ID,
        run_id=_RUN_ID,
        factory="a factory {{ x }}",
        pr_number=4615,
        pr_head="head1111",
        waited_seconds=7,
        running_checks=("check-lint",),
    )

    assert "factory:" not in body
    assert "{{" not in body
    assert "1 names were left out" in body
