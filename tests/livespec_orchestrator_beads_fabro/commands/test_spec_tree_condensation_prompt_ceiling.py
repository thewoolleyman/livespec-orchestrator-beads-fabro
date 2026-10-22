"""One work-item's judgement fits the judging model's input ceiling.

Assertion 1 of `bd-ib-a2bfp3`: "A spec-stated judgement for one work-item
against this repository's spec tree sends the judging model a prompt under
1,048,576 characters."

MEASURED AT THE `run_model` SEAM, not over a condensation's own return value.
The prompt is rendered INSIDE `livespec_runtime.spec_stated.judge`, by a
renderer this repository vendors and does not own, so a test asserting on the
size of the tree handed to that renderer would be asserting about an input and
not about the bytes the model is sent — and the two differ by a framing this
repository cannot change. The injected `run_model` is the one place those bytes
exist, so it is where they are counted.

THE CONTROL IS THE SAME MEASUREMENT THROUGH THE UNREDUCED TREE, and it must
EXCEED the ceiling. Without it the assertion passes for any repository whose
spec tree happens to be small — which is every repository but this one — and a
check that cannot return the other answer is not evidence of anything, which is
the instrument-aim trap `AGENTS.md` catalogues.
Measured 2026-10-22 against this repository's live tree: 1354623 characters
unreduced, against a Codex refusal at 1048576.

THE STATEMENT IS A WORK-ITEM'S OWN INTENT, rendered through the production
`intent_statement`, because the assertion is about a judgement "for one
work-item": the statement is part of the prompt, so a short synthetic string
would measure a prompt no scan ever sends.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._ledger_intent_scan import intent_statement
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification
from livespec_orchestrator_beads_fabro.types import WorkItem
from livespec_runtime.spec_stated import judge
from returns.pipeline import is_successful

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC_ROOT = _REPO_ROOT / "SPECIFICATION"
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_spec_tree_condensation.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._spec_tree_condensation"

# The measured Codex refusal, quoted from the failure the work-item records:
# `Input exceeds the maximum length of 1048576 characters (input_too_large,
# actual_chars 1360329)`.
_CODEX_INPUT_CEILING = 1_048_576

_UNSTATED_REPLY = (
    '{"kind": "unstated", "stated_by": [], '
    '"generalization_target": null, "rationale": "not stated"}'
)

_ITEM = WorkItem(
    id="bd-ib-a2bfp3",
    title="The spec-stated judgement renders the whole spec tree into every prompt",
    description=(
        "`livespec_runtime.spec_stated.judge` renders the WHOLE current spec tree "
        "into every judgement prompt, so a judgement against this repository is "
        "1.36M characters and a Codex judge refuses it."
    ),
    acceptance_criteria="- A judgement sends the judging model a prompt under the ceiling.",
    type="bug",
    status="active",
    origin="freeform",
    gap_id=None,
    rank="a0",
    assignee=None,
    depends_on=(),
    captured_at="2026-10-22T00:00:00Z",
    resolution=None,
    reason=None,
    audit=None,
    superseded_by=None,
    spec_commitment_hint=None,
)


@dataclass(kw_only=True)
class _Recorder:
    """A `ModelRunner` that keeps every prompt it is handed.

    `__call__` rather than a closure because the shared `ModelRunner` alias is
    POSITIONAL by contract, and a dunder is the one shape this repository's
    keyword-only rule exempts.
    """

    reply: str = _UNSTATED_REPLY
    prompts: list[str] = field(default_factory=list)

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply


def test_one_work_items_judgement_fits_the_judging_models_input_ceiling() -> None:
    """The condensed judgement is under the ceiling the unreduced one exceeds."""
    assert _MODULE_PATH.is_file(), (
        f"{_MODULE_PATH} does not exist, so no condensation stands between this "
        "repository's spec tree and the judging model's input ceiling"
    )
    condensation = importlib.import_module(_MODULE_NAME)
    spec_tree = read_current_specification(spec_root=_SPEC_ROOT).files
    statement = intent_statement(item=_ITEM)

    control = _Recorder()
    _ = judge(spec_tree=spec_tree, statement=statement, run_model=control)
    assert len(control.prompts[0]) > _CODEX_INPUT_CEILING, (
        "the unreduced judgement no longer exceeds the ceiling, so this "
        "measurement can no longer tell a working condensation from an absent one"
    )

    recorder = _Recorder()
    verdict = condensation.judge_within_ceiling(
        spec_tree=spec_tree, statement=statement, run_model=recorder
    )

    assert len(recorder.prompts) == 1
    assert len(recorder.prompts[0]) < _CODEX_INPUT_CEILING
    assert is_successful(verdict)
