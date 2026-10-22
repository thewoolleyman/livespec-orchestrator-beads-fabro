"""A falsely derived plan-level obligation is superseded by an await on its carrier.

`bd-ib-evrynu`, the half that unlocks the epics whose records already carry the
defect. Scenario 211 of `scenarios.md` governs, and spec v198 widened the
`misderived` cause for exactly this case: "it names a plan-level step (`proof`,
`review` or `archive`) while a work-item carrier named by the epic's latest
carrier-map scope event was not closed, so the step could not honestly be
taken."

WHY PREVENTION IS NOT ENOUGH, which is the whole reason this module exists
beside the three that gate the derivation. Once a plan-level obligation is
PERSISTED it cannot be re-aimed: `_plan_progress_decision` refuses to rename an
unmet obligation "without evidenced causal supersession", and the `await` a
human would reach for names a work-item in another tenant. Measured 2026-10-22
on plan epic `bd-ib-fyozyd`: after the carrier's repository was made observable,
`set_next_action` carrying an await on it was still refused — `the unmet
obligation ... item_comment bd-ib-fyozyd marker Plan Proof of Done cannot be
renamed ... without evidenced causal supersession` — and the only state left was
a human pointer.

WHAT THE REPLACEMENT MUST NOT BE ALLOWED TO DO, and what every refusal case
here is about. A supersession is the one write that may rename an unmet
obligation, so it is also the one write that could launder an expired deadline
into a fresh one. The clause therefore requires the replacement to "inherit the
superseded obligation's original deadline and consumed handoff count unchanged",
and this module reads BOTH off the persisted pointer rather than off the return
value: the pointer is what the next resume grades its budget against, and a
build that preserved the authority while projecting the candidate's own budget
would satisfy a return-value assertion and still hand the plan a new clock.

WHY THE MODULE IS REACHED THROUGH AN ASSERTION RATHER THAN A TOP-LEVEL IMPORT.
The names under test do not exist when this Red is authored, and a top-level
import of an absent name dies at COLLECTION — which proves only that the name is
absent, never that the behaviour is unimplemented. The first assertion is
therefore a genuine check on the module's own path, and the surface is reached
through `importlib` after it.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    ChainHead,
    CommittedTransition,
    TransitionRequest,
    commit_transition,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    PLAN_PROGRESS_PREFIX,
    chain_cache_metadata,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import create_token
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NextAction,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reference import (
    parse_result_reference,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import ResultReference
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    PLAN_SCOPE_PREFIX,
    plan_comment_body,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = f"{_PACKAGE}._plan_supersession"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_plan_supersession.py"
)

_NOW = "2026-10-22T07:00:00Z"
# Later than the deriving transition, which is what makes "the carrier was open
# WHEN the derivation was recorded" a question about two instants rather than one.
_LATER = "2026-10-22T09:00:00Z"
_DESCRIPTION = "## Definition of Done\n\n- The plan reaches its archive.\n"
_DEADLINE = "2099-10-10T12:00:00Z"
_MAX_HANDOFFS = 4
_CONSUMED_HANDOFFS = 2
_EPIC = "bd-ib-plan"
_OWN = "repo"
_OWN_PREFIX = "bd-ib"
_CARRIER_REPO = "carrier-repo"
_CARRIER_PREFIX = "cr"
_OPEN_CARRIER = f"{_CARRIER_PREFIX}-open"
_DERIVING_OPERATION = "op-derived-while-the-carrier-was-open"
# The carrier's own state in a fixture, spelled rather than flagged: a boolean
# parameter reads as `True` in a test id and says nothing about which state it
# names, and the two states are what every case below differs by.
_OPEN = "open"
_CLOSED = "closed"
_PLAN_RESUME_ACTOR = "plan-resume"
# The obligation the false derivation persisted: the plan's own proof record.
_SUPERSEDED_RESULT: dict[str, object] = {
    "repo": _OWN,
    "item_comment": {"item_id": _EPIC, "marker": PLAN_PROOF_RECORD_TITLE},
}
_CARRIER_RESULT: dict[str, object] = {
    "repo": _CARRIER_REPO,
    "item_status": {"item_id": _OPEN_CARRIER, "status": "closed"},
}


def _canonical_identity(*, required_result: dict[str, object]) -> str:
    """The canonical result identity, ASKED OF the production reference parse.

    Not transcribed. The clause requires the supersession to name "the
    superseded obligation's canonical result identity", and that rendering is
    the reference's own — a literal written here would keep passing after the
    rendering had changed, which is a green that is no longer about anything.
    """
    parsed = parse_result_reference(value=required_result)
    assert isinstance(parsed, ResultReference), parsed
    return parsed.identity


@pytest.fixture(autouse=True)
def _hermetic_tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix=_OWN_PREFIX,
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


def _connection(*, prefix: str) -> dict[str, object]:
    return {"livespec-orchestrator-beads-fabro": {"connection": {"prefix": prefix}}}


def _project(*, tmp_path: Path) -> Path:
    repo = tmp_path / _OWN
    repo.mkdir()
    configured: dict[str, object] = dict(_connection(prefix=_OWN_PREFIX))
    configured["cross_repo_targets"] = {
        _CARRIER_REPO: {"github_url": f"https://github.com/thewoolleyman/{_CARRIER_REPO}"}
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(configured), encoding="utf-8")
    carrier = tmp_path / _CARRIER_REPO
    carrier.mkdir()
    _ = (carrier / ".livespec.jsonc").write_text(
        json.dumps(_connection(prefix=_CARRIER_PREFIX)), encoding="utf-8"
    )
    return repo


def _carrier(*, repo: Path, status: str) -> None:
    fake = _fake(repo=repo)
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=_OPEN_CARRIER,
            issue_type="task",
            title=_OPEN_CARRIER,
            description="a carrier of one plan assertion, in a sibling tenant",
            assignee=None,
            created_at=_NOW,
        )
    )
    if status == _CLOSED:
        fake.close_issue(issue_id=_OPEN_CARRIER, reason="the carrier landed")


def _seed(*, repo: Path, author: str) -> int:
    """An epic whose chain records a plan-level obligation one transition wrote.

    `author` is the party the deriving transition is recorded under — the whole
    discriminator of the `misderived` cause, which is admitted only for an
    obligation "written by a derivation (the `plan-resume` or `plan-archive`
    actor), not by a writer that named it". Returns the epoch that transition
    moved the chain to, which is the epoch the supersession must name.
    """
    required_result = _SUPERSEDED_RESULT
    fake = _fake(repo=repo)
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=_EPIC,
            issue_type="epic",
            title=_EPIC,
            description=_DESCRIPTION,
            assignee=None,
            created_at=_NOW,
            metadata={
                "next_action": {
                    "kind": "proof",
                    "ref": f"capture:{_EPIC}",
                    "text": f"Capture the plan Proof of Done record for {_EPIC}.",
                    "required_result": required_result,
                    "budget": {
                        "deadline": _DEADLINE,
                        "max_handoffs": _MAX_HANDOFFS,
                        "epoch": "1",
                        "handoff_count": _CONSUMED_HANDOFFS,
                    },
                },
                "last_session": f"{author} at {_NOW}",
            },
        )
    )
    genesis = create_token(client=fake)
    fake.update_issue(
        issue_id=_EPIC,
        metadata=chain_cache_metadata(
            existing_metadata=dict(fake.show_issue(issue_id=_EPIC)["metadata"]),
            latest_closed=None,
            current=genesis,
        ),
    )
    config = _config(repo=repo)
    head = read_chain_head(config=config, epic_id=_EPIC)
    assert isinstance(head, ChainHead), head
    committed = commit_transition(
        config=config,
        epic_id=_EPIC,
        request=TransitionRequest(
            operation_id=_DERIVING_OPERATION,
            observed_head=head,
            authority=AuthorityState(
                required_result=required_result,
                original_deadline=_DEADLINE,
                max_handoffs=_MAX_HANDOFFS,
                consumed_handoffs=_CONSUMED_HANDOFFS,
            ),
            event_kind="pointer",
            author=author,
            now=_NOW,
        ),
    )
    assert isinstance(committed, CommittedTransition), committed
    fake.add_comment(
        issue_id=_EPIC,
        body=plan_comment_body(
            prefix=PLAN_SCOPE_PREFIX,
            author="plan-session",
            now=_NOW,
            body=f"carriers:\n- 1: {_OPEN_CARRIER}",
        ),
    )
    return committed.payload.new_epoch


def _replacement() -> NextAction:
    """The await the supersession replaces the falsely derived step with."""
    return NextAction(
        kind="await",
        ref=f"item:{_OPEN_CARRIER}",
        text=f"Wait for plan carrier {_OPEN_CARRIER} to close in {_CARRIER_REPO}.",
        required_result=_CARRIER_RESULT,
        budget={"deadline": _DEADLINE, "max_handoffs": _MAX_HANDOFFS},
    )


def _supersession(*, epoch: int, module: Any, **overrides: object) -> Any:
    fields: dict[str, object] = {
        "superseded_result_identity": _canonical_identity(required_result=_SUPERSEDED_RESULT),
        "previous_epoch": epoch,
        "cause": "misderived",
        "deriving_operation_id": _DERIVING_OPERATION,
        "open_carrier_id": _OPEN_CARRIER,
        "writer": "plan-session",
    }
    fields.update(overrides)
    return module.CausalSupersession(**fields)


def _pointer(*, repo: Path) -> dict[str, object]:
    return dict(_fake(repo=repo).show_issue(issue_id=_EPIC)["metadata"]["next_action"])


def _progress_events(*, repo: Path) -> list[str]:
    return [
        cast("str", comment["text"])
        for comment in _fake(repo=repo).list_comments(issue_id=_EPIC)
        if cast("str", comment["text"]).startswith(PLAN_PROGRESS_PREFIX)
    ]


def test_a_misderived_plan_level_obligation_is_replaced_by_an_await_on_its_carrier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write is accepted, and the replacement keeps BOTH original limits.

    The deriving transition is recorded under the `plan-resume` actor, the
    carrier the epic's latest carrier-map event names was open when it was
    recorded, and it is open still — the three facts spec v198 makes the
    `misderived` cause turn on. So the unmet proof obligation is replaced by an
    await on that carrier's closure.

    The deadline and the consumed handoff count are read off the PERSISTED
    pointer, because that is what the next resume grades its budget against: a
    build preserving the authority while projecting the candidate's own budget
    would hand the plan a fresh clock with every surface still reading correct.
    """
    assert _MODULE_PATH.is_file(), (
        "the causal-supersession surface does not exist yet, so the unmet"
        " obligation cannot be replaced at all"
    )
    module = importlib.import_module(_MODULE)
    repo = _project(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    _carrier(repo=repo, status=_OPEN)
    epoch = _seed(repo=repo, author=_PLAN_RESUME_ACTOR)

    refusal = set_next_action(
        config=_config(repo=repo),
        epic_id=_EPIC,
        action=_replacement(),
        session="plan-session",
        now=_LATER,
        supersession=_supersession(epoch=epoch, module=module),
    )

    assert refusal is None, refusal
    pointer = _pointer(repo=repo)
    assert pointer["kind"] == "await"
    assert pointer["ref"] == f"item:{_OPEN_CARRIER}"
    assert pointer["required_result"] == _CARRIER_RESULT
    budget = cast("dict[str, object]", pointer["budget"])
    assert budget["deadline"] == _DEADLINE
    assert budget["handoff_count"] == _CONSUMED_HANDOFFS
    assert budget["max_handoffs"] == _MAX_HANDOFFS


def test_the_supersession_is_recorded_as_a_progress_event_before_the_pointer_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The durable obligation history names the supersession as its own kind.

    The clause requires the event to be "recorded as a `plan-progress-event` of
    kind `supersession` before the pointer changes", so an operator reading the
    epic's progress history can tell a renamed obligation from an advanced one.
    A replacement that only rewrote the pointer would leave the two
    indistinguishable.
    """
    assert _MODULE_PATH.is_file(), (
        "the causal-supersession surface does not exist yet, so no supersession"
        " event can be recorded"
    )
    module = importlib.import_module(_MODULE)
    repo = _project(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    _carrier(repo=repo, status=_OPEN)
    epoch = _seed(repo=repo, author=_PLAN_RESUME_ACTOR)

    refusal = set_next_action(
        config=_config(repo=repo),
        epic_id=_EPIC,
        action=_replacement(),
        session="plan-session",
        now=_LATER,
        supersession=_supersession(epoch=epoch, module=module),
    )

    assert refusal is None, refusal
    events = _progress_events(repo=repo)
    assert any("event: supersession" in one for one in events), events
    assert module.EVENT_SUPERSESSION == "supersession"


@pytest.mark.parametrize(
    ("label", "author", "carrier_status", "overrides"),
    [
        (
            "a writer that named the obligation itself is no derivation",
            "plan-session",
            _OPEN,
            {},
        ),
        (
            "a carrier already closed when the derivation was recorded",
            _PLAN_RESUME_ACTOR,
            _CLOSED,
            {},
        ),
        (
            "a deriving operation identity no recorded transition carries",
            _PLAN_RESUME_ACTOR,
            _OPEN,
            {"deriving_operation_id": "op-nobody-committed"},
        ),
        (
            "a carrier the epic's latest carrier-map event does not name",
            _PLAN_RESUME_ACTOR,
            _OPEN,
            {"open_carrier_id": f"{_CARRIER_PREFIX}-unmapped"},
        ),
        (
            "a cause outside the ratified closed set",
            _PLAN_RESUME_ACTOR,
            _OPEN,
            {"cause": "a-new-label"},
        ),
    ],
)
def test_an_unverified_supersession_is_refused_and_the_obligation_stands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    author: str,
    carrier_status: str,
    overrides: dict[str, object],
) -> None:
    """Each refusal leaves the pointer and its obligation exactly as they were.

    These are the cases Scenario 211 enumerates, and together they are what
    keeps the cause from becoming a rename with a label attached: a rename
    nothing verified is the evasion the clause forbids, and its only visible
    difference from an evidenced one is the evidence.

    The POINTER is asserted unchanged as well as the refusal, because a write
    that refused and mutated anyway would satisfy a refusal-only assertion while
    having already replaced the obligation.
    """
    assert _MODULE_PATH.is_file(), (
        "the causal-supersession surface does not exist yet, so no refusal can be"
        " attributed to the evidence"
    )
    module = importlib.import_module(_MODULE)
    repo = _project(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    _carrier(repo=repo, status=carrier_status)
    epoch = _seed(repo=repo, author=author)

    refusal = set_next_action(
        config=_config(repo=repo),
        epic_id=_EPIC,
        action=_replacement(),
        session="plan-session",
        now=_LATER,
        supersession=_supersession(epoch=epoch, module=module, **overrides),
    )

    assert refusal is not None, label
    pointer = _pointer(repo=repo)
    assert pointer["kind"] == "proof", label
    assert pointer["required_result"] == _SUPERSEDED_RESULT, label
