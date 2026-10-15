"""The two record lines a changed-head refresh's carry-forward decision reads.

`SPECIFICATION/contracts.md` section "Definition-of-Done and Proof-of-Done
stages" -> "The observation scope" (v138) puts TWO obligations on the record
every proof stage publishes, and both are obligations on PROSE the stage writes
by hand. The verified record "MUST state, ahead of its numbered steps, the line
`Working directory: .`", and `proof_capture` and `proof_verify` "MUST write that
line into their record exactly when every one of its steps ran from the
repository root"; and when `proof_verify` "executes a working-tree read, it MUST
record, for each of that command's path operands, one *read identity* line
`Read: <canonical path> <identity>`" whose identity is "the output of `git
hash-object --no-filters <path>` for the working-tree file it read, taken in the
same execution".

WHY A PROMPT TEST AND NOT A CODE TEST. Neither line is rendered by any Python
caller: both stages hand-format their record and post it with `gh pr comment`,
exactly as the size-budget discipline beside this module records. The code that
READS them is the carry-forward decision, and a reader whose writer never writes
the line answers `reproof_required` for every record forever -- a silent,
permanent retirement of the carry-forward route that no decision-side test can
see, because from the decision's side the absent line is a correct observation.

WHY THE SPELLINGS ARE IMPORTED RATHER THAN TYPED. The decision parses these two
lines literally. A prompt that instructs `Working dir: .`, or `Read <path>`
without the colon, reads to a human as the same instruction and to the decision
as no line at all. Every needle below therefore comes from the module that owns
the spelling, so re-wording one without re-wording the other fails here.

PROMPT PROSE IS HARD-WRAPPED, so every needle is chosen to sit WITHIN one
physical line, for the reason the size-budget module records: a needle
straddling a line break fails silently while the prose says exactly the thing.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS_DIR = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "prompts"
)
_GRAMMAR_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_carry_forward_grammar.py"
)
_GRAMMAR_MODULE_NAME = (
    "livespec_orchestrator_beads_fabro.commands._dispatcher_carry_forward_grammar"
)

_CAPTURE_PROMPT = _PROMPTS_DIR / "proof-capture.md"
_VERIFY_PROMPT = _PROMPTS_DIR / "proof-verify.md"

# The condition the clause attaches to the working-directory line, quoted so a
# prompt that states the line unconditionally -- which would make it a lie for
# any record whose steps ran elsewhere -- fails here.
_ROOT_CONDITION = "exactly when every one of its steps ran from the repository root"

# The command whose output the read identity must be. Spelled with its
# `--no-filters` flag because a plain `git hash-object` hashes the file through
# the repository's filters, which is a DIFFERENT value from the raw bytes the
# decision re-reads at the new head -- so the flagless form would make every
# comparison fail while looking correct.
_IDENTITY_COMMAND = "git hash-object --no-filters"


def _grammar_module() -> object:
    """The module that owns the two spellings, loaded from its own path."""
    assert _GRAMMAR_MODULE_PATH.is_file(), (
        "the direct-read grammar module owning the record-line spellings is absent at "
        f"{_GRAMMAR_MODULE_PATH}, so neither prompt can be held to the line the "
        "carry-forward decision parses"
    )
    return importlib.import_module(_GRAMMAR_MODULE_NAME)


def test_the_grammar_module_owns_both_record_line_spellings() -> None:
    """One module spells the two lines, so prompt and decision cannot drift."""
    module = _grammar_module()
    assert module.WORKING_DIRECTORY_LINE == "Working directory: ."
    assert module.READ_IDENTITY_LABEL == "Read"


@pytest.mark.parametrize("prompt", [_CAPTURE_PROMPT, _VERIFY_PROMPT])
def test_each_proof_stage_prompt_states_the_working_directory_line(prompt: Path) -> None:
    """Both stages write the line, and both state the condition on writing it."""
    module = _grammar_module()
    text = prompt.read_text(encoding="utf-8")
    assert module.WORKING_DIRECTORY_LINE in text, (
        f"{prompt.name} never spells the working-directory line the carry-forward "
        "decision parses, so every record it publishes puts every step outside the "
        "direct-read grammar"
    )
    assert _ROOT_CONDITION in text, (
        f"{prompt.name} states the working-directory line without the condition the "
        "clause attaches to it, so a record whose steps ran elsewhere would declare "
        "the repository root anyway"
    )


def test_the_verify_prompt_states_the_read_identity_line() -> None:
    """`proof_verify` records the raw identity of every working-tree file it read."""
    module = _grammar_module()
    text = _VERIFY_PROMPT.read_text(encoding="utf-8")
    label = module.READ_IDENTITY_LABEL
    assert f"{label}: <canonical path> <identity>" in text, (
        "proof-verify.md never spells the read identity line, so the carry-forward "
        "decision has nothing to compare the new head's working-tree bytes against "
        "and every refresh re-proves"
    )
    assert _IDENTITY_COMMAND in text, (
        "proof-verify.md names no raw-bytes identity command, so the identity it "
        "records may be the filtered hash rather than the bytes the step read"
    )
