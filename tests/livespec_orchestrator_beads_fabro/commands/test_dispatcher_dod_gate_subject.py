"""The `dod_gate` node's judgement subject, delivered to that node alone.

WHAT THE DEFECT WAS. From v0.310.0 the dispatch goal appended the whole
Definition-of-Done judgement subject, and Fabro injects the goal into EVERY ACP
node, so each request of each node carried the item's referenced spec sections
although only `dod_gate` grades them (bd-ib-tzvtgc: 24,910 to 136,040 characters
on bd-ib-qshcwc). The one-rubric-one-subject rule of `contracts.md` still requires
the node and every host taking to grade BYTE-IDENTICAL subjects, and since the bounded clause selection the node cannot rebuild the
subject by reading the spec tree itself. So the subject travels to the node as a
file a prepare step materializes, which only the `dod_gate` prompt reads.

THE FILE IS ASSERTED BY EXECUTING THE STEPS, because the claim is that a file with
the right bytes appears where the node reads. The steps are run in order under
bash against a throwaway plugins root, exactly as the sandbox runs them.
"""

from __future__ import annotations

import importlib
import subprocess
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    judgement_subject,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import CondensedClause
from livespec_orchestrator_beads_fabro.types import WorkItem

from tests.prepare_step_support import env_of, steps_in

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_subject"
_HEADING = "## Scenario 174 — The judgement runs before admission"


def _subject_module() -> ModuleType:
    return importlib.import_module(_MODULE)


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-7f66ar",
        type="feature",
        status="ready",
        title="Judge the Definition of Done before dispatch",
        description=(
            "## Definition of Done\n\n"
            "- The judgement runs before an item moves to ready.\n\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-20T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _write_spec(*, root: Path) -> None:
    spec = root / "SPECIFICATION"
    spec.mkdir()
    _ = (spec / "scenarios.md").write_text(
        f"{_HEADING}\n\nThe shared subject text.\n", encoding="utf-8"
    )


def _materialize(*, block: str, plugins_root: Path) -> str:
    """Run every step of a rendered block in order and read the file the node reads."""
    module = _subject_module()
    for step in steps_in(block=block):
        completed = subprocess.run(
            ["bash", "-c", step.script],
            check=False,
            capture_output=True,
            text=True,
            env=env_of(
                step=step,
                base={
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                    "HOME": str(plugins_root.parent / "home"),
                    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(plugins_root),
                },
            ),
        )
        assert completed.returncode == 0, completed.stderr
    return (plugins_root / module.DOD_GATE_SUBJECT_FILENAME).read_text(encoding="utf-8")


def test_the_node_subject_is_byte_identical_to_the_subject_a_host_taking_grades(
    tmp_path: Path,
) -> None:
    """Assertion 2: one item, one subject, whichever party renders it."""
    module = _subject_module()
    _write_spec(root=tmp_path)
    rider = "Rider: narrow the first assertion to the admission wall."
    record = "livespec-dod-judgement-unavailable\n\nThe judgement did not run."

    node_subject = module.dod_gate_subject(item=_item(), repo=tmp_path, comments=(rider, record))
    host_subject = judgement_subject(item=_item(), cwd=tmp_path, comments=(rider, record))
    landed = _materialize(
        block=module.dod_gate_subject_prepare_steps_block(subject=node_subject),
        plugins_root=tmp_path / "plugins",
    )

    assert node_subject == host_subject
    assert landed == host_subject
    assert "The shared subject text." in landed
    assert rider in landed
    assert "livespec-dod-judgement-unavailable" not in landed


def test_a_subject_larger_than_one_payload_value_lands_whole_and_byte_identical(
    tmp_path: Path,
) -> None:
    """The bounded subject may reach 150,000 characters; one env value may not hold it."""
    module = _subject_module()
    subject = (
        "é— multi-byte, $(touch /tmp/livespec-subject-should-not-exist) `date`\n" * 4000
    ) + "end"
    block = module.dod_gate_subject_prepare_steps_block(subject=subject)

    landed = _materialize(block=block, plugins_root=tmp_path / "plugins")

    assert len(steps_in(block=block)) > 1
    assert landed == subject
    assert not Path("/tmp/livespec-subject-should-not-exist").exists()


def test_the_step_scripts_carry_no_subject_bytes() -> None:
    """Fabro re-sends each completed stage's script to every later request."""
    module = _subject_module()
    subject = "unmistakable-subject-marker " * 5000
    steps = steps_in(block=module.dod_gate_subject_prepare_steps_block(subject=subject))

    assert steps
    assert all("unmistakable-subject-marker" not in step.script for step in steps)
    assert all(len(step.script) < 1000 for step in steps)


def test_no_subject_projects_no_step() -> None:
    assert _subject_module().dod_gate_subject_prepare_steps_block(subject=None) == ""


def test_the_node_reads_the_path_the_step_writes() -> None:
    module = _subject_module()
    expansion = module.dod_gate_subject_path_expansion()

    assert SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR in expansion
    assert expansion.endswith(f"/{module.DOD_GATE_SUBJECT_FILENAME}")


def test_the_node_subject_carries_every_clause_the_verdict_names_or_selects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assertion 3: the node's subject is built on the verdict the taking recorded."""
    module = _subject_module()
    _write_spec(root=tmp_path)
    verdict = GoverningHeadingVerdict(
        kind="partial",
        stated_by=(_HEADING,),
        generalization_target="## Governing",
        selected_clauses=(CondensedClause(heading=_HEADING, body="\n\nSelected clause marker.\n"),),
        named_clauses=(CondensedClause(heading=_HEADING, body="\n\nNamed clause marker.\n"),),
    )
    monkeypatch.setattr(module, "reusable_governing_heading_verdict", lambda **_: verdict)
    item = replace(_item(), title="Judge it")

    subject = module.dod_gate_subject(item=item, repo=tmp_path, comments=())

    assert "Selected clause marker." in subject
    assert "Named clause marker." in subject
    assert subject == judgement_subject(item=item, cwd=tmp_path, comments=(), governing=verdict)
