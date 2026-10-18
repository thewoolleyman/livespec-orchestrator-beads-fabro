"""The HOST half of the per-assertion proof grade: what a dispatch projects.

Separate from `test_dispatcher_proof_grade_program.py`, which grades the program
BYTES, because these are claims about what the Dispatcher hands the sandbox: the
assertion set, its absences, and the two paths the node and the prepare step must
resolve identically. A projection asserted beside the program would read as a
property of the grade; it is a property of the dispatch.
"""

from __future__ import annotations

import base64
import json
from dataclasses import replace

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_grade_program import (
    PROOF_GRADE_ASSERTIONS_ENV_VAR,
    PROOF_GRADE_PROGRAM_FILENAME,
    PROOF_GRADE_READER_DIRECTORY,
    PROOF_GRADE_READER_MODULES,
    factory_captured_assertions,
    proof_grade_assertions_env_lines,
    proof_grade_program_path_expansion,
    proof_grade_program_prepare_steps_block,
    proof_record_reader_sources,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_MIXED_DEFINITION_OF_DONE = """## Definition of Done

- alpha holds.
- beta holds.

### Host-captured

Reason: it needs the released build on an operator host.

- gamma holds on the released build.

### Human-attested

Reason: it is a values call.

- delta reads well.
"""

# Enough bullets that the base64 payload clears the declared bound, which is the
# only shape the no-truncation arm can be reached through. Sized off the bound
# rather than off a round number, so the case keeps failing for the right reason
# if the bound ever moves.
_ENORMOUS_ASSERTION_COUNT = 1500


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-grade",
        type="task",
        status="ready",
        title="A graded task",
        description=_MIXED_DEFINITION_OF_DONE,
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-17T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _projected(*, lines: str) -> list[str]:
    """The assertion list the env line carries, decoded as the sandbox decodes it."""
    assert lines.startswith(f"{PROOF_GRADE_ASSERTIONS_ENV_VAR} = ")
    payload = json.loads(lines.split(" = ", 1)[1].strip())
    assert isinstance(payload, str)
    decoded = json.loads(base64.b64decode(payload.encode("ascii")).decode("utf-8"))
    assert isinstance(decoded, list)
    return [one for one in decoded if isinstance(one, str)]


def test_only_the_factory_captured_assertions_are_projected() -> None:
    """The grade's question is the factory leg's, in Definition of Done order.

    The fixture is deliberately MIXED, because an item declaring only factory
    assertions would make a projection that ignored the modes altogether read
    exactly like a correct one. The host and human assertions must be absent:
    each is owed by a different party on a different surface, and a grade
    demanding a verdict for either would refuse every mixed item's record.
    """
    item = _item()

    assert factory_captured_assertions(item=item) == ("alpha holds.", "beta holds.")
    assert _projected(lines=proof_grade_assertions_env_lines(item=item)) == [
        "alpha holds.",
        "beta holds.",
    ]


def test_a_caller_holding_no_work_item_projects_nothing() -> None:
    """A direct caller renders exactly the overlay it rendered before.

    The grade reads the absence as an UNESTABLISHED question and fails closed on
    it, which is why rendering an empty list here would be the dangerous reading:
    an empty set of assertions advances every record.
    """
    assert proof_grade_assertions_env_lines(item=None) == ""


def test_a_payload_over_its_bound_projects_nothing_rather_than_a_truncation() -> None:
    """A truncated assertion set is a question about something else.

    The bound exists because the encoded payload rides an `execve` argument, and
    the honest response to overflowing it is to project NOTHING: a truncated list
    would be a well-formed projection of a DIFFERENT question, and the grade would
    then advance a record on whichever assertions happened to fit.
    """
    bullets = "\n".join(
        f"- assertion {index} holds for this item." for index in range(_ENORMOUS_ASSERTION_COUNT)
    )
    item = _item(description=f"## Definition of Done\n\n{bullets}\n")

    assert len(factory_captured_assertions(item=item)) == _ENORMOUS_ASSERTION_COUNT
    assert proof_grade_assertions_env_lines(item=item) == ""


def test_the_node_and_the_prepare_step_resolve_one_root() -> None:
    """A node resolving a different root than the prepare pass finds no program.

    Both halves are asserted — the program's own path AND the reader directory it
    imports from — because a step that wrote the reader somewhere the program does
    not look fails at the import line, in a stage whose refusal then names the
    grade rather than the preparation.
    """
    expansion = proof_grade_program_path_expansion()
    block = proof_grade_program_prepare_steps_block().replace("\\", "")

    assert expansion == f"{sandbox_plugins_root_expansion()}/{PROOF_GRADE_PROGRAM_FILENAME}"
    assert expansion in block
    assert f"{sandbox_plugins_root_expansion()}/{PROOF_GRADE_READER_DIRECTORY}" in block
    assert "[[run.prepare.steps]]" in block


def test_the_reader_travels_as_the_packages_own_bytes_with_no_package_import_left() -> None:
    """The shipped sources ARE the reader, minus the one qualifier a sandbox lacks.

    Each source is asserted PRESENT IN THE STEP whole, rather than by a needle,
    because the claim is that nothing but the package prefix changed — a fragment
    that happened to carry the same function names would satisfy any containment
    check on a needle. The prefix's ABSENCE is asserted too, since a source still
    naming the package would raise `ModuleNotFoundError` inside the sandbox, and
    each heredoc delimiter is asserted QUOTED, since an unquoted one would have
    the shell substitute into a source whose regular expressions carry `$` and
    backticks.
    """
    sources = proof_record_reader_sources()
    block = proof_grade_program_prepare_steps_block()

    assert [name for name, _ in sources] == list(PROOF_GRADE_READER_MODULES)
    for index, (name, source) in enumerate(sources):
        assert "livespec_orchestrator_beads_fabro" not in source, name
        assert source.strip() != "", name
        assert f"<<'LIVESPEC_PROOF_RECORD_READER_{index}'" in json.loads(
            block.split("script = ", 1)[1]
        )
        assert source in json.loads(block.split("script = ", 1)[1]), name
