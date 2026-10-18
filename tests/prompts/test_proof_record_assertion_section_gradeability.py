"""The per-assertion gradeability discipline every record-publishing prompt carries.

`bd-ib-kcq6pu`, review-fix round: the `proof_grade` node asks the shipped reader
whether each assertion reads as reproduced. It CANNOT ask whether the reader
resolved that assertion to the right section — and two authoring shapes make the
reader answer about the wrong one, both FAIL-OPEN, so the grade passes and the
record is still ungradeable by the post-merge acceptance pass afterwards.

The two shapes, each measured against the shipped reader by the control below:

1. A payload carrying a three-backtick line inside a three-backtick fence. The
   reader closes a fence only on the same character with a run AT LEAST AS LONG,
   so the inner line closes the outer fence early and every line after it is read
   as record PROSE — a heading the proof merely PRINTED opens a section, and a
   `Reproduced:` line the proof printed becomes an authored verdict.
2. An assertion section carrying ANOTHER assertion's text. `_assertion_section`
   takes the FIRST section whose text contains the needle, and that search is NOT
   fence-aware, so a quoted Definition of Done absorbs every later assertion into
   the section the quotation sits in.

WHY THESE ARE PROMPT TESTS. Neither shape is reachable from the `proof_grade`
node: the record is already posted by the time it runs, and the record contract
forbids editing a posted record. The only venue is AUTHORING time, so the prose
is the deliverable — and prose with no test drifts, which is how the instruction
that already asked for a per-assertion verdict was deviated from on the incident
that filed this item.

WHY THE PROMPT SET IS DERIVED FROM CONTENT RATHER THAN LISTED, and why a control
asserts the derivation reached the publishers known today: identical reasoning to
`test_proof_record_size_budget_discipline`, whose derivation this reuses. A
literal pair of filenames is blind to a third publisher added later, and a scan
that silently matched nothing would report a clean pass over an empty set.

PROMPT PROSE IS HARD-WRAPPED, so every needle here is chosen to sit WITHIN one
physical line. A needle straddling a line break can only fail silently while the
prose says exactly the thing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import ProofRecord

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS_DIR = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "prompts"
)

# What makes a prompt a RECORD PUBLISHER — the same two marks the size-budget
# module derives on, for the same reason: either alone is too loose.
_RECORD_TITLE = "Proof of Done —"
_POST_CALL = "gh pr comment"

_KNOWN_PUBLISHERS = ("proof-capture.md", "proof-verify.md")

_SECTION_HEADING = "### Keep every assertion section gradeable on its own"


def _publisher_prompts() -> tuple[str, ...]:
    """Every prompt file that instructs an agent to publish a Proof of Done record."""
    return tuple(
        sorted(
            one.name
            for one in _PROMPTS_DIR.glob("*.md")
            if _RECORD_TITLE in one.read_text(encoding="utf-8")
            and _POST_CALL in one.read_text(encoding="utf-8")
        )
    )


def _text(*, name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _section(*, name: str) -> str:
    """The gradeability section's own text, from its heading to the next `### `.

    Scoped to the SECTION rather than the whole file for the reason
    `test_proof_capture_git_history_anchoring` scopes to a bullet: both prompts
    already discuss fences and verbatim assertion text elsewhere, so a whole-file
    probe would pass over a section that said nothing.
    """
    text = _text(name=name)
    start = text.index(_SECTION_HEADING)
    rest = text[start + len(_SECTION_HEADING) :]
    end = rest.find("\n### ")
    return rest if end == -1 else rest[:end]


def test_the_derivation_reaches_every_known_record_publisher() -> None:
    """The control: the content scan found the publishers, so an empty scan cannot pass."""
    derived = _publisher_prompts()

    assert set(_KNOWN_PUBLISHERS) <= set(derived)
    assert _PROMPTS_DIR.is_dir()


@pytest.mark.parametrize("name", _KNOWN_PUBLISHERS)
def test_the_prompt_carries_the_gradeability_section(*, name: str) -> None:
    """Every publisher carries the section, and each section is non-empty.

    The scoping helper below indexes on the heading, so without this a prompt that
    lost the section would raise rather than report, and a prompt that kept only
    the heading would satisfy every needle test vacuously.
    """
    assert _SECTION_HEADING in _text(name=name)
    assert len(_section(name=name)) > 500


@pytest.mark.parametrize("name", _KNOWN_PUBLISHERS)
def test_the_prompt_states_how_the_reader_resolves_an_assertion(*, name: str) -> None:
    """First match on the narrowest section — the rule both faults exploit.

    Stated positively, because an agent that does not know the resolution rule
    cannot tell either prohibition below from arbitrary formatting etiquette.
    """
    section = _section(name=name)

    assert "NARROWEST heading-rooted section" in section
    assert "FIRST MATCH" in section
    assert "fail-OPEN" in section


@pytest.mark.parametrize("name", _KNOWN_PUBLISHERS)
def test_the_prompt_requires_a_longer_delimiter_around_a_nested_fence(*, name: str) -> None:
    """The remedy is a LONGER run, and the prompt says why a same-length one fails.

    The rule and its mechanism are asserted together: "use four backticks" alone
    reads as a style preference and does not generalise to a payload that already
    carries four.
    """
    section = _section(name=name)

    assert "LONGER delimiter" in section
    assert "AT LEAST AS LONG" in section
    assert "strictly longer one" in section


@pytest.mark.parametrize("name", _KNOWN_PUBLISHERS)
def test_the_prompt_forbids_another_assertions_text_in_a_section(*, name: str) -> None:
    """Including inside proof payloads, which is the half a prose-only rule misses.

    The fenced half is the load-bearing one: fencing is what makes every OTHER
    hazard in a record inert, so an agent that fenced its quotation would
    reasonably believe it had complied.
    """
    section = _section(name=name)

    assert "ANOTHER assertion's text" in section
    assert "Definition of Done quoted as a block" in section
    assert "reads fenced lines as well" in section


@pytest.mark.parametrize("name", _KNOWN_PUBLISHERS)
def test_the_prompt_prescribes_attachment_rather_than_truncation(*, name: str) -> None:
    """The one remedy that always works, and the two wrong ones ruled out by name.

    Truncating is already forbidden by the size-budget section for a different
    reason, and this section would otherwise read as licensing it.
    """
    section = _section(name=name)

    assert "do NOT truncate" in section
    assert "ATTACH that proof instead" in section
    assert "carry no assertion text" in section


# ---------------------------------------------------------------------------
# The controls. Each asserts that the shipped reader ACTUALLY behaves the way the
# prose above claims — so a prompt rule cannot outlive the reader that motivated
# it, and a reader change that retired either fault fails here rather than leaving
# two prompts instructing agents against a hazard that no longer exists.
# ---------------------------------------------------------------------------

_ALPHA = "Alpha holds."
_BETA = "Beta holds."


def _record(*, body: str) -> ProofRecord:
    return ProofRecord(verdict="verified", run_id="R", timestamp="T", url="", body=body)


def _two_assertion_body(*, first_section_payload: tuple[str, ...]) -> str:
    return "\n".join(
        (
            "Proof of Done — verified — run R — T",
            "",
            f"## Assertion 1 — {_ALPHA}",
            "",
            *first_section_payload,
            "",
            "Reproduced: yes.",
            "",
            f"## Assertion 2 — {_BETA}",
            "",
            "Reproduced: no.",
        )
    )


def test_the_positive_control_grades_a_well_formed_record_per_assertion() -> None:
    """The instrument is aimed correctly: distinct verdicts on a record with neither fault.

    Without this, every control below is consistent with a reader that answers the
    same way for any input at all.
    """
    record = _record(body=_two_assertion_body(first_section_payload=()))

    assert record.reproduced(assertion=_ALPHA) is True
    assert record.reproduced(assertion=_BETA) is False


def test_a_same_length_nested_fence_makes_the_record_ungradeable() -> None:
    """The first fault, measured: fence tracking inverts and both verdicts are lost."""
    body = _two_assertion_body(
        first_section_payload=("```python", "text = '''", "```", "'''", "```")
    )
    record = _record(body=body)

    assert record.reproduced(assertion=_ALPHA) is None
    assert record.reproduced(assertion=_BETA) is None


def test_a_longer_delimiter_keeps_the_same_payload_gradeable() -> None:
    """The prescribed remedy, measured against the same payload the fault used.

    This is what makes the prohibition actionable rather than merely true: the
    identical proof bytes grade correctly once the delimiter outruns them.
    """
    body = _two_assertion_body(
        first_section_payload=("````python", "text = '''", "```", "'''", "````")
    )
    record = _record(body=body)

    assert record.reproduced(assertion=_ALPHA) is True
    assert record.reproduced(assertion=_BETA) is False


def test_a_quoted_sibling_assertion_absorbs_that_assertion_fail_open() -> None:
    """The second fault, measured in PROSE: Assertion 2 reads Assertion 1's verdict."""
    body = _two_assertion_body(
        first_section_payload=(f"The Definition of Done reads: {_ALPHA} {_BETA}",)
    )
    record = _record(body=body)

    assert record.reproduced(assertion=_BETA) is True


def test_a_quoted_sibling_assertion_absorbs_it_from_inside_a_fence_too() -> None:
    """The half a prose-only rule misses: the needle search is NOT fence-aware.

    The absorbed verdict here is `yes` while the record's own Assertion 2 section
    says `no` — the fail-open direction, and invisible at the forge, which renders
    both sections exactly as written.
    """
    body = _two_assertion_body(
        first_section_payload=("```", "$ cat definition-of-done.txt", _ALPHA, _BETA, "```")
    )
    record = _record(body=body)

    assert record.reproduced(assertion=_BETA) is True
