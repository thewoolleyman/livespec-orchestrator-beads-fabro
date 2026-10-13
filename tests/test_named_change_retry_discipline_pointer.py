"""`AGENTS.md`'s pointer at the fleet named-change retry discipline, graded as prose.

Each test here grades ONE assertion of `bd-ib-t4dtx4`'s Definition of Done against the
`## Decision authority — when to ask, proceed, or self-resolve` section of `AGENTS.md`.
The rule itself lives in the livespec repository's `agent-disciplines.md`; what this
repository owes is a POINTER that states the rule and cites that section by its exact
heading, so an agent reading only this file still learns the discipline and knows where
the authority lives.

Two deliberate shapes in the helpers below, each guarding a way a presence-only check
would pass a file that does not deliver:

1. The bullet is sliced out of its OWN section, not searched for across the whole file.
   A bullet carrying this text anywhere else in `AGENTS.md` would satisfy a bare `in`
   check while leaving the Definition of Done's named section without it.
2. The sliced bullet is whitespace-normalized before any phrase assertion. `AGENTS.md`
   is hard-wrapped, so every multi-word phrase this grades spans a line break and an
   indent; asserting against the raw text would make the tests fail on a re-wrap that
   changed nothing, and would tempt a future editor to pack lines to satisfy them.

On the citation's spelling: the pointer names the livespec file as `agent-disciplines.md`
plus its `.ai/` tree, rather than as one `.ai/agent-disciplines.md` token. That token is
what `check-agents-ai-references-resolve` reads as a reference to a file in THIS
repository's `.ai/` tree, which has no such file — the check resolves every concrete
`.ai/<topic>.md` reference relative to the `AGENTS.md` that makes it. The split spelling
is this repository's established form for a CROSS-REPO citation (the "Stop the line for
breakages" paragraph cites the same livespec file the same way), and it is the honest
one: a cross-repo citation is not the local progressive-disclosure pointer that check
exists to keep resolvable.
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AGENT_INSTRUCTIONS = (_REPO_ROOT / "AGENTS.md").read_text()

_SECTION_HEADING = "## Decision authority — when to ask, proceed, or self-resolve"
_BULLET_LEAD = "- **Never re-attempt a failed dispatch without naming what changed.**"
_DISCIPLINE_HEADING = "Never re-attempt a failed dispatch without naming what changed"


def _decision_authority_section() -> str:
    """The named section's body, from its heading to the next `## ` heading."""
    start = _AGENT_INSTRUCTIONS.find(_SECTION_HEADING)
    assert start != -1, f"AGENTS.md carries no section {_SECTION_HEADING!r}"
    body = _AGENT_INSTRUCTIONS[start + len(_SECTION_HEADING) :]
    end = body.find("\n## ")
    return body if end == -1 else body[:end]


def _retry_discipline_bullet() -> str:
    """The pointer bullet, whitespace-normalized, sliced from its own section.

    The slice runs to the next top-level `- ` bullet (or the section's end), so a
    phrase living in a NEIGHBOURING bullet cannot satisfy an assertion about this one.
    """
    section = _decision_authority_section()
    start = section.find(_BULLET_LEAD)
    assert start != -1, f"section {_SECTION_HEADING!r} carries no bullet leading {_BULLET_LEAD!r}"
    rest = section[start + len(_BULLET_LEAD) :]
    end = rest.find("\n- ")
    bullet = _BULLET_LEAD + (rest if end == -1 else rest[:end])
    return re.sub(r"\s+", " ", bullet).strip()


def test_pointer_requires_naming_in_one_sentence_what_changed() -> None:
    bullet = _retry_discipline_bullet()

    # The obligation itself: one sentence, naming the difference, before any retry.
    assert "Before any retry" in bullet
    assert "in ONE sentence" in bullet
    assert "the specific difference that addresses the recorded failure" in bullet

    # What counts as a named difference. Asserted as three separate terms rather than
    # one fragment, so a pointer keeping only part of the list cannot pass.
    assert "a code change in the failing check you can point to" in bullet
    assert "a changed item text" in bullet
    assert "a recovered external condition" in bullet

    # And the rest state when no difference can be named — without this, the rule
    # reads as a pause rather than as a stop, and a retry still follows the thinking.
    assert "stop and report it as a defect rather than retrying" in bullet


def test_pointer_states_a_newer_build_is_not_a_reason_and_drift_is_ambient() -> None:
    bullet = _retry_discipline_bullet()

    # A newer registered build existing is not, by itself, a reason to re-dispatch.
    assert "A newer registered build EXISTING is not a reason to re-dispatch" in bullet

    # Why: drift is permanent here, so the warning is ambient rather than a diagnosis.
    # Both halves are graded, because the "ambient" claim without the permanence that
    # makes it true reads as an opinion a reader may discount.
    assert "build drift is permanent in this continuous-deployment fleet" in bullet
    assert "the build-drift warning is ambient information, not a diagnosis" in bullet

    # The work the agent owes INSTEAD of switching builds — the diff that would turn
    # "a newer build exists" into a named difference, if there is one.
    assert "diff that code across builds before launching anything" in bullet


def test_pointer_cites_the_livespec_discipline_by_its_exact_heading() -> None:
    bullet = _retry_discipline_bullet()

    # The owning repository and file, named so a reader can find it from here.
    assert "livespec" in bullet
    assert "`agent-disciplines.md`" in bullet
    assert "`.ai/`" in bullet

    # The section, by its exact heading, in this repository's established
    # section-sign-plus-quoted-heading citation form (spelled in the literal below
    # rather than in this comment, which may not carry that marker).
    assert f'§"{_DISCIPLINE_HEADING}"' in bullet
