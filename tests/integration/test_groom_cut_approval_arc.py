"""Scenario 118 end to end: the groom door, the drafted cut, the approval valve, the filing.

Binds `SPECIFICATION/scenarios.md` "Scenario 118 — A groom workflow variant
drafts a cut, parks it in the ledger, and files only on a recorded approval".
Every other test of this behaviour is narrower than the claim: the unit tier
covers the draft comment and the filing seam separately, and the neighbouring
integration modules cover the apply phase's conformance gate and the criteria
wall. Nothing walked the ARC, and the scenario's whole point is the
relationship between its steps: a draft that files nothing, an approval that
exists as a ledger fact BEFORE anything moves, and a filing that is stamped
with who approved it.

THE ARC RUNS PRODUCTION CODE AT EVERY STEP and stands in only the two things
that are not this repository's: the Fabro CLI (`fabro inspect` is answered with
the payload a terminated run publishes) and the forge. The door is
`groom_dispatch`, the propose phase's ending is the Dispatcher's real post-run
disposition (`post_run_dispositions`, which records the draft and then rests the
item), the approval is the real `drive.run_action` over the
`resolve-blocked:<id>:ready` valve, and the apply phase's ending is that same
post-run disposition handed the filing plan an apply run publishes.

THE ORDER OF THE APPROVAL IS READ OFF THE WRITES, not off the end state. A build
that transitioned the item first and wrote the answer second leaves the same
`ready` item carrying the same comment; only the sequence of the two ledger
writes differs, and a `ready` item is selectable by `next` the instant the
status write returns, so the order is the property.

THE CONTROL LEG IS LOAD-BEARING. A test asserting only that `ready` approves
would pass against an implementation in which a `:backlog` bounce ALSO read as
approval, since such an implementation approves everything. The control answers
the same parked draft with `backlog` and asserts that the item rests at
`backlog`, that nothing is filed, and that the draft reads as unapproved to the
reader the apply gate uses.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import dispatch_workflow_for
from livespec_orchestrator_beads_fabro._store_groom_approval import groom_approval_for
from livespec_orchestrator_beads_fabro.commands import _dispatcher_groom_park
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_door import (
    GroomDispatch,
    groom_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_draft import (
    approved_groom_draft_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    post_run_dispositions,
)
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_item_comments,
    read_work_items,
    update_work_item_status,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-groomarc"
_GROOM_VARIANT = "groom-cut"
_GROOM_DIR = ".fabro/workflows/groom-cut"
_IMPLEMENT_VARIANT = "codex-first"
_IMPLEMENT_DIR = ".fabro/workflows/codex-first"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_PROPOSE_RUN = "01M2PROPOSERUN"
_APPLY_RUN = "01M2APPLYRUN"
_SENTINEL = "LIVESPEC_NEEDS_HUMAN: "

_OPERATOR = InvokerIdentity(invoker="human:chad", invoker_source="flag")
_READY = f"resolve-blocked:{_ITEM_ID}:ready"
_BACKLOG = f"resolve-blocked:{_ITEM_ID}:backlog"
_APPROVAL_ANSWER = "Approved as drafted."
_SEND_BACK_ANSWER = "Too coarse: split the filing from the parsing."
_ANSWER_MARKER = "livespec-human-answer"
_DRAFT_MARKER = "livespec-groom-draft"

_FIRST_SLICE = "Park the drafted cut in the ledger"
_SECOND_SLICE = "File the approved cut host-side"
_DRAFT = (
    f"slice={_FIRST_SLICE} | layer=1 | tier=factory | repo=repo | acceptance=The draft rests. "
    f"| blockers=none ;; slice={_SECOND_SLICE} | layer=2 | tier=factory | repo=repo "
    f"| acceptance=The slices exist. | blockers={_FIRST_SLICE}"
)
# What the apply run publishes after it read the approval off the ledger. The
# approver is the identity the answer comment named, because the filing seam
# stamps whoever the plan says approved and the plan is authored from the
# comment.
_ROUTE = f"{_READY} answer comment on {_ITEM_ID}"
_PLAN = (
    f"livespec-groom-plan | approver={_OPERATOR.invoker} | route={_ROUTE}"
    f" ;; slice={_FIRST_SLICE} | tier=factory | repo=repo"
    " | acceptance=The draft rests as a ledger comment. | blockers=none | spec=no"
    " | scope=Record the draft beside the preserve-by-reference pointer."
    f" ;; slice={_SECOND_SLICE} | tier=factory | repo=repo"
    f" | acceptance=The approved slices exist. | blockers={_FIRST_SLICE} | spec=no"
    " | scope=File through intake routing and close the original."
)


@dataclass(frozen=True, kw_only=True)
class _Write:
    verb: str
    issue_id: str
    status: str | None


@dataclass(frozen=True, kw_only=True)
class _Command:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(kw_only=True)
class _Fabro:
    """The Fabro CLI, answering `inspect` with the account of whichever run is named."""

    accounts: dict[str, str] = field(default_factory=dict)
    inspected: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> _Command:
        _ = (cwd, timeout_seconds, env, stdin)
        run_id = next(run for run in self.accounts if run in argv)
        self.inspected.append(run_id)
        payload = {"run": {"id": run_id, "stderr": f"{_SENTINEL}{self.accounts[run_id]}"}}
        return _Command(exit_code=0, stdout=json.dumps(payload), stderr="")


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.delenv("BEADS_DOLT_PASSWORD", raising=False)
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


def _manifest(*, kind: str) -> str:
    return f'[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "{kind}"\n'


def _repo(*, tmp_path: Path) -> Path:
    """A target registering one groom variant, with the IMPLEMENT one as the default.

    The default is the implement variant so that the pin the door writes can be
    told apart from what an unpinned dispatch would have resolved.
    """
    repo = tmp_path / "repo"
    for directory, kind in ((_GROOM_DIR, "groom"), (_IMPLEMENT_DIR, "implement")):
        target = repo / directory
        target.mkdir(parents=True)
        _ = (target / "workflow.toml").write_text(_manifest(kind=kind), encoding="utf-8")
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "bd-ib",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "default_workflow": _IMPLEMENT_VARIANT,
                        "workflows": {
                            _GROOM_VARIANT: _GROOM_DIR,
                            _IMPLEMENT_VARIANT: _IMPLEMENT_DIR,
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _backlog_epic() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="epic",
        status="backlog",
        title="An epic with more than one coherent done",
        description="It carries more than one coherent done.",
        origin="freeform",
        gap_id=None,
        rank="m",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_criteria="- The epic is decomposed.",
    )


def _tenant() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def _stored() -> WorkItem:
    return _tenant()[_ITEM_ID]


def _comment_bodies() -> tuple[str, ...]:
    comments = read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
    return tuple(comment.text for comment in comments)


def _journal_stages(*, repo: Path) -> list[str]:
    lines = (repo / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line)["stage"] for line in lines]


def _recorded_writes(*, monkeypatch: pytest.MonkeyPatch) -> list[_Write]:
    """Record every comment and status write, delegating to the real verbs."""
    writes: list[_Write] = []
    add_comment = FakeBeadsClient.add_comment
    update_issue = FakeBeadsClient.update_issue

    def recording_add_comment(self: FakeBeadsClient, *, issue_id: str, body: str) -> None:
        writes.append(_Write(verb="add_comment", issue_id=issue_id, status=None))
        add_comment(self, issue_id=issue_id, body=body)

    def recording_update_issue(
        self: FakeBeadsClient, *, issue_id: str, status: str | None = None, **rest: Any
    ) -> None:
        writes.append(_Write(verb="update_issue", issue_id=issue_id, status=status))
        update_issue(self, issue_id=issue_id, status=status, **rest)

    monkeypatch.setattr(FakeBeadsClient, "add_comment", recording_add_comment)
    monkeypatch.setattr(FakeBeadsClient, "update_issue", recording_update_issue)
    return writes


def _terminate_run(
    *, repo: Path, fabro: _Fabro, run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hand the Dispatcher's post-run disposition a groom run that ended at needs-human."""
    monkeypatch.setattr(_dispatcher_groom_park, "ShellCommandRunner", lambda: fabro)
    outcome = DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="the run terminated at its needs-human node",
        fabro_run_id=run_id,
    )
    _ = post_run_dispositions(
        args=argparse.Namespace(
            close_on_merge=False,
            fabro_bin="fabro",
            fabro_factory_target=argparse.Namespace(server=_SERVER),
        ),
        repo=repo,
        item=_stored(),
        outcome=outcome,
        journal=JournalFile(path=repo / "journal.jsonl"),
        wall_clock_seconds=1.0,
        dispatch_context_size=10,
        token_supplier=lambda: "token",
    )


