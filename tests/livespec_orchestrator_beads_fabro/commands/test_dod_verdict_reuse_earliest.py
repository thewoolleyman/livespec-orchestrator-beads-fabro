"""Reuse selects the EARLIEST record matching the current digests.

`SPECIFICATION/scenarios.md` Scenario 240 states the selection rule outright —
"Reuse selects the earliest record among those matching the current digests" —
and its worked example is a timeline carrying subject digest A, then B, then A
again: judged while the current digest is B the reuse takes B, and once the
subject is RESTORED to A it must take the FIRST A record, not the later one.

WHY THE EARLIEST AND NOT THE NEWEST, which is the reading an implementation
falls into. The clause's purpose is that "the first verdict on a Definition of
Done stands until its text or rubric changes", so a subject that is edited and
then restored must come back to the verdict it already had rather than to
whichever re-judgement happened in between. A newest-first reader is also
wrong in a second, quieter way: it stops at the newest record, so a timeline
whose newest verdict was taken on some OTHER subject reports that NOTHING is
reusable — and the item is re-judged on every pass, which is the model call the
whole rule exists to avoid.

THE TWO MATCHING RECORDS CARRY DIFFERENT FINDINGS, which is the only thing that
makes the selection observable: two records agreeing on their outcome are
indistinguishable at every surface, so a reader taking the later one would pass
a test that only read the verdict.

THE THREE INVALIDATORS ARE ASSERTED BESIDE IT, because "reuses the earliest
match" is worthless if everything matches. A rider appended after filing, a
ratified specification change and a changed `dod_gate` prompt each move one of
the two digests, and each must leave the recorded verdict unreusable.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    JUDGEMENT_HELD,
    DodJudgement,
    judgement_subject_digest,
    rubric_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_ADMISSION,
    STAGE_PRE_DISPATCH,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from types import ModuleType

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record"
_RUBRIC = "# the gate prompt's bytes\n"
_OTHER_RUBRIC = "# a released build's different gate prompt\n"
_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64
_FIRST_FINDING = "bd-ib-m76p2n: the first verdict named this remedy."
_LATER_FINDING = "bd-ib-m76p2n: a later verdict named a different remedy."
_HEADING = "## Scenario 174 — The judgement runs before admission"


def _record(*, digest: str, finding: str, outcome: str = JUDGEMENT_HELD) -> str:
    return verdict_comment(
        item_id="bd-ib-m76p2n",
        stage=STAGE_PRE_ADMISSION,
        digest=digest,
        rubric_digest=rubric_digest(rubric=_RUBRIC),
        judgement=DodJudgement(outcome=outcome, findings=(finding,)),
    )


def _reusable(*, comments: tuple[str, ...], digest: str) -> object:
    module: ModuleType = importlib.import_module(_MODULE)
    return module.reusable_verdict(
        comments=comments, digest=digest, rubric_digest=rubric_digest(rubric=_RUBRIC)
    )


def test_a_restored_subject_reuses_the_first_record_carrying_its_digest() -> None:
    """Scenario 240's worked example: A, then B, then A again, judged at A."""
    timeline = (
        _record(digest=_DIGEST_A, finding=_FIRST_FINDING),
        _record(digest=_DIGEST_B, finding="a verdict on another subject"),
        _record(digest=_DIGEST_A, finding=_LATER_FINDING),
    )

    reused = _reusable(comments=timeline, digest=_DIGEST_A)

    assert reused is not None
    assert reused.findings == (_FIRST_FINDING,)


def test_the_same_timeline_judged_at_the_other_digest_reuses_that_record() -> None:
    """The control: the selection follows the CURRENT digest, not a position."""
    timeline = (
        _record(digest=_DIGEST_A, finding=_FIRST_FINDING),
        _record(digest=_DIGEST_B, finding="a verdict on another subject"),
        _record(digest=_DIGEST_A, finding=_LATER_FINDING),
    )

    reused = _reusable(comments=timeline, digest=_DIGEST_B)

    assert reused is not None
    assert reused.findings == ("a verdict on another subject",)


