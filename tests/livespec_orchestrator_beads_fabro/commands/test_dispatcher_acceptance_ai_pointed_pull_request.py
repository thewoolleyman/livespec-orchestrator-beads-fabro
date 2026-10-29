"""The acceptance pass resolves the merged pull request through the item's pointer.

A dispatch that found its work already merged opens no pull request, so its outcome
carries no pull request number. Reading the proof leg from that outcome alone reports
the merge as unknown ("pull request number unavailable") even though the pointer the
earlier merge wrote names it. The pass takes the number off the pointer for the proof
read, and a pull request holding only a `captured` record is then reported with that
record named rather than as an unreadable one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from pathlib import Path

_ASSERTION = "The projection carries the parent field."
_RUN_ID = "d547aa765bb3427cb43e70ebc9fd54a6"
_CAPTURED_URL = "https://example.test/owner/repo/pull/7#issuecomment-1"
_DESCRIPTION = f"## Definition of Done\n\n- {_ASSERTION}\n\nReferences: ## Something\n"
_POINTER = (
    "\n## Proof of Done\n\n"
    "- Pull request: #7\n"
    "- Verified record: https://example.test/c/9\n"
    f"- Run: {_RUN_ID}\n"
    "- Timestamp: 2026-10-27T00:46:00Z\n"
    "- Verdict: host_verified\n"
)
_CAPTURED_BODY = f"Proof of Done — captured — run {_RUN_ID} — 2026-10-27T00:46:00Z\n\nCaptured.\n"


@dataclass(kw_only=True)
class _ForgeRunner:
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
        comments = [{"url": _CAPTURED_URL, "body": _CAPTURED_BODY}]
        return CommandResult(exit_code=0, stdout=json.dumps({"comments": comments}), stderr="")


def _item(*, description: str) -> WorkItem:
    return WorkItem(
        id="bd-ib-pointed",
        type="bug",
        status="acceptance",
        title="Task",
        description=description,
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


def _outcome_without_a_pull_request() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-pointed",
        status="green",
        stage="done",
        pr_number=None,
        merge_sha=None,
        detail="work already merged",
        fabro_run_id=_RUN_ID,
    )


def test_the_proof_leg_reads_the_pull_request_the_pointer_names(tmp_path: Path) -> None:
    runner = _ForgeRunner()

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(description=_DESCRIPTION + _POINTER),
        outcome=_outcome_without_a_pull_request(),
        runner=runner,
    )

    assert ["gh", "pr", "view", "7", "--json", "comments"] in runner.argvs
    assert result.proof is not None
    assert "unavailable" not in result.proof.reason
    assert [one.record_comment for one in result.proof.assertions] == [_CAPTURED_URL]
    assert result.verdict == "NEEDS_ATTENTION"


def test_without_a_pointer_the_missing_pull_request_stays_unknown(tmp_path: Path) -> None:
    runner = _ForgeRunner()

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(description=_DESCRIPTION),
        outcome=_outcome_without_a_pull_request(),
        runner=runner,
    )

    assert not [argv for argv in runner.argvs if "comments" in argv]
    assert result.proof is not None
    assert result.proof.reason == "pull request number unavailable"
