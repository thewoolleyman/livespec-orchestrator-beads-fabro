"""The post-merge acceptance pass's PROOF evidence leg.

The proof-evidence-leg clause of `SPECIFICATION/contracts.md` (v114) says the
pass "MUST take as its criteria-leg evidence the `proof_verify` record of the
run whose pull request merged, observed from the pull request", and that it
"MUST NOT apply merged-diff vocabulary matching to an assertion that carries a
proof mode".

THE DISCRIMINATOR IS THE DIFF. Every fixture here hands the pass a merged diff
that shares no significant term with the assertion under judgment, so the
vocabulary matcher could only ever fail it. A verdict of PASS therefore cannot
have come from the diff — it can only have come from the record. A fixture whose
diff happened to carry the assertion's words would pass under BOTH
implementations and would bind neither.

The legacy control is the other half: an item that resolves from the criteria
FIELD declares no proof mode at all, and the clause keeps vocabulary matching
for exactly those items (they are the work already in flight when v114
ratified). Without that control a change that routed EVERY item through the
record would look identical here.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ASSERTION = "The projection carries the parent field."
_RUN_ID = "01M3PROOFRUNID"
_RECORD_URL = "https://example.test/owner/repo/pull/7#issuecomment-900"
# Shares no significant term with `_ASSERTION`: see the module docstring.
_MERGED_DIFF = "diff --git a/x b/x\n+rearranged an unrelated helper\n"
_REFERENCE_LINE = (
    "References: ## Scenario 132 — A factory-captured proof is captured on a"
    " draft pull request, reviewed, replayed and published"
)


@dataclass(kw_only=True)
class _ForgeRunner:
    """One seam answering both forge reads the pass performs, by argv."""

    comments: str
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
        if "comments" in argv:
            return CommandResult(exit_code=0, stdout=self.comments, stderr="")
        return CommandResult(exit_code=0, stdout=_MERGED_DIFF, stderr="")


def _record_body(*, verdict: str, reproduced: str) -> str:
    return textwrap.dedent(f"""\
        Proof of Done — {verdict} — run {_RUN_ID} — 2026-10-01T09:00:00Z

        ## Assertion 1 — {_ASSERTION}

        Proof mode: `factory_captured`

        Reproduction steps, as published:

        1. Run the projection. Produces proof 01.

        Proof 01:

        ```
        every record carries parent
        ```

        Reproduced: {reproduced}
        """)


def _comments_json(*, verdict: str, reproduced: str, run_id: str = _RUN_ID) -> str:
    body = _record_body(verdict=verdict, reproduced=reproduced).replace(_RUN_ID, run_id)
    return json.dumps({"comments": [{"url": _RECORD_URL, "body": body}]})


def _definition_of_done() -> str:
    return textwrap.dedent(f"""\
        ## Definition of Done

        - {_ASSERTION}

        {_REFERENCE_LINE}
        """)


def _item(*, description: str, criteria: str | None = None) -> WorkItem:
    return WorkItem(
        id="bd-ib-proof",
        type="task",
        status="active",
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
        acceptance_policy="ai-only",
        acceptance_criteria=criteria,
    )


def _outcome(*, run_id: str | None = _RUN_ID) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-proof",
        status="green",
        stage="done",
        pr_number=7,
        merge_sha="abc123",
        detail="merged",
        fabro_run_id=run_id,
    )


def test_a_factory_captured_assertion_is_graded_from_the_verified_record(
    tmp_path: Path,
) -> None:
    runner = _ForgeRunner(comments=_comments_json(verdict="verified", reproduced="yes."))

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(description=_definition_of_done()),
        outcome=_outcome(),
        runner=runner,
    )

    assert ["gh", "pr", "view", "7", "--json", "comments"] in runner.argvs
    assert result.verdict == "PASS"
    assert [check.text for check in result.criteria] == [_ASSERTION]
    assert [check.passed for check in result.criteria] == [True]
    assert [check.reason for check in result.criteria] == [
        f"Proof of Done verified record {_RECORD_URL} lists the assertion as reproduced"
    ]


def test_a_record_listing_the_assertion_as_not_reproduced_fails_the_pass(
    tmp_path: Path,
) -> None:
    runner = _ForgeRunner(
        comments=_comments_json(verdict="verified", reproduced="NO. Step 1 printed nothing.")
    )

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(description=_definition_of_done()),
        outcome=_outcome(),
        runner=runner,
    )

    assert result.verdict == "FAIL"
    assert [check.passed for check in result.criteria] == [False]
    assert [check.reason for check in result.criteria] == [
        f"Proof of Done verified record {_RECORD_URL} lists the assertion as not reproduced"
    ]


def test_a_legacy_criteria_field_item_still_grades_on_merged_diff_vocabulary(
    tmp_path: Path,
) -> None:
    """The control: an item declaring no proof mode keeps the pre-v114 leg."""
    runner = _ForgeRunner(comments=_comments_json(verdict="verified", reproduced="yes."))

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(
            description="Rearrange the helper.",
            criteria="- rearranged an unrelated helper.",
        ),
        outcome=_outcome(),
        runner=runner,
    )

    assert ["gh", "pr", "view", "7", "--json", "comments"] not in runner.argvs
    assert result.verdict == "PASS"
    assert [check.reason for check in result.criteria] == ["matched merged diff evidence"]
