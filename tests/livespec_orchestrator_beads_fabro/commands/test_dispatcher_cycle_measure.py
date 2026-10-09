"""The canonical product logical-line measurement one completed cycle reports.

Scenario 165's first assertion needs changed product logical lines to mean
"added plus removed logical lines between the pair's test-only Red state and
Green state, not net file growth", through the repository's canonical
logical-line counting and product-path classification, excluding tests,
documentation, comments, blank lines and formatting-only changes.

The cases that matter are the ones a naive reader gets wrong: a replaced
statement is TWO changed lines rather than a net zero; a docstring or comment
edit is zero rather than one; a `ruff format` reflow that changes no token is
zero rather than the physical-line churn it looks like; and a source that does
not tokenize is UNOBSERVABLE rather than zero.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_measure"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_cycle_measure.py"
)


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first.

    The existence assertion is deliberate: it is the genuine failing assertion
    the Red commit for this slice stands on, rather than a collection-time
    `ModuleNotFoundError` that would prove only unimportability.
    """
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def test_a_replaced_statement_counts_added_plus_removed_not_net_growth() -> None:
    module = _module()

    changed = module.changed_product_logical_lines(
        before="value = 1\nother = 2\n",
        after="value = 3\nother = 2\n",
    )

    assert changed == 2


def test_docstring_comment_and_blank_line_edits_change_nothing() -> None:
    module = _module()

    changed = module.changed_product_logical_lines(
        before='"""One."""\n\nvalue = 1\n',
        after='"""Another, much longer sentence."""\n\n\n# A new comment.\nvalue = 1\n',
    )

    assert changed == 0


def test_a_formatting_only_reflow_changes_nothing() -> None:
    module = _module()

    changed = module.changed_product_logical_lines(
        before="value = render(first, second)\n",
        after="value = render(\n    first,\n    second,\n)\n",
    )

    assert changed == 0


def test_an_untokenizable_source_is_unobserved_rather_than_zero() -> None:
    module = _module()

    assert module.changed_product_logical_lines(before="value = (\n", after="value = 1\n") is None
    assert module.changed_product_logical_lines(before="value = 1\n", after="def (:\n") is None


def test_product_path_classification_excludes_tests_docs_and_vendored_code() -> None:
    module = _module()
    prefixes = (".claude-plugin/scripts/livespec_orchestrator_beads_fabro", "dev-tooling/checks")

    assert module.is_product_path(
        path=".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/x.py",
        prefixes=prefixes,
    )
    assert not module.is_product_path(path="tests/commands/test_x.py", prefixes=prefixes)
    assert not module.is_product_path(
        path=".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/x.md",
        prefixes=prefixes,
    )
    assert not module.is_product_path(
        path=".claude-plugin/scripts/_vendor/tomli/_parser.py", prefixes=prefixes
    )
    assert not module.is_product_path(path="plan/topic/handoff.md", prefixes=prefixes)


def test_product_source_prefixes_come_from_this_repositorys_own_declaration() -> None:
    module = _module()

    prefixes = module.product_source_prefixes(
        pyproject_text=(_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert ".claude-plugin/scripts/livespec_orchestrator_beads_fabro" in prefixes
    assert "dev-tooling/checks" in prefixes


def test_an_unparseable_declaration_yields_no_prefixes_rather_than_a_guess() -> None:
    module = _module()

    assert module.product_source_prefixes(pyproject_text="not = = toml") == ()
    assert module.product_source_prefixes(pyproject_text="[tool.other]\nx = 1\n") == ()


def test_the_measurement_method_is_named_for_operator_replay() -> None:
    module = _module()

    assert isinstance(module.PRODUCT_LLOC_MEASUREMENT_METHOD, str)
    assert module.PRODUCT_LLOC_MEASUREMENT_METHOD != ""
