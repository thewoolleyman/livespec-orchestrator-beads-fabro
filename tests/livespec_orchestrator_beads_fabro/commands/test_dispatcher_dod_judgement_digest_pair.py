"""The DIGEST PAIR, as the three surfaces that key on it actually read it.

`contracts.md`'s one-rubric-one-subject clause keys verdict reuse on two
digests — the subject's and the rubric's — and three surfaces read that pair:
the subject itself, which must not move when a receipt is recorded; the
pre-dispatch judgement, which reuses on a match and judges again on a
difference; and drain candidate enumeration, which excludes a refused item only
while both still match.

EVERY CASE HERE IS PAIRED WITH ITS OWN CONTROL, because each claim is about
something that must NOT happen and is therefore satisfied by a build that does
nothing at all. "The digest did not move" is satisfied by a digest that never
moves; "no second comment was appended" by a gate that appends none; "the item
left the enumeration" by a filter that drops every row. So each case asserts the
negative BESIDE the positive that differs in exactly one input.

THE RUBRIC IS VARIED BY HANDING THE GATE A DIFFERENT PAYLOAD ROOT, which is what
a plugin release is from the gate's point of view: the rubric is read from the
build that will execute the dispatch, so two payload roots carrying different
`dod-gate.md` bytes are two releases. Nothing here edits the shipped file.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    judge_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_ADMISSION,
    STAGE_PRE_DISPATCH,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    judgement_rubric,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_wall import (
    dod_unrefused_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    unjudged_governing_heading,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_HEADING = "## Effective acceptance criteria"
_HELD_REPLY = (
    '{"outcome": "failed", "failure_reason":'
    ' "bd-ib-pair: the References line omits the governing scenario; add that heading."}'
)
_PASS_REPLY = '{"outcome": "passed"}'
_FINDING = "bd-ib-pair: the References line omits the governing scenario; add that heading."
_RIDER = "EVIDENCE: the preflight and the in-run gate disagreed on these same bytes."
# A rubric digest no build could produce, which is what a verdict taken under an
# EARLIER release looks like from here.
_FOREIGN_RUBRIC_DIGEST = "0" * 64


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass
class _Runner:
    """A CommandRunner double counting how many judgements were actually taken."""

    result: CommandResult
    calls: int = 0
    prompts: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
        start_new_session: bool = False,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin, start_new_session)
        self.prompts.append(argv[argv.index("-p") + 1])
        self.calls += 1
        return self.result


class _Ledger:
    """The comment sidecar as the gate sees it: a read and an append."""

    def __init__(self) -> None:
        self.bodies: list[str] = []

    def append(self, *, body: str) -> None:
        self.bodies.append(body)


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-pair",
        type="feature",
        status="ready",
        title="A released slice",
        description=(
            "## Definition of Done\n"
            "\n"
            "- The dispatched slice lands its change.\n"
            "\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-22T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _spec_tree(*, repo: Path) -> Path:
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nThe criteria clause.\n", encoding="utf-8"
    )
    return repo


def _connected_repo(*, tmp_path: Path, name: str = "connected") -> Path:
    repo = _spec_tree(repo=tmp_path / name)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


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


def _payload(*, tmp_path: Path, name: str, rubric: str) -> Path:
    """One plugin build's payload root, carrying the rubric bytes it ships."""
    root = tmp_path / name
    prompts = root / ".fabro" / "workflows" / "implement-work-item" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    _ = (prompts / "dod-gate.md").write_text(rubric, encoding="utf-8")
    return root


def _executing_rubric_digest() -> str:
    """The digest of the rubric the wall's own surfaces resolve.

    Taken off the shipped file, because `dod_unrefused_candidates` reads the
    EXECUTING build: a digest of this module's own invention would be one the
    filter correctly refuses to reuse, and the exclusion case would then pass
    for the wrong reason.
    """
    rubric = judgement_rubric()
    assert rubric is not None
    return rubric_digest(rubric=rubric)


def _stand_a_refusal(
    *, repo: Path, item: WorkItem, rubric: str, subject: str | None = None
) -> None:
    """Record a refusing verdict against this item under the named digests."""
    config = _config(repo=repo)
    append_work_item(path=config, item=item)
    append_work_item_comment(
        path=config,
        work_item_id=item.id,
        body=verdict_comment(
            item_id=item.id,
            stage=STAGE_PRE_DISPATCH,
            digest=judgement_subject_digest(item=item, cwd=repo) if subject is None else subject,
            rubric_digest=rubric,
            judgement=DodJudgement(outcome=JUDGEMENT_HELD, findings=(_FINDING,)),
        ),
    )