def test_a_matching_record_behind_a_newer_unmatched_one_is_still_reused() -> None:
    """A newest-first reader reports nothing reusable and re-judges every pass."""
    timeline = (
        _record(digest=_DIGEST_A, finding=_FIRST_FINDING),
        _record(digest=_DIGEST_B, finding="a verdict on another subject"),
    )

    reused = _reusable(comments=timeline, digest=_DIGEST_A)

    assert reused is not None
    assert reused.findings == (_FIRST_FINDING,)


def test_a_legacy_record_naming_no_digest_is_passed_over_rather_than_ending_the_scan() -> None:
    """Such a record supports no comparison, so it can neither match nor block.

    Ending the scan on it is the fail-CLOSED reading of a newest-first walk and
    is wrong oldest-first: it would make one pre-digest record permanently
    retire every verdict recorded after it.
    """
    legacy = "livespec-dod-judgement\n\nwork-item: bd-ib-m76p2n\noutcome: admitted\n"
    timeline = (legacy, _record(digest=_DIGEST_A, finding=_FIRST_FINDING))

    reused = _reusable(comments=timeline, digest=_DIGEST_A)

    assert reused is not None
    assert reused.findings == (_FIRST_FINDING,)


def test_no_record_matching_the_current_digests_is_reused() -> None:
    """The control for every case above: an unmatched timeline reuses nothing."""
    timeline = (_record(digest=_DIGEST_B, finding="a verdict on another subject"),)

    assert _reusable(comments=timeline, digest=_DIGEST_A) is None


def _item(*, description: str | None = None) -> WorkItem:
    return WorkItem(
        id="bd-ib-m76p2n",
        type="feature",
        status="ready",
        title="A judged slice",
        description=(
            f"## Definition of Done\n\n- The slice lands its change.\n\nReferences: {_HEADING}\n"
            if description is None
            else description
        ),
        origin="freeform",
        gap_id=None,
        rank="b0f",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-23T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nBody.\n", encoding="utf-8"
    )
    return repo


def test_the_three_invalidators_each_leave_the_recorded_verdict_unreusable(
    tmp_path: Path,
) -> None:
    """A rider, a ratified spec change and a changed rubric, one at a time.

    Each is asserted against the SAME baseline digest pair, so the three are
    three readings of one rule rather than three unrelated facts; and the
    baseline itself is asserted reusable first, without which a build whose
    digests never matched anything would satisfy all three.
    """
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    digest = judgement_subject_digest(item=item, cwd=repo)
    record = verdict_comment(
        item_id=item.id,
        stage=STAGE_PRE_DISPATCH,
        digest=digest,
        rubric_digest=rubric_digest(rubric=_RUBRIC),
        judgement=DodJudgement(outcome=JUDGEMENT_ADMITTED),
    )
    module: ModuleType = importlib.import_module(_MODULE)

    def reusable(*, comments: tuple[str, ...], subject: str, rubric: str) -> object:
        return module.reusable_verdict(
            comments=comments, digest=subject, rubric_digest=rubric_digest(rubric=rubric)
        )

    assert reusable(comments=(record,), subject=digest, rubric=_RUBRIC) is not None

    rider = "EVIDENCE: narrow the assertion to the admission wall."
    with_rider = judgement_subject_digest(item=item, cwd=repo, comments=(rider,))

    assert reusable(comments=(record, rider), subject=with_rider, rubric=_RUBRIC) is None

    _ = (repo / "SPECIFICATION" / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nBody.\n\n## Scenario 999 — A later ratification\n\nNew.\n",
        encoding="utf-8",
    )
    after_ratification = judgement_subject_digest(item=item, cwd=repo)

    assert after_ratification != digest
    assert reusable(comments=(record,), subject=after_ratification, rubric=_RUBRIC) is None
    assert reusable(comments=(record,), subject=digest, rubric=_OTHER_RUBRIC) is None
