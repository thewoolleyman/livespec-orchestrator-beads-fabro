"""Tests for the `accept:<id>` valve's host-captured and human-attested gates.

The ratified journeys are bound through real dispatches — the human leg in
`tests/integration/test_proof_of_done_acceptance_scenarios132_133.py` and the host
leg in `tests/integration/test_host_captured_leg_scenario136.py`. What this module
owns is the discrimination those journeys cannot show from one fixture each: the
valve refuses for several different reasons, and each must say which, because an
item with no pointer and an item whose replay has not been published yet need
different things from the operator.

THE ALL-FACTORY-CAPTURED CONTROL IS NOT OPTIONAL. Every refusal case here would
pass equally well against a valve that had simply stopped accepting anything, so
the ordinary item — no pending leg at all, no pointer, no forge read — closes in
the same module.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._drive_accept_valve import (
    HOST_REPLAY_PENDING_ERR,
    HUMAN_ATTESTATION_PENDING_ERR,
    accept_item,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_HUMAN_ASSERTION = "The production console renders the capacity banner."
_HOST_ASSERTION = "The released build prints its own version on an operator host."
_ATTESTED_BODY = "Proof of Done — human_attested — run alice — 2026-10-01T10:00:00Z\n\nDone.\n"
_HOST_VERIFIED_BODY = (
    "Proof of Done — host_verified — session replaying-session — 2026-10-01T11:00:00Z\n"
    "\n"
    f"## Assertion 1 — {_HOST_ASSERTION}\n"
    "\n"
    "Reproduced: yes.\n"
)


@dataclass(kw_only=True)
class _Runner:
    result: CommandResult
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        return self.result


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


# The pointer section the post-merge write leaves, shared by both fixtures: the
# pull request it names is the ONLY route either leg has to the records.
_POINTER_BLOCK = textwrap.dedent("""
    ## Proof of Done

    - Pull request: #11
    - Verified record: https://example.test/c/1
    - Run: 01M3RUN
    - Timestamp: 2026-10-01T09:00:00Z
    - Verdict: verified
    """)


def _mixed_description(*, pointer: bool = True) -> str:
    section = textwrap.dedent(f"""\
        ## Definition of Done

        - The projection carries the parent field.

        ### Human-attested

        Reason: the sandbox has no session on the production console.

        - {_HUMAN_ASSERTION}

        References: ## Something
        """)
    if not pointer:
        return section
    return section + _POINTER_BLOCK


def _host_description(*, pointer: bool = True) -> str:
    """A host-captured item, with the SAME pointer block the mixed one carries."""
    section = textwrap.dedent(f"""\
        ## Definition of Done

        - The projection carries the parent field.

        ### Host-captured

        Reason: the proof needs the released build installed on an operator host.

        - {_HOST_ASSERTION}

        References: ## Something
        """)
    if not pointer:
        return section
    return section + _POINTER_BLOCK


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-accept",
        type="task",
        status="acceptance",
        title="Task",
        description=_mixed_description(),
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-then-human",
        acceptance_criteria=None,
    )
    return replace(base, **overrides)


def _stored(*, item_id: str) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[item_id]


def _comments(*, bodies: list[str]) -> str:
    return json.dumps(
        {"comments": [{"url": "https://example.test/c/2", "body": body} for body in bodies]}
    )


def _accept(*, item: WorkItem, runner: _Runner | None, tmp_path: Path) -> dict[str, object]:
    append_work_item(path=_config(), item=item)
    return accept_item(
        repo=tmp_path, config=_config(), item=item, action_id=f"accept:{item.id}", runner=runner
    )


def test_an_item_with_no_human_attested_assertion_closes_without_reaching_the_forge(
    tmp_path: Path,
) -> None:
    """The control: the ordinary item is unaffected, and nothing is read."""
    runner = _Runner(result=CommandResult(exit_code=0, stdout=_comments(bodies=[]), stderr=""))
    item = _item(description="## Definition of Done\n\n- It works.\n\nReferences: ## Something\n")

    result = _accept(item=item, runner=runner, tmp_path=tmp_path)

    assert result["status"] == "green"
    assert runner.argvs == []
    assert _stored(item_id=item.id).status == "done"


def test_an_item_outside_acceptance_is_refused_on_its_source_state(tmp_path: Path) -> None:
    item = _item(status="active")

    result = _accept(item=item, runner=None, tmp_path=tmp_path)

    assert result["status"] == "failed"
    assert _stored(item_id=item.id).status == "active"


@pytest.mark.parametrize(
    ("description", "comments", "detail"),
    [
        (
            _mixed_description(pointer=False),
            _comments(bodies=[_ATTESTED_BODY]),
            "carries no Proof of Done pointer",
        ),
        (_mixed_description(), _comments(bodies=[]), "no such record on pull request #11"),
        (_mixed_description(), "not json", "no such record on pull request #11"),
    ],
)
def test_each_reason_the_human_leg_is_unobserved_refuses_in_its_own_words(
    description: str,
    comments: str,
    detail: str,
    tmp_path: Path,
) -> None:
    """Three refusals, and the FIRST is the one a record alone cannot satisfy.

    Its fixture carries a perfectly good human-attested record on the pull
    request and still refuses, because the item's description names no pull
    request to look at — which is the whole reason the pointer, not the branch,
    is the route.
    """
    runner = _Runner(result=CommandResult(exit_code=0, stdout=comments, stderr=""))
    item = _item(description=description)

    result = _accept(item=item, runner=runner, tmp_path=tmp_path)

    assert result["status"] == "failed"
    assert result["domain_error"] == HUMAN_ATTESTATION_PENDING_ERR
    summary = result["summary"]
    assert isinstance(summary, str)
    assert _HUMAN_ASSERTION in summary
    assert detail in summary
    assert "Proof of Done — human_attested — <human identity> — <UTC timestamp>" in summary
    assert _stored(item_id=item.id).status == "acceptance"


@pytest.mark.parametrize(
    ("description", "comments", "detail"),
    [
        (
            _host_description(pointer=False),
            _comments(bodies=[_HOST_VERIFIED_BODY]),
            "carries no Proof of Done pointer",
        ),
        (
            _host_description(),
            _comments(bodies=[]),
            "no host_verified record on pull request #11 lists them as reproduced",
        ),
        (
            _host_description(),
            "not json",
            "no host_verified record on pull request #11 lists them as reproduced",
        ),
    ],
)
def test_each_reason_the_host_leg_is_unobserved_refuses_in_its_own_words(
    description: str,
    comments: str,
    detail: str,
    tmp_path: Path,
) -> None:
    """Three refusals, and the FIRST is the one a record alone cannot satisfy.

    Its fixture carries a perfectly good `host_verified` record on the pull request
    and still refuses, because the item's description names no pull request to look
    at — a host record on an unidentified pull request is exactly what the clause
    calls not evidence.

    The THIRD is the unreadable read, and it refuses rather than accepting: a failed
    read is evidence of nothing, and the valve disposes only on observed evidence.
    """
    runner = _Runner(result=CommandResult(exit_code=0, stdout=comments, stderr=""))
    item = _item(description=description)

    result = _accept(item=item, runner=runner, tmp_path=tmp_path)

    assert result["status"] == "failed"
    assert result["domain_error"] == HOST_REPLAY_PENDING_ERR
    summary = result["summary"]
    assert isinstance(summary, str)
    assert _HOST_ASSERTION in summary
    assert detail in summary
    assert "Proof of Done — host_verified — <session identity> — <UTC timestamp>" in summary
    assert _stored(item_id=item.id).status == "acceptance"


def test_a_host_verified_record_lets_the_host_only_item_close_with_no_pointer_rewrite(
    tmp_path: Path,
) -> None:
    """The positive control for the host leg, and the pointer it does NOT touch.

    `host_verified_url` is not a pointer field this build writes — the pointer's
    host link arrives with the posting primitive — so the valve closes the item and
    leaves the section exactly as the post-merge write left it. Asserting that is
    what keeps a later slice's addition an intentional change rather than a silent
    one.
    """
    runner = _Runner(
        result=CommandResult(exit_code=0, stdout=_comments(bodies=[_HOST_VERIFIED_BODY]), stderr="")
    )
    item = _item(description=_host_description())

    result = _accept(item=item, runner=runner, tmp_path=tmp_path)

    assert result["status"] == "green"
    assert runner.argvs == [["gh", "pr", "view", "11", "--json", "comments"]]
    assert _stored(item_id=item.id).status == "done"
    assert _stored(item_id=item.id).description == item.description


def test_a_host_leg_outranks_a_human_leg_on_the_same_item(tmp_path: Path) -> None:
    """Both legs pending: the refusal names the HOST one, which an agent can clear.

    The modes are ordered `factory_captured`, `host_captured`, `human_attested`, and
    reporting the human leg first would hand the operator work that needs them while
    the agent-performable leg sat unmentioned.
    """
    description = (
        "## Definition of Done\n"
        "\n"
        "### Host-captured\n"
        "\n"
        "Reason: the proof needs the released build on an operator host.\n"
        "\n"
        f"- {_HOST_ASSERTION}\n"
        "\n"
        "### Human-attested\n"
        "\n"
        "Reason: the sandbox has no session on the production console.\n"
        "\n"
        f"- {_HUMAN_ASSERTION}\n"
        "\n"
        "References: ## Something\n"
    ) + _POINTER_BLOCK
    runner = _Runner(
        result=CommandResult(exit_code=0, stdout=_comments(bodies=[_ATTESTED_BODY]), stderr="")
    )

    result = _accept(item=_item(description=description), runner=runner, tmp_path=tmp_path)

    assert result["domain_error"] == HOST_REPLAY_PENDING_ERR
    summary = result["summary"]
    assert isinstance(summary, str)
    assert _HOST_ASSERTION in summary
    assert _HUMAN_ASSERTION not in summary


def test_a_posted_human_attested_record_lets_the_same_item_close(tmp_path: Path) -> None:
    """The positive control: the SAME item and valve, one comment different."""
    runner = _Runner(
        result=CommandResult(exit_code=0, stdout=_comments(bodies=[_ATTESTED_BODY]), stderr="")
    )
    item = _item()

    result = _accept(item=item, runner=runner, tmp_path=tmp_path)

    assert result["status"] == "green"
    assert runner.argvs == [["gh", "pr", "view", "11", "--json", "comments"]]
    assert _stored(item_id=item.id).status == "done"


def test_closing_on_the_human_record_leaves_a_pointer_carrying_both_links(
    tmp_path: Path,
) -> None:
    """Scenario 133 — "its pointer carries both record links".

    `done` for a mixed item means BOTH records observed, and the pointer is the
    only durable place that fact is written down: the valve's own result is a
    transient payload and the pull request's comments are not the item's record.
    The verified link is asserted beside the human one, because a rewrite that
    replaced the section rather than extending it would satisfy a check for the
    human link alone while destroying the evidence the acceptance pass graded.
    """
    runner = _Runner(
        result=CommandResult(exit_code=0, stdout=_comments(bodies=[_ATTESTED_BODY]), stderr="")
    )
    item = _item()

    result = _accept(item=item, runner=runner, tmp_path=tmp_path)

    assert result["status"] == "green"
    description = _stored(item_id=item.id).description
    assert "- Human-attested record: https://example.test/c/2" in description
    assert "- Verified record: https://example.test/c/1" in description
    assert "- Pull request: #11" in description
    assert description.count("## Proof of Done") == 1
