# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""closed_item_integrity — beads-private closed-item-integrity static check.

Mechanical guard for the closed-item-integrity invariant
(SPECIFICATION/constraints.md §"Closed-item integrity" and contracts.md
§"Closed-item-integrity check"). A closed gap-tied work-item must mean
"proven", not merely "status flipped": it MUST carry the
`resolution:completed` label AND its acceptance scenario MUST be bound to
a real integration-tier-or-above test in `tests/heading-coverage.json`
(never the `TODO` sentinel).

The check enumerates every closed gap-tied work-item from the store,
derives each item's `gap-id` from its materialized `gap_id` (the store
derives that from the `gap-id:<id>` label), resolves the gap-id to an
acceptance scenario via the `clauses[]` gap-id→scenario map in
`tests/heading-coverage.json`, and emits a `closed-item-integrity`
finding for any item whose resolved scenario's heading-coverage entry is
still `TODO`-bound (or unresolvable) OR which lacks the
`resolution:completed` label.

Severity is governed by the self-documenting `LIVESPEC_CLOSED_ITEM_INTEGRITY`
lever (only `warn` and `fail` are recognized): `warn` (the DEFAULT)
surfaces each offender as a warning and exits 0; `fail` surfaces each as
an error and exits non-zero; an unset or unrecognized value defaults to
`warn`. The lever is the SEVERITY switch, not a wiring carve-out — the
check always enumerates every closed gap-tied item and always runs.

