"""The repository preflight composes its prompt through the PACKAGE, not its own.

`contracts.md`'s one-rubric-one-subject clause names the repository preflight as
a host taking, so it grades the same rubric over the same subject as the
Dispatcher's own pre-dispatch judgement and appends only the ending contract.
The preflight's prompt is therefore not something it assembles: it is
`judgement_prompt(gate_prompt=judgement_rubric(...), subject=judgement_subject(...))`,
the exact composition the Dispatcher uses.

WHY THIS IS A CONTENT TEST AND WHAT IT CAN AND CANNOT SHOW. The script resolves
its rubric from the operator host's Claude Code plugin install registry and reads
the live ledger tenant through a credential wrapper, neither of which a sandbox
has — so the end-to-end behaviour is a host-captured proof and is owed on a host.
What a sandbox CAN establish is the property that makes that proof possible: the
committed script delegates the composition rather than restating it, and carries
no grading prose of its own. A second composition is the defect: measured four
times on this repository's own items between 2026-10-22 00:21Z and 08:13Z, a
preflight PASS was followed by an in-run refusal on unchanged Definition-of-Done
bytes, and the preflight's own appended paragraphs are prose the node never reads.

THE ABSENCE ASSERTIONS NAME A STATED SCOPE: the committed bytes of
`dev-tooling/dod-preflight.sh`, and each forbidden string is one the script
ACTUALLY CARRIED before this change, copied from it rather than reconstructed —
an invented needle would be absent from any version of the file and the check
would report a clean negative whatever the script said.
"""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path("dev-tooling/dod-preflight.sh")

# The three package names the composition is delegated to. Each one is a
# different half of the claim: the rubric's bytes, the subject's text, and the
# ONE assembly of the two with the ending contract between them.
_DELEGATED = (
    "judgement_rubric",
    "judgement_subject",
    "judgement_prompt",
)

# Prose the script appended to the judge's prompt before this change, copied
# verbatim out of the pre-change file. Every one of them is guidance about HOW to
# grade, which the clause requires to live in the rubric so the node grades by it
# too.
_RETIRED_GRADING_PROSE = (
    "use the committed mirror",
    "For check 5, name the SURFACE",
    "Read files only.",
    "End with the JSON failure line on any finding",
    "the single word PASS alone on the last line",
)


def _script() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def test_the_preflight_delegates_its_whole_prompt_to_the_package() -> None:
    text = _script()

    assert [name for name in _DELEGATED if name not in text] == []


def test_the_preflight_appends_no_grading_prose_of_its_own() -> None:
    text = _script()

    assert [needle for needle in _RETIRED_GRADING_PROSE if needle in text] == []


def test_the_preflight_builds_no_goal_preamble_of_its_own() -> None:
    # The subject is what a host taking grades, and the package renders it. The
    # script used to assemble a `Goal:` preamble out of the item's title,
    # description and comments — a second rendering of the subject, which is the
    # same defect as a second rubric one level over.
    text = _script()

    assert "Goal: %s" not in text
    assert "Ledger comments (operator riders appended after filing" not in text
