"""The size-budget discipline every record-publishing stage prompt must carry.

`bd-ib-555xcd`: a Proof of Done record is ONE forge comment, and a record the forge
REJECTS is a LOST proof that reads downstream as an ABSENT one. The two posting
PRIMITIVES (`post-host-record`, `post-plan-record`) enforce the budget in code,
because a Python caller renders through them. The two factory STAGES do not: they
hand-format their record and post it with `gh pr comment`, so for them the budget
is a prompt instruction, and this module is what stops that instruction from
drifting away from the number the code enforces.

WHY THE NUMBERS ARE IMPORTED RATHER THAN SPELLED. A prompt stating a budget the
code does not enforce is worse than a prompt stating none: the stage would bound
its record to one number while every other publisher bounds to another, and the
disagreement would surface as a rejected comment — the exact failure the budget
exists to prevent. So every figure asserted below comes from
`_dispatcher_proof_budget`, and changing a constant without re-wording the prompts
fails here rather than in production.

WHY THE PROMPT SET IS DERIVED FROM CONTENT RATHER THAN LISTED. A literal pair of
filenames is blind to a third record-publishing stage added later, and would report
a clean pass for a prompt nothing ever read. The set is therefore every prompt that
instructs an agent to publish a Proof of Done record, recognised by the two things
such a prompt must both carry — the record's own first-line title and the forge
call that posts it. The control below asserts the derivation reached the two
publishers known today, so a scan that silently matched nothing, or matched only
one, fails instead of certifying what it never read.

PROMPT PROSE IS HARD-WRAPPED, so every needle here is chosen to sit WITHIN one
physical line. A needle straddling a line break can only fail silently while the
prose says exactly the thing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_budget import (
    FORGE_COMMENT_CEILING_BYTES,
    INLINE_PROOF_ALLOWANCE_BYTES,
    PROOF_RECORD_BUDGET_BYTES,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS_DIR = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "prompts"
)

# What makes a prompt a RECORD PUBLISHER: it names the record's ratified first-line
# title AND the forge call that posts one. Either alone is too loose — the review
# prompt discusses records without publishing one, and several prompts call `gh`.
_RECORD_TITLE = "Proof of Done —"
_POST_CALL = "gh pr comment"

# The publishers known today. Asserted as a SUBSET of the derived set rather than
# as its definition, so a later third publisher widens the set instead of failing.
_KNOWN_PUBLISHERS = ("proof-capture.md", "proof-verify.md")


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


def test_the_derivation_reaches_every_known_record_publisher() -> None:
    """The control: the content scan found the publishers, so an empty scan cannot pass.

    Without this, every per-prompt assertion below is vacuous for any prompt the
    derivation missed — and a derivation that matched NOTHING would report a clean
    pass over an empty set, which is the catalogued shape of an instrument that
    cannot return a hit.
    """
    derived = _publisher_prompts()

    assert set(_KNOWN_PUBLISHERS) <= set(derived)
    assert _PROMPTS_DIR.is_dir()


@pytest.mark.parametrize("name", _KNOWN_PUBLISHERS)
def test_the_prompt_states_the_three_declared_budget_figures(*, name: str) -> None:
    """Ceiling, budget and per-assertion inline allowance, as the CODE declares them."""
    text = _text(name=name)

    assert str(FORGE_COMMENT_CEILING_BYTES) in text
    assert str(PROOF_RECORD_BUDGET_BYTES) in text
    assert str(INLINE_PROOF_ALLOWANCE_BYTES) in text


@pytest.mark.parametrize("name", _KNOWN_PUBLISHERS)
def test_the_prompt_measures_in_bytes_and_says_so(*, name: str) -> None:
    """`wc -c`, not `wc -m`.

    The byte denomination is the arm most easily lost, because on ASCII proof the
    two agree and nothing looks wrong. The discriminating measurement was 131072 em
    dashes: half the character ceiling, but 393216 bytes, and refused.
    """
    text = _text(name=name)

    assert "wc -c" in text
    assert "UTF-8 BYTES" in text
    # The prompt must name the wrong instrument to warn against it, so its presence
    # is required rather than forbidden — and it must not be the one prescribed.
    assert "`wc -m` counts characters" in text


@pytest.mark.parametrize("name", _KNOWN_PUBLISHERS)
def test_the_prompt_refuses_to_post_over_budget_before_posting(*, name: str) -> None:
    """The refusal is BEFORE the post, which is the whole of its value.

    A record comment must not be edited after posting, so a check that ran after the
    forge call would be measuring a record it could no longer withhold.
    """
    text = _text(name=name)

    assert f"more than **{PROOF_RECORD_BUDGET_BYTES}** bytes" in text
    assert "BEFORE YOU POST IT" in text
    assert "no longer withhold" in text


@pytest.mark.parametrize("name", _KNOWN_PUBLISHERS)
def test_the_prompt_states_the_forge_message_is_not_the_ceiling(*, name: str) -> None:
    """The 65536 figure is what the forge SAYS, and it is wrong in number and unit.

    Asserted because this is the number a later editor will "correct" the prompt
    back to: it arrives stamped with the forge's own authority, in the very message
    a publisher sees when a post is refused.
    """
    text = _text(name=name)

    assert "maximum is 65536 characters" in text
    assert "wrong in BOTH its number and its unit" in text
    assert "005-forge-comment-ceiling-measurement-2026-10-07.md" in text


@pytest.mark.parametrize("name", _KNOWN_PUBLISHERS)
def test_the_prompt_forbids_truncating_a_proof_to_fit(*, name: str) -> None:
    """Attaching is the remedy; truncation and dropping the assertion are not.

    Both wrong remedies are silent at the surface: a truncated proof still renders
    as a proof, and a dropped assertion reads as one nobody captured — so the prompt
    has to rule them out by name rather than merely prefer the attachment.
    """
    text = _text(name=name)

    assert "truncate" in text
    assert "proof of something else" in text
