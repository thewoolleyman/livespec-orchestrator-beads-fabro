"""Attributing a Proof of Done record to the dispatch whose pull request merged.

The proof-evidence-leg clause of `SPECIFICATION/contracts.md` (v115) says the
pass "MUST accept either identifier the Dispatcher can attribute to the merging
dispatch — the Fabro run id, or the dispatch id the Dispatcher declared to the
sandbox — so a `verified` record stamped with the dispatch id is attributed to
the merging run exactly as one stamped with the Fabro run id is".

WHY A REAL RECORD CARRIES THE DISPATCH ID RATHER THAN THE FABRO RUN ID. The
capture stage resolves its own run id from `$FABRO_RUN_ID` and falls back to
`git config --get livespec.factoryRunId`, the marker
`_dispatcher_factory_provenance` writes into the sandbox clone's local config —
and `$FABRO_RUN_ID` is unset inside the stage, so the fallback is what every
record is stamped with. Measured on PR #2538 (work-item `bd-ib-mxqrr4`): both
records name `f195238b76b942698485a780611fe1ef`, the DISPATCH id, while the pass
asked for the Fabro run id `01M3WH8Z10278S5V4SV9WRYW20`, found no record, and
reported every assertion unevidenced.

BOTH DIRECTIONS ARE ASSERTED AND NEITHER MEANS ANYTHING ALONE. A widening that
accepted whatever verified record was newest would satisfy the dispatch-id case
just as well, so the refusal of a record belonging to NO dispatch this item ever
had is its control; and a reader that attributed nothing would satisfy that
refusal just as well, so the accepted identifiers are the refusal's control.

THE ACCEPTED SET IS EVERY JOURNALED DISPATCH OF THE ITEM, NOT THE NEWEST ONE.
This file asserted the opposite until 2026-10-05, and the correction is the point:
"the dispatch that merged" is the dispatch that PUBLISHED THE MERGED HEAD, and a
run that dies after publishing is recovered by a LATER dispatch, which the journal
then records after it. Measured 2026-10-05 on `bd-ib-qm4luz`: run
01M44F9E56XCEWZNMVJX4M14Z6 published pull request 2581 and captured and verified
its Proof of Done there; `reconcile-merged` then parked the item NEEDS_ATTENTION
reporting "records read for run e6a5f80fef944709a8b8062c7660c67f or
1b09f96002d24d25ab372219cb9751ae" — the identifiers of the LATEST journaled
dispatch, neither of which the merged head's record carries. Choosing the most
recent journal row is therefore the nonconformance, and the fail-closed boundary
moves from "the newest dispatch" to "any dispatch this item was journaled under".

THE IDENTIFIERS ARE RESOLVED FROM A REAL ON-DISK JOURNAL, not handed in.
`reconcile-merged` re-runs the pass from another process against an outcome it
built itself from a resolved merged pull request, so that outcome carries no
Fabro run id at all and no `DispatchOutcome` has ever carried the dispatch id.
The dispatch journal is the only place both identifiers survive, and a test that
supplied them directly would pass against a build that could not recover them.
"""

from __future__ import annotations

import importlib
import json
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_parking_record import (
    parking_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    read_proof_leg,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_leg import (
    PROOF_RECORD_EVIDENCE_LEG,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attribution"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_proof_attribution.py"
)

_ITEM_ID = "bd-ib-attribution"
# The two identifier SHAPES a real dispatch produces, kept visibly different so a
# fixture cannot accidentally satisfy a build that confuses them: the Fabro run
# id is a ULID, the dispatch id a uuid4 hex.
_FABRO_RUN_ID = "01M3WH8Z10278S5V4SV9WRYW20"
_DISPATCH_ID = "f195238b76b942698485a780611fe1ef"
_EARLIER_FABRO_RUN_ID = "01M2EARLIERRUNIDAAAAAAAAAA"
_EARLIER_DISPATCH_ID = "aaaa1111bbbb2222cccc3333dddd4444"
# An identifier belonging to NO dispatch of this item: the fail-closed boundary of
# the widening, and the only shape a record on this pull request can take that the
# pass must still refuse.
_UNJOURNALED_RUN_ID = "01M9STRANGERRUNIDZZZZZZZZZ"

_ASSERTION = "The projection carries the parent field."
_RECORD_URL = "https://example.test/owner/repo/pull/7#issuecomment-900"
# Shares no significant term with `_ASSERTION`, so the merged-diff vocabulary
# matcher could only ever fail it: a PASS here cannot have come from the diff.
_MERGED_DIFF = "diff --git a/x b/x\n+rearranged an unrelated helper\n"
# One physical line: the criteria segmenter starts a block at a list marker or a
# heading, so a wrapped reference line continues the preceding block and would be
# read as a second assertion.
_REFERENCE_LINE = (
    "References: ## Scenario 132 — A factory-captured proof is captured on a"
    " draft pull request, reviewed, replayed and published"
)


def _attribution() -> Any:
    """Import the attribution module, asserting it exists first.

    The `is_file()` assertion is what makes this a genuine failing assertion
    before the module is written, rather than a collection-time import error that
    proves only unimportability.
    """
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


@dataclass(kw_only=True)
class _ForgeRunner:
    """One seam answering both forge reads the pass performs, selected by argv."""

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


def _comments_json(*, run_id: str) -> str:
    body = textwrap.dedent(f"""\
        Proof of Done — verified — run {run_id} — 2026-10-01T09:00:00Z

        ## Assertion 1 — {_ASSERTION}

        Proof mode: `factory_captured`

        Reproduced: yes.
        """)
    return json.dumps({"comments": [{"url": _RECORD_URL, "body": body}]})


def _definition_of_done() -> str:
    return textwrap.dedent(f"""\
        ## Definition of Done

        - {_ASSERTION}

        {_REFERENCE_LINE}
        """)


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="Task",
        description=_definition_of_done(),
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
    )