def test_recording_a_verdict_leaves_the_subject_it_would_next_be_graded_by_unchanged(
    tmp_path: Path,
) -> None:
    """A receipt is not brief, so appending one cannot move the digest.

    If it could, no later taking would ever reuse the verdict just recorded:
    every pass would pay a model call and append one more receipt, and the
    subject would grow without bound. The CONTROL is an operator RIDER appended
    the same way, which MUST move the digest — without it, "the digest held" is
    satisfied by a digest that ignores every comment, and the judge would then
    never read the prose an operator appends to correct the section.
    """
    repo = _connected_repo(tmp_path=tmp_path)
    item = _item()
    before = judgement_subject_digest(item=item, cwd=repo, comments=(_RIDER,))
    record = verdict_comment(
        item_id=item.id,
        stage=STAGE_PRE_ADMISSION,
        digest=before,
        rubric_digest=_executing_rubric_digest(),
        judgement=DodJudgement(outcome=JUDGEMENT_HELD, findings=(_FINDING,)),
    )

    after = judgement_subject_digest(item=item, cwd=repo, comments=(_RIDER, record))

    assert after == before
    assert (
        judgement_subject_digest(item=item, cwd=repo, comments=(_RIDER, "a second rider")) != before
    )


def test_a_dispatch_reuses_a_verdict_whose_two_digests_both_match_and_appends_nothing(
    tmp_path: Path,
) -> None:
    """Both caps at once: no second judgement, and no second comment."""
    repo = _connected_repo(tmp_path=tmp_path)
    payload = _payload(tmp_path=tmp_path, name="build-one", rubric="# gate one\n")
    ledger = _Ledger()
    runner = _Runner(result=CommandResult(exit_code=0, stdout=_HELD_REPLY, stderr=""))

    first = judge_definition_of_done(
        item=_item(),
        repo=repo,
        stage=STAGE_PRE_DISPATCH,
        comments=tuple(ledger.bodies),
        append=ledger.append,
        runner=runner,
        payload_root=payload,
        governing_heading=unjudged_governing_heading,
    )
    second = judge_definition_of_done(
        item=_item(),
        repo=repo,
        stage=STAGE_PRE_DISPATCH,
        comments=tuple(ledger.bodies),
        append=ledger.append,
        runner=runner,
        payload_root=payload,
        governing_heading=unjudged_governing_heading,
    )

    assert first.reused is False
    assert second.reused is True
    assert second.outcome == first.outcome
    assert runner.calls == 1
    assert len(ledger.bodies) == 1


def test_a_dispatch_under_a_different_rubric_judges_again_and_appends_one_record(
    tmp_path: Path,
) -> None:
    """A release that changes the rubric retires the verdict taken under the old.

    The item is UNTOUCHED between the two takings, so its subject digest is
    identical and the rubric is the only thing that differs. Its control is the
    case above, which reuses on the same subject under the same rubric: without
    that pair, "the judgement ran again" is satisfied by a gate that never reuses
    anything.
    """
    repo = _connected_repo(tmp_path=tmp_path)
    ledger = _Ledger()
    runner = _Runner(result=CommandResult(exit_code=0, stdout=_PASS_REPLY, stderr=""))

    _ = judge_definition_of_done(
        item=_item(),
        repo=repo,
        stage=STAGE_PRE_DISPATCH,
        comments=tuple(ledger.bodies),
        append=ledger.append,
        runner=runner,
        payload_root=_payload(tmp_path=tmp_path, name="build-one", rubric="# gate one\n"),
        governing_heading=unjudged_governing_heading,
    )
    under_new_rubric = judge_definition_of_done(
        item=_item(),
        repo=repo,
        stage=STAGE_PRE_DISPATCH,
        comments=tuple(ledger.bodies),
        append=ledger.append,
        runner=runner,
        payload_root=_payload(tmp_path=tmp_path, name="build-two", rubric="# gate two\n"),
        governing_heading=unjudged_governing_heading,
    )

    assert under_new_rubric.reused is False
    assert runner.calls == 2
    # ONE new record, not two: the cap on a reused verdict is about the spend,
    # and a judgement that genuinely ran owes exactly one receipt.
    assert len(ledger.bodies) == 2


def test_a_drain_excludes_a_refused_item_only_while_both_digests_still_match(
    tmp_path: Path,
) -> None:
    """The exclusion is keyed on the pair, and either difference re-admits the row.

    Three legs over three repositories, because the fake tenant is a
    process singleton and each leg stands its own verdict. The first is the
    positive — both digests match, so the refused row leaves the enumeration —
    and it is what makes the other two able to fail: without it, "the row came
    back" is satisfied by a filter that drops nothing at all.
    """
    matching = _connected_repo(tmp_path=tmp_path, name="matching")
    item = _item()
    _stand_a_refusal(repo=matching, item=item, rubric=_executing_rubric_digest())

    assert dod_unrefused_candidates(items=[item], repo=matching) == []

    reset_fake_singleton()
    other_rubric = _connected_repo(tmp_path=tmp_path, name="other-rubric")
    _stand_a_refusal(repo=other_rubric, item=item, rubric=_FOREIGN_RUBRIC_DIGEST)

    assert dod_unrefused_candidates(items=[item], repo=other_rubric) == [item]

    reset_fake_singleton()
    other_subject = _connected_repo(tmp_path=tmp_path, name="other-subject")
    _stand_a_refusal(
        repo=other_subject,
        item=item,
        rubric=_executing_rubric_digest(),
        subject="f" * 64,
    )

    assert dod_unrefused_candidates(items=[item], repo=other_subject) == [item]