def _open_door_and_propose(
    *, repo: Path, monkeypatch: pytest.MonkeyPatch, fabro: _Fabro
) -> GroomDispatch:
    """The first two steps of the arc, shared by the approving and the control legs."""
    append_work_item(path=_config(), item=_backlog_epic())
    opened = groom_dispatch(
        repo=repo,
        item=_stored(),
        variant=_GROOM_VARIANT,
        journal=JournalFile(path=repo / "journal.jsonl"),
    )
    assert isinstance(opened, GroomDispatch)
    fabro.accounts[_PROPOSE_RUN] = _DRAFT
    _terminate_run(repo=repo, fabro=fabro, run_id=_PROPOSE_RUN, monkeypatch=monkeypatch)
    return opened


def test_a_drafted_cut_is_filed_only_after_a_recorded_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a backlog epic, When it is groomed, approved with ready and applied,
    Then the draft parked first, the approval preceded the transition, and the
    approved slices were filed stamped with that approval."""
    repo = _repo(tmp_path=tmp_path)
    fabro = _Fabro()

    opened = _open_door_and_propose(repo=repo, monkeypatch=monkeypatch, fabro=fabro)
    _assert_draft_parked_and_nothing_filed(repo=repo, opened=opened)

    _press_ready_and_assert_approval_precedes_transition(repo=repo, monkeypatch=monkeypatch)

    # The apply phase: admitted under its claim, it publishes the filing plan.
    update_work_item_status(path=_config(), item_id=_ITEM_ID, status="active", assignee="fabro")
    fabro.accounts[_APPLY_RUN] = _PLAN
    _terminate_run(repo=repo, fabro=fabro, run_id=_APPLY_RUN, monkeypatch=monkeypatch)

    _assert_cut_filed_and_stamped(repo=repo)


def _assert_draft_parked_and_nothing_filed(*, repo: Path, opened: GroomDispatch) -> None:
    assert opened.workflow_name == _GROOM_VARIANT
    assert dispatch_workflow_for(path=_config(), work_item_id=_ITEM_ID) == _GROOM_VARIANT
    assert "groom-dispatch" in _journal_stages(repo=repo)
    assert set(_tenant()) == {_ITEM_ID}
    parked = _stored()
    assert (parked.status, parked.blocked_reason) == ("blocked", "needs-human")
    drafts = [body for body in _comment_bodies() if body.startswith(_DRAFT_MARKER)]
    assert len(drafts) == 1
    assert drafts[0].endswith(_DRAFT)
    assert f"({_GROOM_VARIANT}," in drafts[0].split("\n", 1)[0]
    assert "groom-draft-recorded" in _journal_stages(repo=repo)
    # Unanswered, the draft is not an approved one.
    assert approved_groom_draft_for(path=_config(), work_item_id=_ITEM_ID) is None


def _press_ready_and_assert_approval_precedes_transition(
    *, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writes = _recorded_writes(monkeypatch=monkeypatch)
    result = run_action(repo=repo, action_id=_READY, answer=_APPROVAL_ANSWER, identity=_OPERATOR)

    assert result["status"] == "green"
    assert [(write.verb, write.status) for write in writes] == [
        ("add_comment", None),
        ("update_issue", "ready"),
    ]
    marker_line, _, body = _comment_bodies()[-1].partition("\n")
    assert marker_line.startswith(f"{_ANSWER_MARKER} ({_OPERATOR.invoker} via ")
    assert marker_line.endswith(f"{_READY}):")
    assert body == _APPROVAL_ANSWER
    assert _stored().status == "ready"
    assert set(_tenant()) == {_ITEM_ID}
    assert approved_groom_draft_for(path=_config(), work_item_id=_ITEM_ID) == _GROOM_VARIANT
    assert dispatch_workflow_for(path=_config(), work_item_id=_ITEM_ID) == _GROOM_VARIANT


def _assert_cut_filed_and_stamped(*, repo: Path) -> None:
    tenant = _tenant()
    filed = {item.title: item for item in tenant.values() if item.id != _ITEM_ID}
    assert set(filed) == {_FIRST_SLICE, _SECOND_SLICE}
    # Dependency edges are linked: the second slice waits on the first.
    assert filed[_SECOND_SLICE].depends_on == (
        {"kind": "local", "work_item_id": filed[_FIRST_SLICE].id},
    )
    assert filed[_FIRST_SLICE].depends_on == ()
    # The original is regroomed out against the ids that were filed, and is not
    # moved back to blocked by the needs-human escalation.
    original = tenant[_ITEM_ID]
    assert original.status == "done"
    assert original.resolution == "no-longer-applicable"
    for slice_item in filed.values():
        assert slice_item.id in (original.reason or "")
    assert "groom-cut-filed" in _journal_stages(repo=repo)
    # Every filed slice and the original carry the approval, in a queryable field.
    for stamped in (*filed.values(), original):
        approval = groom_approval_for(path=_config(), work_item_id=stamped.id)
        assert approval is not None
        assert approval.approver == _OPERATOR.invoker
        assert approval.route == _ROUTE


def test_a_backlog_answer_does_not_read_as_approval_and_files_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a parked draft, When the operator answers backlog with feedback,
    Then no slice is filed, the item rests at backlog, and the draft is unapproved."""
    repo = _repo(tmp_path=tmp_path)
    fabro = _Fabro()
    _ = _open_door_and_propose(repo=repo, monkeypatch=monkeypatch, fabro=fabro)
    assert _stored().status == "blocked"

    result = run_action(repo=repo, action_id=_BACKLOG, answer=_SEND_BACK_ANSWER, identity=_OPERATOR)

    assert result["status"] == "green"
    assert result["target_status"] == "backlog"
    assert set(_tenant()) == {_ITEM_ID}
    assert _stored().status == "backlog"
    # The answer is on the ledger after the draft, naming the backlog action, and
    # still does not consent: the disposition is read, not merely the position.
    answer_header = _comment_bodies()[-1].split("\n", 1)[0]
    assert answer_header.startswith(_ANSWER_MARKER)
    assert answer_header.endswith(f"{_BACKLOG}):")
    assert approved_groom_draft_for(path=_config(), work_item_id=_ITEM_ID) is None
    assert groom_approval_for(path=_config(), work_item_id=_ITEM_ID) is None