def _outcome(*, fabro_run_id: str | None = _FABRO_RUN_ID) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="green",
        stage="done",
        pr_number=7,
        merge_sha="abc123",
        detail="merged",
        fabro_run_id=fabro_run_id,
    )


def _journal(*, tmp_path: Path, dispatches: tuple[tuple[str, str], ...]) -> Path:
    """Write a dispatch journal recording one `(dispatch_id, fabro_run_id)` per dispatch.

    The record SHAPES are the production ones — the `dispatch-id` stage record
    `_dispatcher_dispatch_id_journal` appends before launch, and the `fabro-run`
    stage record carrying the run id — so the readers under test are reading the
    file they read in production rather than a shape invented here.
    """
    path = tmp_path / "fabro-dispatch-journal.jsonl"
    lines: list[str] = []
    for dispatch_id, fabro_run_id in dispatches:
        lines.append(
            json.dumps(
                {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": dispatch_id}
            )
        )
        lines.append(
            json.dumps({"stage": "fabro-run", "work_item_id": _ITEM_ID, "run_id": fabro_run_id})
        )
    _ = path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_the_merging_dispatch_accepts_every_journaled_dispatch_of_the_item(
    tmp_path: Path,
) -> None:
    """Both identifiers of EVERY journaled dispatch are accepted, newest first.

    The two-dispatch fixture is what makes the claim observable: a reader that
    took only the newest dispatch would return two ids here and would still
    satisfy a single-dispatch fixture. The newest dispatch's own identifiers stay
    first and stay separately readable, because the pointer and the journal record
    name the dispatch now terminating.
    """
    attribution = _attribution()
    journal_path = _journal(
        tmp_path=tmp_path,
        dispatches=(
            (_EARLIER_DISPATCH_ID, _EARLIER_FABRO_RUN_ID),
            (_DISPATCH_ID, _FABRO_RUN_ID),
        ),
    )

    resolved = attribution.merging_dispatch(
        work_item_id=_ITEM_ID, fabro_run_id=None, journal_path=journal_path
    )

    assert resolved.dispatch_id == _DISPATCH_ID
    assert resolved.fabro_run_id == _FABRO_RUN_ID
    assert resolved.run_ids == (
        _FABRO_RUN_ID,
        _DISPATCH_ID,
        _EARLIER_FABRO_RUN_ID,
        _EARLIER_DISPATCH_ID,
    )
    # The outcome's OWN Fabro run id LEADS when the outcome carries one — that is
    # the dispatch path, where the run the outcome describes is the run now
    # terminating, and the journal's newest is only the reconcile path's fallback.
    # It no longer NARROWS the set: an earlier dispatch of this item may still be
    # the one that published the merged head.
    assert attribution.merging_dispatch(
        work_item_id=_ITEM_ID, fabro_run_id=_FABRO_RUN_ID, journal_path=journal_path
    ).run_ids == (
        _FABRO_RUN_ID,
        _DISPATCH_ID,
        _EARLIER_FABRO_RUN_ID,
        _EARLIER_DISPATCH_ID,
    )
    # An unidentifiable dispatch accepts NO record rather than the newest one.
    assert attribution.MergingDispatch(fabro_run_id=None, dispatch_id=None).run_ids == ()
    # One dispatch whose two identifiers happen to coincide is one accepted id,
    # not the same id twice.
    assert attribution.MergingDispatch(
        fabro_run_id=_DISPATCH_ID, dispatch_id=_DISPATCH_ID
    ).run_ids == (_DISPATCH_ID,)


def test_a_record_stamped_with_either_identifier_grades_the_assertion(tmp_path: Path) -> None:
    """The widening, in both directions, through the real leg reader."""
    attribution = _attribution()
    dispatch = attribution.MergingDispatch(fabro_run_id=_FABRO_RUN_ID, dispatch_id=_DISPATCH_ID)
    criteria = effective_criteria(item=_item())

    stamped_with_dispatch_id = read_proof_leg(
        repo=tmp_path,
        criteria=criteria,
        outcome=_outcome(),
        runner=_ForgeRunner(comments=_comments_json(run_id=_DISPATCH_ID)),
        dispatch=dispatch,
    )
    stamped_with_fabro_run_id = read_proof_leg(
        repo=tmp_path,
        criteria=criteria,
        outcome=_outcome(),
        runner=_ForgeRunner(comments=_comments_json(run_id=_FABRO_RUN_ID)),
        dispatch=dispatch,
    )

    for leg in (stamped_with_dispatch_id, stamped_with_fabro_run_id):
        assert leg.record is not None
        assert leg.unevidenced == ()
        assert [check.passed for check in leg.checks] == [True]
    assert stamped_with_dispatch_id.record is not None
    assert stamped_with_dispatch_id.record.run_id == _DISPATCH_ID
    assert stamped_with_fabro_run_id.record is not None
    assert stamped_with_fabro_run_id.record.run_id == _FABRO_RUN_ID
    # The reason names every identifier the pass accepted, so an operator reading
    # a refusal can see which dispatch the pass was asking about.
    assert stamped_with_dispatch_id.reason == (
        f"pull request #7 records read for run {_FABRO_RUN_ID} or {_DISPATCH_ID}"
    )


def test_a_record_outside_the_accepted_identifier_set_is_unobserved(
    tmp_path: Path,
) -> None:
    """The control for the widening: a record outside the accepted set is refused.

    The accepted set here is handed in rather than resolved, so what it excludes
    is exactly what the test states — this is the record reader's own refusal, at
    the one seam where the set is a given. Both identifier KINDS are tried,
    because a build that narrowed on only one of them would report a refusal for
    the other and look correct from one fixture.
    """
    attribution = _attribution()
    dispatch = attribution.MergingDispatch(fabro_run_id=_FABRO_RUN_ID, dispatch_id=_DISPATCH_ID)
    criteria = effective_criteria(item=_item())

    for stale in (_EARLIER_DISPATCH_ID, _EARLIER_FABRO_RUN_ID):
        leg = read_proof_leg(
            repo=tmp_path,
            criteria=criteria,
            outcome=_outcome(),
            runner=_ForgeRunner(comments=_comments_json(run_id=stale)),
            dispatch=dispatch,
        )

        # The records WERE read; none of them is attributable to this merge.
        assert leg.records != ()
        assert leg.record is None
        assert leg.unevidenced == (_ASSERTION,)
        assert leg.absent_evidence == (f"{PROOF_RECORD_EVIDENCE_LEG} for {_ASSERTION!r}",)


def test_the_pass_resolves_the_merging_dispatch_from_the_journal_it_is_given(
    tmp_path: Path,
) -> None:
    """End to end: the pass PASSES on a dispatch-id-stamped record, and says why not.

    The no-journal control is the degraded leg every non-production caller takes:
    with no journal there is no dispatch id to recover, the accepted set reduces
    to the outcome's own Fabro run id, and the same record is unevidenced. It is
    asserted here so the default is a measured behaviour rather than an
    assumption.
    """
    _ = _attribution()
    journal_path = _journal(tmp_path=tmp_path, dispatches=((_DISPATCH_ID, _FABRO_RUN_ID),))

    with_journal = run_acceptance_pass(
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(),
        runner=_ForgeRunner(comments=_comments_json(run_id=_DISPATCH_ID)),
        journal_path=journal_path,
    )
    without_journal = run_acceptance_pass(
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(),
        runner=_ForgeRunner(comments=_comments_json(run_id=_DISPATCH_ID)),
    )

    assert with_journal.verdict == "PASS"
    assert with_journal.absent_evidence == ()
    assert without_journal.verdict == "NEEDS_ATTENTION"
    assert without_journal.absent_evidence == (f"{PROOF_RECORD_EVIDENCE_LEG} for {_ASSERTION!r}",)


def test_the_record_of_the_dispatch_that_published_the_merged_head_is_attributed(
    tmp_path: Path,
) -> None:
    """A later dispatch of the same item does not unattribute the publishing one.

    The incident shape end to end (`bd-ib-qm4luz`, 2026-10-05): the dispatch that
    published the merged head captured and verified its record there and then
    died, a LATER dispatch of the same item was journaled, and `reconcile-merged`
    re-ran the pass from an outcome carrying no Fabro run id of its own. Both
    identifier KINDS of the publishing dispatch are tried, because a build that
    widened on only one would look correct from one fixture.
    """
    _ = _attribution()
    journal_path = _journal(
        tmp_path=tmp_path,
        dispatches=(
            (_EARLIER_DISPATCH_ID, _EARLIER_FABRO_RUN_ID),
            (_DISPATCH_ID, _FABRO_RUN_ID),
        ),
    )

    for stamped in (_EARLIER_DISPATCH_ID, _EARLIER_FABRO_RUN_ID):
        result = run_acceptance_pass(
            repo=tmp_path,
            item=_item(),
            outcome=_outcome(fabro_run_id=None),
            runner=_ForgeRunner(comments=_comments_json(run_id=stamped)),
            journal_path=journal_path,
        )

        assert result.verdict == "PASS"
        assert result.absent_evidence == ()
        assert result.proof is not None
        assert result.proof.record is not None
        assert result.proof.record.run_id == stamped
        assert [check.passed for check in result.proof.checks] == [True]


def test_a_record_from_no_journaled_dispatch_of_the_item_is_still_unobserved(
    tmp_path: Path,
) -> None:
    """The widening's boundary is the journal, not "whatever verified record exists".

    The control for the test above, and the one it needs: that record is verified,
    is the only one on the pull request, and is therefore also the newest, so a
    build that had widened to "any verified record" would attribute it and pass.
    Its run identifier belongs to no dispatch this item was ever journaled under,
    so the pass must leave the proof leg unobserved — and the parking record must
    SAY so, since that rendered line is what an operator reads.
    """
    _ = _attribution()
    journal_path = _journal(tmp_path=tmp_path, dispatches=((_DISPATCH_ID, _FABRO_RUN_ID),))

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(fabro_run_id=None),
        runner=_ForgeRunner(comments=_comments_json(run_id=_UNJOURNALED_RUN_ID)),
        journal_path=journal_path,
    )
    record = parking_record(item_id=_ITEM_ID, policy="ai-only", result=result, pull_request=7)

    assert result.verdict == "NEEDS_ATTENTION"
    assert result.proof is not None
    assert result.proof.records != ()
    assert result.proof.record is None
    assert result.absent_evidence == (f"{PROOF_RECORD_EVIDENCE_LEG} for {_ASSERTION!r}",)
    assert [leg.render() for leg in record.legs if leg.name == PROOF_RECORD_EVIDENCE_LEG] == [
        f"- {PROOF_RECORD_EVIDENCE_LEG}: NOT OBSERVED — {result.proof.reason}"
    ]


