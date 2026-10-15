"""The materialized carry-forward decision program, as an artifact.

Scenario 178's behaviour is exercised end to end against real git in
`tests/integration/test_pr_refresh_carry_forward_scenario178.py`. What is left
here is what that test cannot see: the properties of the SHIPPED BYTES. A
program that decides correctly in a sandbox where this package happens to be
importable, or whose prepare step lets the shell substitute into its own source,
is broken in exactly the way no behavioural case can reach — the governed clone
has no copy of the package, and the decision's forbidden-character set contains a
literal `$` and a literal backtick.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_carry_forward_program import (
    CARRY_FORWARD_PROGRAM_FILENAME,
    carry_forward_program_path_expansion,
    carry_forward_program_prepare_steps_block,
    carry_forward_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_carry_forward_record import (
    record_reader_fragment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_head import (
    proof_head_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)


def _materialized(*, tmp_path: Path) -> ModuleType:
    """The program as a module, loaded from the bytes the prepare step writes."""
    path = tmp_path / CARRY_FORWARD_PROGRAM_FILENAME
    _ = path.write_text(carry_forward_program_source(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("livespec_carry_forward", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_program_imports_in_a_clone_that_has_no_copy_of_this_package(
    tmp_path: Path,
) -> None:
    """The composition resolves: every fragment's names are defined by the time it runs.

    Loading it is the assertion. The fragments are concatenated in a dependency
    order the assembly owns — the record reader defines `FENCE` and
    `fence_after`, the grammar defines `canonical_path` and the refusal reasons,
    the parse uses all four, the decision uses everything — so a reordering
    raises `NameError` here rather than deciding something wrong in a sandbox.
    """
    program = _materialized(tmp_path=tmp_path)

    assert "livespec_orchestrator_beads_fabro" not in carry_forward_program_source()
    for name in (
        "classify_command",
        "canonical_path",
        "published_head",
        "record_verdict",
        "reproduction_steps",
        "read_identities",
        "declared_working_directory",
        "step_command",
        "decide",
        "render",
        "main",
    ):
        assert callable(getattr(program, name)), name


def test_the_two_materialized_programs_share_one_record_reader() -> None:
    """One account of the record format, composed into both programs.

    This is the whole reason the reader moved out of
    `_dispatcher_publication_head`: that module measured a second, hand-rolled
    account of this format returning NOTHING on 100% of real records, so a
    second materialized program reading it had to compose the same text rather
    than carry a copy. Asserted on the SHARED FRAGMENT appearing in both
    sources, because two copies that happened to agree today would pass any
    behavioural comparison.
    """
    shared = record_reader_fragment()

    assert shared in carry_forward_program_source()
    assert shared in proof_head_program_source()


def test_the_prepare_step_writes_the_program_through_a_quoted_heredoc() -> None:
    """The shell must substitute nothing into a source carrying `$` and a backtick.

    The decision's forbidden-character set is a literal containing both, so an
    UNQUOTED heredoc delimiter would have the shell expand them away while the
    step still succeeded — leaving a grammar that admits the substitutions it
    exists to exclude.
    """
    block = carry_forward_program_prepare_steps_block()

    assert "[[run.prepare.steps]]" in block
    assert "<<'LIVESPEC_CARRY_FORWARD_PROGRAM'" in block
    assert CARRY_FORWARD_PROGRAM_FILENAME in block


def test_the_node_and_the_prepare_step_resolve_one_root() -> None:
    """A node resolving a different root than the prepare pass finds no program."""
    expansion = carry_forward_program_path_expansion()

    assert expansion.startswith(sandbox_plugins_root_expansion())
    assert expansion.endswith(f"/{CARRY_FORWARD_PROGRAM_FILENAME}")
    assert expansion in carry_forward_program_prepare_steps_block().replace("\\", "")
