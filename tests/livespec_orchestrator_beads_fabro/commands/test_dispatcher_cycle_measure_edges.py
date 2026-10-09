"""Edge arms of the product logical-line measurement.

Beside `test_dispatcher_cycle_measure`, which pins the measurement's meaning,
this file exercises the arms a malformed declaration and an unusual module
reach: a `mirror_pairings` array entry that is not a table, an entry declaring
no source tree, an empty module, and a module whose first statement is a
constant that is not a docstring.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_measure import (
    changed_product_logical_lines,
    product_source_prefixes,
)


def test_a_non_table_pairing_entry_is_skipped_rather_than_failing_the_read() -> None:
    prefixes = product_source_prefixes(
        pyproject_text=(
            "[tool.livespec_dev_tooling]\n"
            'mirror_pairings = [1, {source_tree = "src/pkg", test_tree = "tests/pkg"}]\n'
        )
    )

    assert prefixes == ("src/pkg",)


def test_a_pairing_declaring_no_source_tree_contributes_no_prefix() -> None:
    prefixes = product_source_prefixes(
        pyproject_text=(
            "[tool.livespec_dev_tooling]\n"
            'mirror_pairings = [{test_tree = "tests/pkg"}, {source_tree = ""}]\n'
        )
    )

    assert prefixes == ()


def test_a_non_table_section_on_the_declaration_path_yields_no_prefixes() -> None:
    assert product_source_prefixes(pyproject_text="tool = 1\n") == ()


def test_an_empty_module_carries_no_logical_lines_and_no_change() -> None:
    assert changed_product_logical_lines(before="", after="") == 0
    assert changed_product_logical_lines(before="", after="value = 1\n") == 1


def test_a_leading_constant_that_is_not_a_docstring_counts_as_code() -> None:
    assert changed_product_logical_lines(before="1\n", after="2\n") == 2
    assert changed_product_logical_lines(before="1\n", after="1\nvalue = 1\n") == 1
