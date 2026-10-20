"""Scenario 200 — declared record files merge during a refresh, without a repair round.

WHY THIS FILE EXISTS. `SPECIFICATION/contracts.md` section "Declared record
files merge without a repair round" (revision v162) gives the refresh stages a
new arm: a conflict confined to files this repository DECLARES as shared
append-only records is merged entry by entry rather than handed to the fix
agent. The declaration is the whole input to that arm, and it lives in committed
configuration rather than in code, so nothing in the package can establish it.

This module executes the five stage sub-scenarios against the shipped
`pr_refresh` bytes through the real-Git harness in
`test_scripted_refresh_execution.py`.  The harness is deliberately loaded as
the test subject rather than paraphrased here: it parses the committed DOT
graph, materializes the production merger and helpers, and asserts origin's
actual refs.  Keeping Scenario 200's cases here makes the scenario's own test
entry point a reproducible stage-level proof of configuration, merge ordering,
observability, and repair routing.
"""

from __future__ import annotations

import importlib.util
import sys
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._jsonc import loads

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STAGE_CASES_PATH = _REPO_ROOT / "tests" / "integration" / "test_scripted_refresh_execution.py"


class _Scenario200StageCases(Protocol):
    """The shipped-stage cases Scenario 200 owns, loaded from their real-Git harness."""

    def test_a_declared_json_record_conflict_merges_and_republishes_without_repair(
        self, tmp_path: Path
    ) -> None: ...

    def test_a_declared_json_record_merge_is_recorded_with_its_format_and_per_side_counts(
        self, tmp_path: Path
    ) -> None: ...

    def test_a_declared_markdown_record_conflict_keeps_the_defaults_lines_then_the_runs(
        self, tmp_path: Path
    ) -> None: ...

    def test_a_conflict_outside_the_declared_records_merges_nothing_and_takes_repair(
        self, tmp_path: Path
    ) -> None: ...

    def test_a_declared_record_whose_key_both_sides_changed_differently_takes_repair(
        self, tmp_path: Path
    ) -> None: ...

    def test_a_merged_record_head_the_gate_rejects_takes_repair(self, tmp_path: Path) -> None: ...


@cache
def _stage_cases() -> _Scenario200StageCases:
    """Load the real-Git stage harness without relying on pytest collection order."""
    specification = importlib.util.spec_from_file_location(
        "scenario200_shipped_stage_cases", _STAGE_CASES_PATH
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    assert isinstance(module, ModuleType)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return cast("_Scenario200StageCases", module)


# The four shared records every revise and every scenario-binding change in this
# repository appends to, and therefore the four this repository declares. The two
# JSON arrays are keyed by the triple that identifies one heading, which is the
# identity `heading_coverage` itself indexes them by; the two Markdown files are
# flat bullet registries a new test file inserts one entry into.
_EXPECTED_RECORD_FILES = [
    {
        "path": "tests/heading-coverage.json",
        "format": "json-array",
        "key": ["spec_root", "spec_file", "heading"],
    },
    {
        "path": "tests/heading-coverage-debt.json",
        "format": "json-array",
        "key": ["spec_root", "spec_file", "heading"],
    },
    {"path": "tests/integration/CLAUDE.md", "format": "markdown-insertions"},
    {"path": "tests/prompts/CLAUDE.md", "format": "markdown-insertions"},
]


def _committed_dispatcher_configuration() -> dict[str, object]:
    """The committed `dispatcher` table, read the way the sandbox stage reads it.

    Through the repository's own JSONC loader rather than `json.loads`, because
    `.livespec.jsonc` carries `//` comments and a bare JSON parse of it raises
    rather than returning a drifted value — which would make this case fail for
    the wrong reason and hide whatever the declaration actually says.
    """
    config = cast(
        "dict[str, object]",
        loads(text=(_REPO_ROOT / ".livespec.jsonc").read_text(encoding="utf-8")),
    )
    plugin = config.get("livespec-orchestrator-beads-fabro")
    assert isinstance(plugin, dict)
    dispatcher = plugin.get("dispatcher")
    assert isinstance(dispatcher, dict)
    return cast("dict[str, object]", dispatcher)


def test_the_committed_configuration_declares_this_repositorys_shared_record_files() -> None:
    """The declaration names the four records, with the formats v162 defines.

    Asserted as a whole list rather than by containment: the arm merges ONLY
    declared paths, so an extra entry widens what a refresh will rewrite without
    a human in the loop, and a missing one leaves the collision this item was
    filed for costing a whole factory run. Both directions matter, and only an
    equality check sees both.
    """
    dispatcher = _committed_dispatcher_configuration()

    assert dispatcher.get("record_files") == _EXPECTED_RECORD_FILES


def test_stage_merges_declared_json_records_in_default_then_run_order(tmp_path: Path) -> None:
    _stage_cases().test_a_declared_json_record_conflict_merges_and_republishes_without_repair(
        tmp_path
    )


def test_stage_records_each_json_merge_with_its_format_and_side_counts(tmp_path: Path) -> None:
    _stage_cases().test_a_declared_json_record_merge_is_recorded_with_its_format_and_per_side_counts(
        tmp_path
    )


def test_stage_merges_declared_markdown_insertions_in_default_then_run_order(
    tmp_path: Path,
) -> None:
    _stage_cases().test_a_declared_markdown_record_conflict_keeps_the_defaults_lines_then_the_runs(
        tmp_path
    )


def test_stage_routes_an_undeclared_conflict_to_refresh_repair(tmp_path: Path) -> None:
    _stage_cases().test_a_conflict_outside_the_declared_records_merges_nothing_and_takes_repair(
        tmp_path
    )


def test_stage_routes_a_differently_changed_record_key_to_refresh_repair(
    tmp_path: Path,
) -> None:
    _stage_cases().test_a_declared_record_whose_key_both_sides_changed_differently_takes_repair(
        tmp_path
    )


def test_stage_routes_a_gate_rejection_of_the_merged_head_to_refresh_repair(
    tmp_path: Path,
) -> None:
    _stage_cases().test_a_merged_record_head_the_gate_rejects_takes_repair(tmp_path)
