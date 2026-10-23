"""A refused item re-enters the drain and is judged ONCE on the way back.

Work-item `bd-ib-m76p2n`'s last assertion: "A refused item excluded from drain
candidates re-enters enumeration and is judged once after the subject digest or
the rubric digest it would now be graded by differs from the refusing verdict's."

THE "ONCE" IS THE PART NOTHING ELSE BINDS. The re-entry itself is already
covered — `test_dispatcher_dod_judgement_digest_pair.py` drives the filter over
a changed subject and a changed rubric — but a filter that re-admits the row and
a wall that then judges it on EVERY pass produce the same enumeration, pass after
pass, while spending a model call per pass on an item nothing about has changed.
That is the spend the reuse rule exists to avoid, and it is invisible at the
surface the re-entry cases read.

SO EVERY CASE COUNTS THE JUDGE EXECUTABLE. It is stood in at the executable
rather than at a seam, as in both Scenario 174 modules, so the argv, the prompt
read and the exit-code mapping are exercised; and one script answers both
takings of a judgement, told apart by their own argv — the spec-stated component
puts its prompt on standard input and its argv ends `-p --model <model>`, while
the rubric judgement passes the prompt as the argument after `-p`.

ONE TAKING IS TWO INVOCATIONS, and the number is named rather than written as a
literal for that reason: the component and the rubric are two headless calls
through one resolver, so a bare 2 beside a bare 0 reads as an arbitrary pair
rather than as "the judgement was taken exactly once".

THE EXCLUDED PASS IS THE CONTROL. Without a pass in which the row is dropped and
NOTHING is spent, "judged once on re-entry" is equally consistent with a build
whose filter never excluded anything.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_HELD,
    DodJudgement,
    judgement_subject_digest,
    rubric_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_ADMISSION,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    judgement_rubric,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_wall import (
    dod_judgement_refusal,
    dod_unrefused_candidates,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-m76p2n"
_HEADING = "## Scenario 174 — The judgement runs before admission"
_REFUSAL = "bd-ib-m76p2n: the References line omits the governing scenario; add that heading."
_RIDER = "EVIDENCE: narrow the assertion to the admission wall."

# One taking of the judgement is TWO invocations of the judge executable: the
# spec-stated judgement the governing-heading verdict comes from, and the
# rubric judgement itself. Named rather than spelled, because its meaning is
# "the judgement was taken exactly once".
_ONE_TAKING = 2

_SPEC_STATED_REPLY = (
    '{\\"kind\\": \\"stated\\", \\"stated_by\\": [\\"' + _HEADING + '\\"],'
    ' \\"generalization_target\\": null, \\"rationale\\": \\"It states it.\\"}'
)
_PASS_REPLY = '{\\"outcome\\": \\"passed\\"}'


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nThe slice's behaviour is stated here.\n", encoding="utf-8"
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="feature",
        status="ready",
        title="A judged slice",
        description=(
            "## Definition of Done\n\n- The dispatched slice lands its change.\n\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
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


class _Judge:
    """A real judge executable that records every invocation it receives."""

    def __init__(self, *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._ledger = tmp_path / "judge-calls"
        script = tmp_path / "fake-judge"
        _ = script.write_text(
            "#!/bin/sh\n"
            f"echo call >> {self._ledger}\n"
            'if [ "$2" = "--model" ]; then\n'
            f'  printf "%s\\n" "{_SPEC_STATED_REPLY}"\n'
            "else\n"
            f'  printf "%s\\n" "{_PASS_REPLY}"\n'
            "fi\n",
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))

    @property
    def calls(self) -> int:
        if not self._ledger.is_file():
            return 0
        return len(self._ledger.read_text(encoding="utf-8").splitlines())


def _stand_a_refusal(*, repo: Path) -> None:
    """A refusing verdict recorded against the item's CURRENT digest pair.

    The rubric digest is the EXECUTING build's own, because the surfaces under
    test resolve the shipped `dod-gate.md` rather than a fixture's — a verdict
    recorded under any other rubric is correctly unreusable, and would make
    every case here pass for the wrong reason.
    """
    config = _config(repo=repo)
    item = _item()
    append_work_item(path=config, item=item)
    rubric = judgement_rubric()
    assert rubric is not None
    append_work_item_comment(
        path=config,
        work_item_id=_ITEM_ID,
        body=verdict_comment(
            item_id=_ITEM_ID,
            stage=STAGE_PRE_ADMISSION,
            digest=judgement_subject_digest(item=item, cwd=repo),
            rubric_digest=rubric_digest(rubric=rubric),
            judgement=DodJudgement(outcome=JUDGEMENT_HELD, findings=(_REFUSAL,)),
        ),
    )


def test_a_refused_item_is_dropped_from_the_enumeration_and_costs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: a pass that drops the row spends no judgement at all."""
    repo = _repo(tmp_path=tmp_path)
    judge = _Judge(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stand_a_refusal(repo=repo)

    assert dod_unrefused_candidates(items=[_item()], repo=repo) == []
    assert judge.calls == 0


def test_the_row_re_enters_once_its_subject_digest_differs_and_is_judged_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-entry AND the spend: one taking on the way back, none on the next pass."""
    repo = _repo(tmp_path=tmp_path)
    judge = _Judge(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stand_a_refusal(repo=repo)
    append_work_item_comment(path=_config(repo=repo), work_item_id=_ITEM_ID, body=_RIDER)

    assert dod_unrefused_candidates(items=[_item()], repo=repo) == [_item()]
    assert judge.calls == 0

    assert dod_judgement_refusal(repo=repo, items=[_item()]) is None
    assert judge.calls == _ONE_TAKING

    assert dod_judgement_refusal(repo=repo, items=[_item()]) is None
    assert judge.calls == _ONE_TAKING


def test_an_unchanged_row_is_never_judged_however_many_passes_reach_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mirror control: the exclusion holds, and holds without spending."""
    repo = _repo(tmp_path=tmp_path)
    judge = _Judge(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stand_a_refusal(repo=repo)

    for _pass in range(3):
        assert dod_unrefused_candidates(items=[_item()], repo=repo) == []

    assert judge.calls == 0
