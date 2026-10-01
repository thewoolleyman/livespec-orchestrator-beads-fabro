"""Tests for the `accept:<id>` valve's human-attested gate.

The ratified journey — a mixed item parking after merge and the valve refusing —
is bound through a real dispatch in
`tests/integration/test_proof_of_done_acceptance_scenarios132_133.py`. What this
module owns is the discrimination that journey cannot show from one fixture: the
valve refuses for THREE different reasons, and each must say which, because an
item with no pointer and an item whose human has not posted yet need different
things from the operator.

THE ALL-FACTORY-CAPTURED CONTROL IS NOT OPTIONAL. Every refusal case here would
pass equally well against a valve that had simply stopped accepting anything, so
the ordinary item — no human-attested assertion, no pointer, no forge read at all
— closes in the same module.
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
_ATTESTED_BODY = "Proof of Done — human_attested — run alice — 2026-10-01T10:00:00Z\n\nDone.\n"


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
    return section + textwrap.dedent("""
        ## Proof of Done

        - Pull request: #11
        - Verified record: https://example.test/c/1
        - Run: 01M3RUN
        - Timestamp: 2026-10-01T09:00:00Z
        - Verdict: verified
        """)


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
