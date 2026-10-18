"""The materialized per-assertion Proof of Done grade, as an artifact.

Scenario 195's behaviour is exercised end to end against the shipped bytes in
`tests/integration/test_proof_grade_scenario195.py`. What is left here is what
that test cannot see: the properties of the PROGRAM ITSELF. A grade that reads a
record correctly in a process where this package happens to be importable is
broken in exactly the way no behavioural case can reach — the governed clone has
no copy of the package — and a grade whose reader is a second ACCOUNT of the
record format would agree with the acceptance pass today and drift tomorrow,
silently, with every assertion still reading as unevidenced.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
)
_MODULE_PATH = _COMMANDS / "_dispatcher_proof_grade_program.py"

_RUN_ID = "0f7c1b5fd4ff4a2f9c4f0d2b6e8a1c33"

_VERIFIED_RECORD = f"""Proof of Done — verified — run {_RUN_ID} — 2026-10-17T09:00:00Z

Publish-branch head: {"a" * 40}

## Assertion 1 — alpha holds.

Proof mode: `factory_captured`

Reproduced: yes.

## Assertion 2 — beta holds.

Proof mode: `factory_captured`

Reproduced: yes.
"""


def _module() -> ModuleType:
    """The host module under test, imported by path so Red fails on the assertion."""
    spec = importlib.util.spec_from_file_location("_livespec_proof_grade_program", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _materialized(*, tmp_path: Path) -> ModuleType:
    """The sandbox program as a module, loaded from the bytes the prepare step writes.

    Written beside its reader directory exactly as the prepare step lands it, so
    the import this performs is the import the sandbox performs.
    """
    host = _module()
    root = tmp_path / "plugins"
    reader = root / host.PROOF_GRADE_READER_DIRECTORY
    reader.mkdir(parents=True)
    for name, source in host.proof_record_reader_sources():
        _ = (reader / name).write_text(source, encoding="utf-8")
    path = root / host.PROOF_GRADE_PROGRAM_FILENAME
    _ = path.write_text(host.proof_grade_program_source(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("livespec_proof_grade", path)
    assert spec is not None
    assert spec.loader is not None
    program = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(program)
    return program


def test_the_grade_reads_the_acceptance_passs_own_record_reader_bytes(tmp_path: Path) -> None:
    """Every factory assertion verdicted in prose grades the record reproduced.

    THE READER IS THE SHIPPED BYTES, not a second account of the format. The
    sources the prepare step writes are the package's own `.py` files with their
    intra-package import prefix stripped, so the sandbox grades with the reader
    the acceptance pass grades with rather than with one held equal to it by
    hope. Asserted by loading the program in a process where the package is NOT
    importable under its own name and still grading a real record shape.
    """
    assert _MODULE_PATH.is_file()
    host = _module()
    program = _materialized(tmp_path=tmp_path)

    record = program.attributed_verified_record(
        comments=[{"body": _VERIFIED_RECORD, "url": "https://forge/comment/1"}],
        run_ids=(_RUN_ID,),
    )

    assert record is not None
    assert (
        program.ungraded_assertions(record=record, assertions=["alpha holds.", "beta holds."]) == []
    )
    assert "livespec_orchestrator_beads_fabro" not in host.proof_grade_program_source()


def test_a_record_of_another_dispatch_is_not_this_dispatchs_evidence(tmp_path: Path) -> None:
    """Attribution is the same closed question the acceptance pass asks.

    The control is the SAME bytes read under a different accepted set: a grade
    that had stopped filtering would return the record either way, and the
    verdict it then published would be about a run this dispatch is not.
    """
    program = _materialized(tmp_path=tmp_path)
    comments = [{"body": _VERIFIED_RECORD, "url": "https://forge/comment/1"}]

    assert program.attributed_verified_record(comments=comments, run_ids=(_RUN_ID,)) is not None
    assert program.attributed_verified_record(comments=comments, run_ids=("other-run",)) is None


def test_an_item_declaring_no_factory_assertion_grades_nothing(tmp_path: Path) -> None:
    """Nothing to grade is not a failure to grade.

    A host-only or legacy item declares no `factory_captured` assertion, so the
    projection carries an empty list and the grade has no verdict to read. It
    advances, exactly as the acceptance pass's own proof leg does for such an
    item; refusing here would park every host-only item at non-convergence.
    """
    program = _materialized(tmp_path=tmp_path)

    record = program.attributed_verified_record(
        comments=[{"body": _VERIFIED_RECORD, "url": "u"}], run_ids=(_RUN_ID,)
    )

    assert record is not None
    assert program.ungraded_assertions(record=record, assertions=[]) == []
