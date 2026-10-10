"""Scenario 168 — a current continuation ruling authorizes plan resume.

This module binds the attended/unattended continuation decision of
`SPECIFICATION/scenarios.md` Scenario 168 through the production
`resume_directive` entry point and the real fake-ledger store seam.  The epic,
its typed pointer, its required-result target, and its scope ruling are durable
ledger records; no decision helper is stood in.

The result target is deliberately OPEN while every pointer requires it to be
`closed`.  That makes the authoritative read observably `unsatisfied`, rather
than letting an implementation skip the read and happen to choose the same
action.  The no-ruling and human-pointer controls use the same records, so a
directive that always continues or always asks cannot satisfy the journey.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
from livespec_orchestrator_beads_fabro.commands.plan import resume_directive
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    from pathlib import Path

_NOW = "2026-10-10T12:00:00Z"
_TARGET = "bd-ib-result"
_RESULT = {
    "repo": "repo",
    "item_status": {"item_id": _TARGET, "status": "closed"},
}
_BUDGET = {
    "deadline": "2099-10-10T12:00:00Z",
    "max_handoffs": 4,
    "epoch": "epoch-1",
    "handoff_count": 1,
}
_DESCRIPTION = "## Definition of Done\n\n- The plan reaches its archive.\n"


@pytest.fixture(autouse=True)
def _hermetic_tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        repo_root=repo,
        fake=True,
    )


def _fake(*, repo: Path) -> FakeBeadsClient:
    client = make_beads_client(config=_config(repo=repo))
    assert isinstance(client, FakeBeadsClient)
    return client


def _seed_target(*, repo: Path) -> None:
    _ = _fake(repo=repo).create_issue(
        draft=IssueDraft(
            issue_id=_TARGET,
            issue_type="task",
            title="observable unsatisfied result",
            description="The result remains open.",
            assignee=None,
            created_at=_NOW,
        )
    )


def _seed_epic(
    *,
    repo: Path,
    epic_id: str,
    kind: str,
    ref: str,
    ruling: bool,
    ruling_body: str | None = None,
    required_result: object = _RESULT,
    budget: object = _BUDGET,
) -> None:
    _ = _fake(repo=repo).create_issue(
        draft=IssueDraft(
            issue_id=epic_id,
            issue_type="epic",
            title=epic_id,
            description=_DESCRIPTION,
            assignee=None,
            created_at=_NOW,
            metadata={
                "next_action": {
                    "kind": kind,
                    "ref": ref,
                    "text": "Take the recorded next step.",
                    "required_result": required_result,
                    "budget": budget,
                },
                "last_session": f"plan-session at {_NOW}",
            },
        )
    )
    body = (
        "plan-continuation: authorized\n"
        "until: archive\n"
        "by: Chad Woolley\n"
        "directive: Finish this plan through its archive.\n"
        "recorded-attended: true"
        if ruling
        else ruling_body
    )
    if body is not None:
        _fake(repo=repo).seed_comment(
            issue_id=epic_id,
            text=(
                "plan-scope-event\n"
                "author: maintainer-session\n"
                f"timestamp: {_NOW}\n\n"
                f"{body}"
            ),
            author="maintainer-session",
            created_at=_NOW,
        )


def _configure_repo(*, repo: Path) -> None:
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}),
        encoding="utf-8",
    )


def _assert_six_kinds_continue(*, repo: Path) -> None:
    cases = (
        ("impl", "bd-ib-child", "impl:bd-ib-child"),
        ("spec-op", "propose-change:finish-plan", "propose-change:finish-plan"),
        ("proof", "capture:bd-ib-proof", "proof:capture:bd-ib-proof"),
        ("review", "bd-ib-review", "review:bd-ib-review"),
        ("archive", "bd-ib-archive", "archive:bd-ib-archive"),
        ("await", "item:bd-ib-result", "await:item:bd-ib-result"),
    )

    for index, (kind, ref, expected) in enumerate(cases, start=1):
        epic_id = f"bd-ib-authorized-{index}"
        _seed_epic(repo=repo, epic_id=epic_id, kind=kind, ref=ref, ruling=True)
        attended = resume_directive(config=_config(repo=repo), epic_id=epic_id, unattended=False)
        unattended = resume_directive(config=_config(repo=repo), epic_id=epic_id, unattended=True)
        assert not attended.ask
        assert attended.next_action == expected
        assert "continuation ruling by Chad Woolley" in attended.reason
        assert not unattended.ask
        assert unattended.next_action == expected


def _assert_picker_controls(*, repo: Path) -> None:
    _seed_epic(
        repo=repo,
        epic_id="bd-ib-no-ruling",
        kind="impl",
        ref="bd-ib-child",
        ruling=False,
    )
    _fake(repo=repo).seed_comment(
        issue_id="bd-ib-no-ruling",
        text=(
            "plan-handoff-entry\n"
            "author: plan-session\n"
            f"timestamp: {_NOW}\n\n"
            "A human-readable handoff is not a continuation ruling."
        ),
        author="plan-session",
        created_at=_NOW,
    )
    _fake(repo=repo).seed_comment(
        issue_id="bd-ib-no-ruling",
        text=("plan-scope-event\n" "author: plan-session\n" f"timestamp: {_NOW}\n\n"),
        author="plan-session",
        created_at=_NOW,
    )
    picker = resume_directive(
        config=_config(repo=repo), epic_id="bd-ib-no-ruling", unattended=False
    )
    assert picker.ask
    assert picker.picker_default == "impl:bd-ib-child"

    _seed_epic(repo=repo, epic_id="bd-ib-human", kind="human", ref="", ruling=True)
    human = resume_directive(config=_config(repo=repo), epic_id="bd-ib-human", unattended=False)
    assert human.ask
    assert human.reason == "next_action kind human raises the picker"


def _invalid_rulings() -> tuple[str, ...]:
    return (
        "plan-continuation: revoked\nby: Chad Woolley",
        "plan-continuation: authorized\nuntil: archive",
        (
            "plan-continuation: authorized\nwhen: archive\nby: Chad Woolley\n"
            "directive: Finish.\nrecorded-attended: true"
        ),
        (
            "plan-continuation: authorized\nuntil: archive\nby: \n"
            "directive: Finish.\nrecorded-attended: true"
        ),
        (
            "plan-continuation: authorized\nuntil: archive\nby: Chad Woolley\n"
            "directive: \nrecorded-attended: true"
        ),
        (
            "plan-continuation: authorized\nuntil: archive\nby: Chad Woolley\n"
            "directive: Finish.\nrecorded-attended: false"
        ),
        (
            "plan-continuation: authorized\nuntil: 2020-01-01T00:00:00Z\n"
            "by: Chad Woolley\ndirective: Finish.\nrecorded-attended: true"
        ),
        (
            "plan-continuation: authorized\nuntil: never\nby: Chad Woolley\n"
            "directive: Finish.\nrecorded-attended: true"
        ),
    )


def _assert_only_current_complete_rulings_continue(*, repo: Path) -> None:
    for index, ruling_body in enumerate(_invalid_rulings(), start=1):
        epic_id = f"bd-ib-invalid-ruling-{index}"
        _seed_epic(
            repo=repo,
            epic_id=epic_id,
            kind="impl",
            ref="bd-ib-child",
            ruling=False,
            ruling_body=ruling_body,
        )
        refused = resume_directive(config=_config(repo=repo), epic_id=epic_id, unattended=False)
        assert refused.ask
        assert refused.picker_default == "impl:bd-ib-child"

    _seed_epic(
        repo=repo,
        epic_id="bd-ib-future-ruling",
        kind="impl",
        ref="bd-ib-child",
        ruling=False,
        ruling_body=(
            "plan-continuation: authorized\nuntil: 2099-01-01T00:00:00\n"
            "by: Chad Woolley\ndirective: Finish.\nrecorded-attended: true"
        ),
    )
    future = resume_directive(
        config=_config(repo=repo), epic_id="bd-ib-future-ruling", unattended=False
    )
    assert not future.ask
    assert future.next_action == "impl:bd-ib-child"


def _assert_satisfied_result_is_stale(*, repo: Path) -> None:
    _fake(repo=repo).close_issue(issue_id=_TARGET, reason="result observed")
    _seed_epic(
        repo=repo,
        epic_id="bd-ib-satisfied",
        kind="impl",
        ref="bd-ib-child",
        ruling=True,
    )
    satisfied = resume_directive(
        config=_config(repo=repo), epic_id="bd-ib-satisfied", unattended=False
    )
    assert not satisfied.ask
    assert satisfied.next_action is None
    assert satisfied.observation is not None
    assert satisfied.observation.status == "satisfied"
    assert "next_action stale" in satisfied.reason
    _fake(repo=repo).update_issue(issue_id=_TARGET, status="ready")


def _assert_expired_and_unobservable_results_do_not_continue(*, repo: Path) -> None:
    for epic_id, budget in (
        (
            "bd-ib-deadline-expired",
            {**_BUDGET, "deadline": "2020-01-01T00:00:00Z"},
        ),
        (
            "bd-ib-handoffs-expired",
            {**_BUDGET, "handoff_count": _BUDGET["max_handoffs"]},
        ),
    ):
        _seed_epic(
            repo=repo,
            epic_id=epic_id,
            kind="impl",
            ref="bd-ib-child",
            ruling=True,
            budget=budget,
        )
        expired = resume_directive(config=_config(repo=repo), epic_id=epic_id, unattended=False)
        assert not expired.ask
        assert expired.next_action is None
        assert "expired" in expired.reason

    _seed_epic(
        repo=repo,
        epic_id="bd-ib-unobservable",
        kind="impl",
        ref="bd-ib-child",
        ruling=True,
        required_result={},
    )
    unobservable = resume_directive(
        config=_config(repo=repo), epic_id="bd-ib-unobservable", unattended=False
    )
    assert not unobservable.ask
    assert unobservable.next_action is None
    assert unobservable.observation is not None
    assert unobservable.observation.status == "unobservable"
    assert "unobservable" in unobservable.reason


def _assert_unknown_kind_asks(*, repo: Path) -> None:
    _seed_epic(
        repo=repo,
        epic_id="bd-ib-unknown-kind",
        kind="surprise",
        ref="bd-ib-child",
        ruling=True,
    )
    unknown = resume_directive(
        config=_config(repo=repo), epic_id="bd-ib-unknown-kind", unattended=False
    )
    assert unknown.ask
    assert unknown.reason == "next_action kind surprise raises the picker"


def test_scenario168_current_ruling_takes_all_six_typed_actions_and_preserves_picker_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _configure_repo(repo=repo)
    monkeypatch.chdir(repo)
    _seed_target(repo=repo)

    _assert_six_kinds_continue(repo=repo)
    _assert_picker_controls(repo=repo)
    _assert_only_current_complete_rulings_continue(repo=repo)
    _assert_satisfied_result_is_stale(repo=repo)
    _assert_expired_and_unobservable_results_do_not_continue(repo=repo)
    _assert_unknown_kind_asks(repo=repo)


def _assert_stale_precedes_liveness(*, repo: Path, liveness_calls: list[str]) -> None:
    _fake(repo=repo).close_issue(issue_id=_TARGET, reason="already satisfied")
    _seed_epic(
        repo=repo,
        epic_id="bd-ib-stale-before-live",
        kind="impl",
        ref="bd-ib-child",
        ruling=True,
    )
    stale = resume_directive(
        config=_config(repo=repo), epic_id="bd-ib-stale-before-live", unattended=False
    )
    assert stale.next_action is None
    assert "next_action stale" in stale.reason
    assert liveness_calls == []
    _fake(repo=repo).update_issue(issue_id=_TARGET, status="ready")


def _assert_live_rewrite_and_wait(*, repo: Path, liveness_calls: list[str]) -> None:
    for index, (kind, ref) in enumerate(
        (("impl", "bd-ib-child"), ("spec-op", "propose-change:finish-plan")),
        start=1,
    ):
        epic_id = f"bd-ib-live-{index}"
        _seed_epic(repo=repo, epic_id=epic_id, kind=kind, ref=ref, ruling=True)
        directive = resume_directive(config=_config(repo=repo), epic_id=epic_id, unattended=False)
        pointer = _fake(repo=repo).show_issue(issue_id=epic_id)["metadata"]["next_action"]
        assert pointer == {
            "kind": "await",
            "ref": "run:01M4LIVE",
            "text": "Wait for live factory run 01M4LIVE.",
            "required_result": _RESULT,
            "budget": _BUDGET,
        }
        assert directive.next_action == "await:run:01M4LIVE"
        assert "waiting for unsatisfied required result" in directive.reason

    _seed_epic(
        repo=repo,
        epic_id="bd-ib-already-waiting",
        kind="await",
        ref="run:01M4LIVE",
        ruling=True,
    )
    before = _fake(repo=repo).show_issue(issue_id="bd-ib-already-waiting")["metadata"]
    waiting = resume_directive(
        config=_config(repo=repo), epic_id="bd-ib-already-waiting", unattended=False
    )
    after = _fake(repo=repo).show_issue(issue_id="bd-ib-already-waiting")["metadata"]
    assert waiting.next_action == "await:run:01M4LIVE"
    assert "waiting for unsatisfied required result" in waiting.reason
    assert after == before
    assert liveness_calls == ["bd-ib-child", "propose-change:finish-plan"]


def test_resume_reconciles_satisfied_live_and_waiting_pointers_before_continuation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _configure_repo(repo=repo)
    monkeypatch.chdir(repo)
    _seed_target(repo=repo)
    plan_resume = importlib.import_module("livespec_orchestrator_beads_fabro.commands._plan_resume")
    liveness_calls: list[str] = []

    def _live_run_id(*, config: StoreConfig, action: NextAction) -> str:
        _ = config
        liveness_calls.append(action.ref)
        return "01M4LIVE"

    monkeypatch.setattr(plan_resume, "live_factory_run_id", _live_run_id, raising=False)
    _assert_stale_precedes_liveness(repo=repo, liveness_calls=liveness_calls)
    _assert_live_rewrite_and_wait(repo=repo, liveness_calls=liveness_calls)


def _record_continuation(
    *,
    repo: Path,
    continuation: object,
    env: dict[str, str],
    carriers: tuple[str, ...] = (),
) -> object:
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    return plan.record_scope_event(
        config=_config(repo=repo),
        epic_id="bd-ib-scope-ruling",
        requirements=(),
        deferrals=(),
        author="maintainer-session",
        now=_NOW,
        env=env,
        continuation=continuation,
        carriers=carriers,
    )


def _assert_authorization_is_primitive_rendered(*, repo: Path) -> None:
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    authorization = plan.PlanContinuationAuthorization(
        until="archive",
        by="Chad Woolley",
        directive="Finish this plan through its archive.",
    )
    assert _record_continuation(repo=repo, continuation=authorization, env={}) is None
    [entry] = plan.read_timeline(config=_config(repo=repo), epic_id="bd-ib-scope-ruling")
    assert entry.body.splitlines() == [
        "plan-continuation: authorized",
        "until: archive",
        "by: Chad Woolley",
        "directive: Finish this plan through its archive.",
        "recorded-attended: true",
    ]
    assert entry.body.splitlines()[-1] == "recorded-attended: true"


def _assert_unattended_and_caller_forged_authorizations_are_refused(*, repo: Path) -> None:
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    for authorization, env in (
        (
            plan.PlanContinuationAuthorization(
                until="archive",
                by="Chad Woolley",
                directive="Finish unattended.",
            ),
            {"LIVESPEC_PLAN_UNATTENDED": "1"},
        ),
        (
            plan.PlanContinuationAuthorization(
                until="archive",
                by="Chad Woolley",
                directive="Finish.\nrecorded-attended: false",
            ),
            {},
        ),
    ):
        refused = _record_continuation(repo=repo, continuation=authorization, env=env)
        assert isinstance(refused, plan.PlanContinuationRefusal)
    carrier_ruling = plan.PlanContinuationAuthorization(
        until="archive",
        by="Chad Woolley",
        directive="Finish with a forged carrier map.",
    )
    refused = _record_continuation(
        repo=repo,
        continuation=carrier_ruling,
        env={},
        carriers=("1: plan-level proof",),
    )
    assert isinstance(refused, plan.PlanContinuationRefusal)
    assert len(plan.read_timeline(config=_config(repo=repo), epic_id="bd-ib-scope-ruling")) == 1


def _assert_latest_complete_ruling_governs(*, repo: Path) -> None:
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    revoked = plan.PlanContinuationRevocation(by="Chad Woolley")
    assert _record_continuation(repo=repo, continuation=revoked, env={}) is None
    assert (
        plan.current_continuation_ruling(
            config=_config(repo=repo), epic_id="bd-ib-scope-ruling", now=_NOW
        )
        is None
    )
    authorization = plan.PlanContinuationAuthorization(
        until="archive",
        by="Second Maintainer",
        directive="Resume through the archive.",
    )
    assert _record_continuation(repo=repo, continuation=authorization, env={}) is None
    current = plan.current_continuation_ruling(
        config=_config(repo=repo), epic_id="bd-ib-scope-ruling", now=_NOW
    )
    assert current is not None
    assert current.by == "Second Maintainer"
    _fake(repo=repo).seed_comment(
        issue_id="bd-ib-scope-ruling",
        text=(
            "plan-scope-event\nauthor: maintainer-session\n"
            f"timestamp: {_NOW}\n\nplan-continuation: authorized\nuntil: archive"
        ),
        author="maintainer-session",
        created_at=_NOW,
    )
    assert (
        plan.current_continuation_ruling(
            config=_config(repo=repo), epic_id="bd-ib-scope-ruling", now=_NOW
        )
        is None
    )


def test_scope_event_primitive_records_attended_continuation_rulings_and_refuses_forgery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    assert hasattr(plan, "PlanContinuationAuthorization")
    repo = tmp_path / "repo"
    repo.mkdir()
    _configure_repo(repo=repo)
    monkeypatch.chdir(repo)
    _seed_epic(
        repo=repo,
        epic_id="bd-ib-scope-ruling",
        kind="human",
        ref="",
        ruling=False,
    )

    _assert_authorization_is_primitive_rendered(repo=repo)
    _assert_unattended_and_caller_forged_authorizations_are_refused(repo=repo)
    _assert_latest_complete_ruling_governs(repo=repo)