def test_the_pass_recovers_the_identifiers_when_the_outcome_carries_none(
    tmp_path: Path,
) -> None:
    """The `reconcile-merged` shape: an outcome with no Fabro run id still attributes.

    This is the case the dispatch path cannot exercise, and the one the repair
    exists for: the reconcile valve builds its own outcome from a resolved merged
    pull request, so `fabro_run_id` is None and the journal is the only source of
    either identifier.
    """
    _ = _attribution()
    journal_path = _journal(tmp_path=tmp_path, dispatches=((_DISPATCH_ID, _FABRO_RUN_ID),))

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(fabro_run_id=None),
        runner=_ForgeRunner(comments=_comments_json(run_id=_DISPATCH_ID)),
        journal_path=journal_path,
    )
    # The control: the SAME outcome against a journal that never names this item,
    # which is the only other thing a missing run id could mean.
    unknown_item = run_acceptance_pass(
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(fabro_run_id=None),
        runner=_ForgeRunner(comments=_comments_json(run_id=_DISPATCH_ID)),
        journal_path=tmp_path / "absent-journal.jsonl",
    )

    assert result.verdict == "PASS"
    assert unknown_item.verdict == "NEEDS_ATTENTION"
    assert unknown_item.proof is not None
    assert unknown_item.proof.reason == "merging run id unavailable"
