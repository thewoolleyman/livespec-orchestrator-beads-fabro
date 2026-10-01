"""Tests for the two Proof of Done hygiene lanes, at the lane boundary.

`tests/integration/test_needs_attention_proof_facts.py` binds the pending-leg
fact through the whole composed snapshot, which is where the ratified arity
claim lives. What this module owns is the staleness COMPARISON, which the
composed pass cannot reach without a forge, and the clearing conditions of both
lanes.

STALENESS FAILS IN TWO INDEPENDENT WAYS and both are asserted: a re-dispatch
publishes a verified record under a new RUN id, while a corrected record from the
same run publishes under a new COMMENT id. A check on either field alone is blind
to the other and would still pass a one-sided test.

AND TWO ABSENCES MUST NOT READ AS STALENESS. A pull request that cannot be read,
and one carrying no `verified` record at all, each yield NO fact: a lane that
treated either as a mismatch would manufacture a finding out of an absent
observation, which is the failure the acceptance pass's evidence rule forbids
everywhere else in this subsystem.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._needs_attention_proof import (
    pending_human_attestation_items,
    stale_proof_pointer_items,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_REPO = "repo"
_RUN_ID = "01M3POINTERRUN"
_RECORD_URL = "https://example.test/owner/repo/pull/11#issuecomment-900"
_HUMAN_ASSERTION = "The production console renders the capacity banner."


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


def _pointer_section(*, run_id: str = _RUN_ID, record_url: str = _RECORD_URL) -> str:
    return (
        "\n## Proof of Done\n"
        "\n"
        "- Pull request: #11\n"
        f"- Verified record: {record_url}\n"
        f"- Run: {run_id}\n"
        "- Timestamp: 2026-10-01T09:00:00Z\n"
        "- Verdict: verified\n"
    )


def _description(*, pointer: str = "", human: bool = False) -> str:
    human_block = (
        "### Human-attested\n"
        "\n"
        "Reason: the sandbox has no session on the production console.\n"
        "\n"
        f"- {_HUMAN_ASSERTION}\n"
        "\n"
        if human
        else ""
    )
    return (
        "## Definition of Done\n"
        "\n"
        "- The factory leg is captured and replayed.\n"
        "\n" + human_block + "References: ## Something\n" + pointer
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-proof",
        type="task",
        status="acceptance",
        title="Task",
        description=_description(pointer=_pointer_section()),
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
        acceptance_policy="ai-then-human",
    )
    return replace(base, **overrides)


def _comments(*, run_id: str = _RUN_ID, url: str = _RECORD_URL) -> str:
    body = (
        f"Proof of Done — verified — run {run_id} — 2026-10-01T09:00:00Z\n"
        "\n"
        "## Assertion 1 — The factory leg is captured and replayed.\n"
        "\n"
        "Reproduced: yes.\n"
    )
    return json.dumps({"comments": [{"url": url, "body": body}]})


def _stale(*, items: list[WorkItem], stdout: str, exit_code: int = 0) -> list[str]:
    runner = _Runner(result=CommandResult(exit_code=exit_code, stdout=stdout, stderr=""))
    facts = stale_proof_pointer_items(
        project_root=Path("/repo"), repo=_REPO, items=items, runner=runner
    )
    return [fact.id for fact in facts]


def test_a_pointer_matching_the_latest_verified_record_is_not_stale() -> None:
    """The control every mismatch case below is measured against."""
    assert _stale(items=[_item()], stdout=_comments()) == []


def test_a_newer_run_and_a_newer_comment_each_make_the_pointer_stale() -> None:
    by_run = _stale(items=[_item()], stdout=_comments(run_id="01M3LATERRUN"))
    by_comment = _stale(items=[_item()], stdout=_comments(url="https://example.test/c/corrected"))

    assert by_run == ["hygiene:stale-proof-pointer:bd-ib-proof"]
    assert by_comment == ["hygiene:stale-proof-pointer:bd-ib-proof"]


def test_an_unobserved_pull_request_yields_no_staleness_finding() -> None:
    """Three absences, none of which is a mismatch.

    An unreadable read, a pull request carrying no `verified` record, and an item
    whose description carries no pointer at all.
    """
    unreadable = _stale(items=[_item()], stdout="", exit_code=1)
    no_verified = _stale(items=[_item()], stdout=json.dumps({"comments": []}))
    no_pointer = _stale(items=[_item(description=_description())], stdout=_comments())

    assert unreadable == []
    assert no_verified == []
    assert no_pointer == []


def test_a_closed_item_is_out_of_scope_and_is_never_read() -> None:
    """A `done` item's pointer is frozen history; the forge is not asked about it."""
    runner = _Runner(result=CommandResult(exit_code=0, stdout=_comments(run_id="other"), stderr=""))

    facts = stale_proof_pointer_items(
        project_root=Path("/repo"),
        repo=_REPO,
        items=[_item(status="done")],
        runner=runner,
    )

    assert facts == []
    assert runner.argvs == []


def test_the_stale_summary_names_the_item_the_run_and_the_pull_request() -> None:
    runner = _Runner(
        result=CommandResult(exit_code=0, stdout=_comments(run_id="01M3LATERRUN"), stderr="")
    )

    fact = stale_proof_pointer_items(
        project_root=Path("/repo"), repo=_REPO, items=[_item()], runner=runner
    )[0]

    assert "bd-ib-proof" in fact.summary
    assert _RUN_ID in fact.summary
    assert "#11" in fact.summary
    assert fact.urgency == "medium"


def test_the_pending_lane_clears_on_every_condition_that_is_not_a_pending_leg() -> None:
    """Four clearing conditions, each removing exactly one trigger.

    Not parked in `acceptance`; no human-attested assertion; no pointer at all;
    and a pointer that already cites the human record. Each would otherwise be
    indistinguishable from the positive case in the composed snapshot, where only
    the fact's presence is visible.
    """
    pending = _item(description=_description(pointer=_pointer_section(), human=True))
    cleared = [
        replace(pending, status="active"),
        _item(),
        _item(description=_description(human=True)),
        _item(
            description=_description(human=True, pointer=_pointer_section())
            + "- Human-attested record: https://example.test/c/2\n"
        ),
    ]

    positive = pending_human_attestation_items(
        project_root=Path("/repo"), repo=_REPO, items=[pending]
    )
    negative = pending_human_attestation_items(
        project_root=Path("/repo"), repo=_REPO, items=cleared
    )

    assert [fact.id for fact in positive] == ["hygiene:pending-human-attestation:bd-ib-proof"]
    assert negative == []
