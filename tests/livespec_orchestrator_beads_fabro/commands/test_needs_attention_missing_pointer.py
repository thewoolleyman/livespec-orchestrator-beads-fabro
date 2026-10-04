"""Tests for the missing-pointer lane's journal read and its unreadable-forge arm.

The lane's composed behaviour is bound through the REAL `needs-attention` CLI in
`tests/integration/test_acceptance_parking_record_scenario138.py`, with a
dispatch-built journal and three clearing controls. What THIS module owns is the
shapes a single dispatch's journal cannot produce: a terminal belonging to ANOTHER
item, a terminal that merged no pull request, and a pull request the forge read
could not reach at all.

EACH ARM YIELDS NO FACT, and that is the point rather than a convenience. The
clause conditions the fact on a `verified` record for the merging run, so every
absent observation here — an unknown pull request, an unreadable one — must
produce silence instead of a finding, exactly as the sibling stale-pointer lane
does. A lane that reported on absence would file hygiene work against every item
whose forge it momentarily could not read.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._needs_attention_missing_pointer import (
    missing_proof_pointer_items,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-nopointer"
_PR_NUMBER = 11
_RUN_ID = "01M3MISSINGRUN"
_ASSERTION = "The dispatched slice lands its change."
_RECORD_URL = "https://example.test/owner/repo/pull/11#issuecomment-700"


class _ForgeRunner:
    """The lane's one external call, standing in for `gh pr view --json comments`."""

    def __init__(self, *, exit_code: int = 0, stdout: str = "") -> None:
        self._exit_code = exit_code
        self._stdout = stdout

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env)
        return CommandResult(exit_code=self._exit_code, stdout=self._stdout, stderr="")


def _verified_comments() -> str:
    body = (
        f"Proof of Done — verified — run {_RUN_ID} — 2026-10-04T09:00:00Z\n"
        "\n"
        f"## Assertion 1 — {_ASSERTION}\n"
        "\n"
        "Reproduced: yes.\n"
    )
    return json.dumps({"comments": [{"url": _RECORD_URL, "body": body}]})


def _item(*, item_id: str = _ITEM_ID) -> WorkItem:
    base = WorkItem(
        id=item_id,
        type="task",
        status="acceptance",
        title="A parked slice",
        description=(
            "## Definition of Done\n\n"
            f"- {_ASSERTION}\n\n"
            "References: ## Effective acceptance criteria\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-04T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-then-human",
    )
    return replace(base)


def _project(*, tmp_path: Path, records: list[dict[str, object]]) -> Path:
    root = tmp_path / "repo"
    (root / "tmp").mkdir(parents=True, exist_ok=True)
    _ = (root / "tmp" / "fabro-dispatch-journal.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    return root


def _terminal(*, work_item_id: str, pr_number: int | None) -> dict[str, object]:
    return {
        "stage": "outcome",
        "outcome": {
            "work_item_id": work_item_id,
            "status": "needs-attention",
            "stage": "acceptance",
            "pr_number": pr_number,
            "merge_sha": "feed01",
            "detail": "merged",
        },
    }


def _dispatch_id_record(*, work_item_id: str) -> dict[str, object]:
    return {"stage": "dispatch-id", "work_item_id": work_item_id, "dispatch_id": _RUN_ID}


@pytest.mark.parametrize(
    ("records", "why"),
    [
        ([], "no terminal at all"),
        ([_terminal(work_item_id="bd-ib-someone-else", pr_number=_PR_NUMBER)], "another item"),
        ([_terminal(work_item_id=_ITEM_ID, pr_number=None)], "merged no pull request"),
    ],
)
def test_a_journal_that_names_no_pull_request_for_the_item_yields_no_fact(
    records: list[dict[str, object]],
    why: str,
    tmp_path: Path,
) -> None:
    """Each way the journal can fail to name THIS item's merged pull request.

    The forge stub is handed a payload that WOULD produce the fact, so every case
    here fails for the journal reason named rather than for a missing record — a
    stub returning nothing would pass all three against a lane that never fires.
    """
    _ = why
    root = _project(
        tmp_path=tmp_path, records=[*records, _dispatch_id_record(work_item_id=_ITEM_ID)]
    )

    facts = missing_proof_pointer_items(
        project_root=root,
        repo="repo",
        items=[_item()],
        runner=_ForgeRunner(stdout=_verified_comments()),
    )

    assert facts == []


def test_an_unreadable_pull_request_is_not_a_missing_pointer(tmp_path: Path) -> None:
    """A failed forge read yields NO fact, never a manufactured one.

    The positive control is the sibling parametrized case's own payload: the
    journal here names the pull request and the dispatch, so the ONLY difference
    from a firing lane is that the read did not succeed.
    """
    root = _project(
        tmp_path=tmp_path,
        records=[
            _terminal(work_item_id=_ITEM_ID, pr_number=_PR_NUMBER),
            _dispatch_id_record(work_item_id=_ITEM_ID),
        ],
    )

    facts = missing_proof_pointer_items(
        project_root=root,
        repo="repo",
        items=[_item()],
        runner=_ForgeRunner(exit_code=1),
    )

    assert facts == []


def test_a_readable_verified_record_for_the_merging_dispatch_does_fire(tmp_path: Path) -> None:
    """The positive control the two negative cases above are measured against.

    Without it, every `facts == []` assertion in this module is equally consistent
    with a lane that can never produce a fact at all — the instrument-aim failure
    this repository's verification discipline names first.
    """
    root = _project(
        tmp_path=tmp_path,
        records=[
            _terminal(work_item_id=_ITEM_ID, pr_number=_PR_NUMBER),
            _dispatch_id_record(work_item_id=_ITEM_ID),
        ],
    )

    facts = missing_proof_pointer_items(
        project_root=root,
        repo="repo",
        items=[_item()],
        runner=_ForgeRunner(stdout=_verified_comments()),
    )

    assert [fact.id for fact in facts] == [f"hygiene:missing-proof-pointer:{_ITEM_ID}"]
    assert f"#{_PR_NUMBER}" in facts[0].summary