The check REUSES existing primitives and introduces NO new gap-id logic:
gap-ids ride the shared `livespec_spec_clauses` extractor's derivation
(the same `clauses[]` `gap_id` values that map carries), the `clauses[]`
map is read from `tests/heading-coverage.json` (the contract livespec
core's constraints.md §"Heading taxonomy" defines), and closed gap-tied
items are read through the existing beads store reader. In hermetic mode
(`LIVESPEC_BEADS_FAKE` truthy, the default `just check` tier) the tenant
is empty, so the enumeration yields nothing and the check passes
trivially. Per-violation diagnostics flow through structlog (JSON to
stderr) — the only output surface the `no_write_direct` ban permits.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
_SCRIPTS_VENDOR = _SCRIPTS / "_vendor"
for _path in (_SCRIPTS, _SCRIPTS_VENDOR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# structlog is the only sanctioned stderr surface for an enforcement script
# (per the `no_write_direct` ban on direct `sys.stderr.write`). It is not
# vendored in this repo's own tree, so it is imported from the installed
# `livespec_dev_tooling` package's vendored copy, whose path is added to
# `sys.path` here. The file-level pyright pragma above silences the
# untyped-structlog diagnostics this import would otherwise raise.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
if str(_DT_VENDOR) not in sys.path:
    sys.path.insert(0, str(_DT_VENDOR))

import structlog  # noqa: E402
from livespec_impl_beads.commands._config import resolve_store_config  # noqa: E402
from livespec_impl_beads.store import materialize_work_items, read_work_items  # noqa: E402
from livespec_impl_beads.types import WorkItem  # noqa: E402

__all__: list[str] = ["main"]

_LEVER_ENV = "LIVESPEC_CLOSED_ITEM_INTEGRITY"
_LEVER_WARN = "warn"
_LEVER_FAIL = "fail"

_TODO_SENTINEL = "TODO"
_COVERAGE_RELPATH = ("tests", "heading-coverage.json")
_REQUIRED_RESOLUTION = "completed"


@dataclass(frozen=True, kw_only=True)
class ScenarioBinding:
    """The acceptance-scenario binding a `clauses[]` gap-id resolves to.

    `scenario` is the scenarios.md H2 section name the `clauses[]` entry
    names; `test_node` is that scenario's heading-coverage `test` field
    (a live integration-tier test node id, or the `TODO` sentinel).
    `proven` is True iff `test_node` is a real node id (not `TODO`).
    """

    scenario: str
    test_node: str

    @property
    def proven(self) -> bool:
        return self.test_node != _TODO_SENTINEL


def _resolve_lever(*, raw: str | None) -> str:
    """Resolve the severity lever; unset/unrecognized defaults to `warn`."""
    if raw == _LEVER_FAIL:
        return _LEVER_FAIL
    return _LEVER_WARN


def _coverage_path(*, cwd: Path) -> Path:
    return cwd.joinpath(*_COVERAGE_RELPATH)


def _scenario_name(*, heading: str) -> str:
    """Strip a leading `## ` from a heading-coverage `heading` field."""
    prefix = "## "
    return heading[len(prefix) :] if heading.startswith(prefix) else heading


def load_clause_map(*, coverage_path: Path) -> dict[str, ScenarioBinding]:
    """Build the gap-id→ScenarioBinding map from `tests/heading-coverage.json`.

    Walks every entry's `clauses[]` array; for each `{gap_id, scenario}`
    link, resolves the named scenario to its own heading-coverage entry's
    `test` field (matching the `scenario` value to a scenarios.md H2
    section name). A `clauses[]` link whose `scenario` does not resolve to
    a live scenario entry is skipped (it does not count as a link, per the
    core `clauses[]` contract). A missing or malformed coverage file
    yields an empty map.
    """
    if not coverage_path.is_file():
        return {}
    try:
        parsed = json.loads(coverage_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(parsed, list):
        return {}
    entries = cast("list[Any]", parsed)
    scenario_test = _scenario_test_index(entries=entries)
    clause_map: dict[str, ScenarioBinding] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        _absorb_entry_clauses(
            entry=cast("dict[str, Any]", entry),
            scenario_test=scenario_test,
            clause_map=clause_map,
        )
    return clause_map


def _absorb_entry_clauses(
    *,
    entry: dict[str, Any],
    scenario_test: dict[str, str],
    clause_map: dict[str, ScenarioBinding],
) -> None:
    """Resolve one heading-coverage entry's `clauses[]` into `clause_map`."""
    clauses = entry.get("clauses")
    if not isinstance(clauses, list):
        return
    for clause in cast("list[Any]", clauses):
        if not isinstance(clause, dict):
            continue
        clause_dict = cast("dict[str, Any]", clause)
        gap_id = clause_dict.get("gap_id")
        scenario = clause_dict.get("scenario")
        if not isinstance(gap_id, str) or not isinstance(scenario, str):
            continue
        test_node = scenario_test.get(scenario)
        if test_node is None:
            continue
        clause_map[gap_id] = ScenarioBinding(scenario=scenario, test_node=test_node)


def _scenario_test_index(*, entries: list[Any]) -> dict[str, str]:
    """Map each scenarios.md H2 section name to its heading-coverage `test`."""
    index: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_dict = cast("dict[str, Any]", entry)
        if entry_dict.get("spec_file") != "scenarios.md":
            continue
        heading = entry_dict.get("heading")
        test_node = entry_dict.get("test")
        if not isinstance(heading, str) or not isinstance(test_node, str):
            continue
        index[_scenario_name(heading=heading)] = test_node
    return index


def offender_reason(*, item: WorkItem, clause_map: dict[str, ScenarioBinding]) -> str | None:
    """Return why a closed gap-tied item is closed-but-unproven, or None.

    The caller has already filtered to `status == "closed"` and
    `origin == "gap-tied"`. An item is an offender when it lacks the
    `resolution:completed` label, when its gap-id has no resolvable
    `clauses[]` scenario link, or when that scenario is still `TODO`-bound.
    """
    if item.resolution != _REQUIRED_RESOLUTION:
        return "lacks the resolution:completed label"
    if item.gap_id is None:
        return "gap-tied item carries no gap-id"
    binding = clause_map.get(item.gap_id)
    if binding is None:
        return f"gap-id {item.gap_id!r} resolves to no acceptance scenario via clauses[]"
    if not binding.proven:
        return (
            f"acceptance scenario {binding.scenario!r} is still bound to the TODO "
            f"sentinel (not a real integration-tier test)"
        )
    return None


def _closed_gap_tied(*, index: dict[str, WorkItem]) -> list[WorkItem]:
    return [
        item for item in index.values() if item.status == "closed" and item.origin == "gap-tied"
    ]


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("closed_item_integrity")
    lever = _resolve_lever(raw=os.environ.get(_LEVER_ENV))
    cwd = Path.cwd()
    clause_map = load_clause_map(coverage_path=_coverage_path(cwd=cwd))
    config = resolve_store_config(cwd=cwd, work_items_arg=None)
    index = materialize_work_items(read_work_items(path=config.work_items_path))
    offenders: list[tuple[str, str]] = []
    for item in _closed_gap_tied(index=index):
        reason = offender_reason(item=item, clause_map=clause_map)
        if reason is not None:
            offenders.append((item.id, reason))
    if not offenders:
        return 0
    for work_item_id, reason in offenders:
        event = "closed-item-integrity finding"
        if lever == _LEVER_FAIL:
            log.error(event, work_item=work_item_id, detail=reason, severity=_LEVER_FAIL)
        else:
            log.warning(event, work_item=work_item_id, detail=reason, severity=_LEVER_WARN)
    return 1 if lever == _LEVER_FAIL else 0


# The shebang-less module is invoked via `just check-closed-item-integrity`
# (`uv run python dev-tooling/checks/closed_item_integrity.py`); the guard
# keeps the exit code propagating to the shell.
if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
