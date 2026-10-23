"""Tests for taking the spec-stated judgement behind the governing-heading verdict.

The impure half of the component. Every case drives `governing_heading_verdict`
itself over a real spec tree on disk with only the `ModelRunner` stood in, so
the condensation, the citation resolution and the shared parser are production
code: a reader that answered from a hand-built verdict would pass each
assertion while saying nothing about the path a host taking takes.

THE THREE ABSENCES ARE THE SUBJECT. A judgement that could not be taken must
answer `None` and never raise, because the three surfaces that consult it sit
on the dispatch path, the intake path and the approve valve — and an exception
there is a bug-class escape from a surface whose whole job is to render an
actionable refusal. Each absence is reached through a DIFFERENT failure: an
item with no section, a spec tree that is not there, and a response the shared
parser refuses.

THE POSITIVE CASE IS WHAT MAKES THEM EVIDENCE. Without a verdict this reader
genuinely returns, a reader answering `None` unconditionally satisfies every
absence in the module.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    governing_heading_verdict,
    host_governing_heading_reader,
    unjudged_governing_heading,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_GOVERNING = "## Scenario 206 — The spec-change tier is decided by the spec-stated judgement"
_CITED = "## Scenario 141 — The referenced scenario governs the proof"

_VERDICT_REPLY = (
    '{"kind": "stated", "stated_by": ["' + _GOVERNING + '"],'
    ' "generalization_target": null, "rationale": "The scenario states it."}'
)


def _item(*, description: str | None = None) -> WorkItem:
    return WorkItem(
        id="bd-ib-m76p2n",
        type="feature",
        status="ready",
        title="The citation checks consult the spec-stated judgement",
        description=(
            "## Definition of Done\n\n- The checks consult the judgement.\n\n"
            f"References: {_CITED}\n"
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
    """A repository whose governed tree carries both headings and nothing else."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_GOVERNING}\n\nIt states the behaviour.\n\n{_CITED}\n\nOther text.\n",
        encoding="utf-8",
    )
    return repo


class _Runner:
    """A `CommandRunner` double standing in for the headless judge."""

    def __init__(self, *, stdout: str, exit_code: int = 0) -> None:
        self.stdout = stdout
        self.exit_code = exit_code
        self.calls = 0

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
        _ = (argv, cwd, timeout_seconds, env, stdin, start_new_session)
        self.calls += 1
        return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr="")


def test_a_readable_verdict_carries_the_governing_headings_the_judgement_named(
    tmp_path: Path,
) -> None:
    verdict = governing_heading_verdict(
        item=_item(), repo=_repo(tmp_path=tmp_path), run_model=lambda _prompt: _VERDICT_REPLY
    )

    assert verdict is not None
    assert verdict.kind == "stated"
    assert verdict.stated_by == (_GOVERNING,)
    assert verdict.generalization_target is None


def test_an_item_with_no_definition_of_done_section_is_never_judged(tmp_path: Path) -> None:
    """No assertion to ask about, so no model call is spent asking.

    Read off the runner's own call count rather than off the verdict alone: a
    reader that asked and then discarded the answer returns the same `None`,
    and the claim is about the spend.
    """
    runner = _Runner(stdout=_VERDICT_REPLY)

    verdict = host_governing_heading_reader(runner=runner)(
        item=_item(description="Prose with no section at all.\n"),
        repo=_repo(tmp_path=tmp_path),
    )

    assert verdict is None
    assert runner.calls == 0


def test_a_judge_whose_invocation_raises_answers_no_verdict_rather_than_unwinding(
    tmp_path: Path,
) -> None:
    """The binding writes the prompt to a file, so the call can fail at the host.

    An `OSError` escaping here would unwind through the pre-dispatch wall, the
    intake router and the approve valve — every one of them a surface whose job
    is to render an actionable refusal.
    """

    def _raising(_prompt: str) -> str:
        raise OSError("no space left on device")

    assert (
        governing_heading_verdict(item=_item(), repo=_repo(tmp_path=tmp_path), run_model=_raising)
        is None
    )


def test_a_spec_file_that_is_not_utf8_answers_no_verdict_rather_than_raising(
    tmp_path: Path,
) -> None:
    """The read failure that is NOT an `OSError`, and is the one that bites.

    The spec reader opens every file with `read_text(encoding="utf-8")`, so one
    invalid byte raises `UnicodeDecodeError` — a `ValueError` subclass. A catch
    naming only `OSError` lets it escape through the pre-dispatch wall, the
    intake router and the approve valve as a traceback, which is the shape the
    sibling repositories' own registry read was repaired for.

    The runner is counted as well, because this arm must return BEFORE the
    judge is reached: a reading taken against a tree that could not be read
    would cite headings nobody can open.
    """
    repo = _repo(tmp_path=tmp_path)
    _ = (repo / "SPECIFICATION" / "scenarios.md").write_bytes(b"## Scenario 1 \xff\xfe\n")
    runner = _Runner(stdout=_VERDICT_REPLY)

    verdict = host_governing_heading_reader(runner=runner)(item=_item(), repo=repo)

    assert verdict is None
    assert runner.calls == 0


def test_an_absent_spec_tree_answers_no_verdict_through_the_shared_refusal(
    tmp_path: Path,
) -> None:
    """An absent tree raises nothing, so it is refused one step down, not here.

    `rglob` on a missing directory yields nothing rather than failing, so the
    tree reads as EMPTY and the shared parser refuses the verdict for citing a
    heading that tree does not carry. The case is kept apart from the one above
    because the two reach the same answer by different arms, and collapsing
    them would let a build with no read-failure arm at all pass both.
    """
    verdict = governing_heading_verdict(
        item=_item(), repo=tmp_path / "absent", run_model=lambda _prompt: _VERDICT_REPLY
    )

    assert verdict is None


def test_a_response_the_shared_parser_refuses_answers_no_verdict(tmp_path: Path) -> None:
    """A judge that answered, unreadably, is a failure to measure like any other."""
    verdict = governing_heading_verdict(
        item=_item(), repo=_repo(tmp_path=tmp_path), run_model=lambda _prompt: "not a verdict"
    )

    assert verdict is None


def test_the_default_reader_takes_no_judgement_and_returns_nothing(tmp_path: Path) -> None:
    assert unjudged_governing_heading(item=_item(), repo=_repo(tmp_path=tmp_path)) is None


def test_the_host_reader_puts_the_prompt_to_the_injected_runner(tmp_path: Path) -> None:
    """The binding is exercised end to end, so the model seam is really reached."""
    runner = _Runner(stdout=_VERDICT_REPLY)

    verdict = host_governing_heading_reader(runner=runner)(
        item=_item(), repo=_repo(tmp_path=tmp_path)
    )

    assert runner.calls == 1
    assert verdict is not None
    assert verdict.stated_by == (_GOVERNING,)
