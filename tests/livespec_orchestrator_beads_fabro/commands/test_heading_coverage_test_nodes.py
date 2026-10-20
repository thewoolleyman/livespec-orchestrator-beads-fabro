"""Tests for resolving a coverage entry's test node id against the tree.

Every case pairs a RESOLVING id with a NON-RESOLVING one of the same
spelling. A resolver that answered `True` for everything, and one that
answered `False` for everything, each satisfy half the module on their
own — and both failures are silent at the detector's surface: the first
reports a dangling registry as fully covered, the second reports a
healthy repository as 252 gaps and 124 findings.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._heading_coverage_test_nodes import (
    names_an_existing_test,
)


def _write_module(*, project_root: Path, dotted: str, body: str) -> None:
    module = project_root.joinpath(*dotted.split(".")).with_suffix(".py")
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(body)


def _write_present_module(*, project_root: Path) -> None:
    _write_module(
        project_root=project_root,
        dotted="tests.integration.test_present",
        body="async def test_async_case() -> None:\n    pass\n\n\ndef test_present_case() -> None:\n    pass\n",
    )


def test_a_dotted_module_and_function_resolves_only_when_both_exist(tmp_path: Path) -> None:
    _write_present_module(project_root=tmp_path)
    assert names_an_existing_test(
        project_root=tmp_path, test_node="tests.integration.test_present.test_present_case"
    )
    assert not names_an_existing_test(
        project_root=tmp_path, test_node="tests.integration.test_present.test_renamed_case"
    )


def test_an_async_test_function_resolves(tmp_path: Path) -> None:
    """An `async def` test is a test, and the registry may legitimately name one."""
    _write_present_module(project_root=tmp_path)
    assert names_an_existing_test(
        project_root=tmp_path, test_node="tests.integration.test_present.test_async_case"
    )


def test_the_pytest_node_id_spelling_resolves_only_when_both_exist(tmp_path: Path) -> None:
    """The live registry carries 36 rows in this spelling; a dotted-only resolver calls them all dangling."""
    _write_present_module(project_root=tmp_path)
    assert names_an_existing_test(
        project_root=tmp_path, test_node="tests.integration.test_present::test_present_case"
    )
    assert not names_an_existing_test(
        project_root=tmp_path, test_node="tests.integration.test_present::test_renamed_case"
    )


def test_a_module_only_node_id_resolves_only_when_the_module_exists(tmp_path: Path) -> None:
    _write_present_module(project_root=tmp_path)
    assert names_an_existing_test(project_root=tmp_path, test_node="tests.integration.test_present")
    assert not names_an_existing_test(
        project_root=tmp_path, test_node="tests.integration.test_absent"
    )


def test_an_id_naming_an_absent_module_does_not_resolve_in_either_spelling(
    tmp_path: Path,
) -> None:
    assert not names_an_existing_test(
        project_root=tmp_path, test_node="tests.integration.test_gone.test_case"
    )
    assert not names_an_existing_test(
        project_root=tmp_path, test_node="tests.integration.test_gone::test_case"
    )


def test_an_id_with_no_dot_at_all_does_not_resolve(tmp_path: Path) -> None:
    """It names no module by inspection, which is an answer rather than a failure."""
    assert not names_an_existing_test(project_root=tmp_path, test_node="test_present_case")


def test_an_empty_id_does_not_resolve(tmp_path: Path) -> None:
    assert not names_an_existing_test(project_root=tmp_path, test_node="")


def test_an_id_whose_function_part_is_empty_does_not_resolve(tmp_path: Path) -> None:
    """A trailing separator states no function, so the row names no test."""
    _write_present_module(project_root=tmp_path)
    assert not names_an_existing_test(
        project_root=tmp_path, test_node="tests.integration.test_present::"
    )


def test_an_id_pointing_into_an_unparseable_module_does_not_resolve(tmp_path: Path) -> None:
    """A module this reader cannot parse defines nothing it can see.

    The paired control is every other case in this module: a resolver that
    returned `False` for parseable modules too would fail all of them.
    """
    _write_module(
        project_root=tmp_path,
        dotted="tests.integration.test_broken",
        body="def test_broken_case(:\n",
    )
    assert not names_an_existing_test(
        project_root=tmp_path, test_node="tests.integration.test_broken.test_broken_case"
    )
