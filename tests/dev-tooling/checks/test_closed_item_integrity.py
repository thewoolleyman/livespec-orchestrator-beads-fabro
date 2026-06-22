"""Tests for the beads-private `closed_item_integrity` static check.

The check enumerates every closed gap-tied work-item from the store,
resolves each item's gap-id to an acceptance scenario via the `clauses[]`
gap-id->scenario map in `tests/heading-coverage.json`, and emits a
`closed-item-integrity` finding for any item that lacks the
`resolution:completed` label or whose scenario is still `TODO`-bound (or
unresolvable). Severity rides the `LIVESPEC_CLOSED_ITEM_INTEGRITY=warn|fail`
lever (default warn).

Tests drive it hermetically through the in-memory `FakeBeadsClient`:
`LIVESPEC_BEADS_FAKE=1` flips the store onto the fake, the singleton is
reset per test, the working directory is a `tmp_path` carrying a fixture
`tests/heading-coverage.json`, and the lever env var is cleared so each
test sets its own mode.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "closed_item_integrity.py"
_CHECK_MODULE_NAME = "closed_item_integrity_under_test"


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_CHECK_MODULE_NAME, _CHECK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so the module's `@dataclass` introspection can
    # resolve `KW_ONLY` via `sys.modules[cls.__module__]`.
    sys.modules[_CHECK_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


_CHECK = _load_check()

from livespec_orchestrator_beads_fabro.store import append_work_item  # noqa: E402
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem  # noqa: E402

_GAP_ID = "gap-j2femmn7"
_SCENARIO = 'Scenario 16 — Closed-item-integrity check rejects "closed but unproven"'
_REAL_TEST_NODE = "tests.integration.test_closed_item_integrity_scenario16.test_proven"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.delenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", raising=False)
    monkeypatch.chdir(tmp_path)
    # The check resolves the tenant connection from cwd via
    # resolve_store_config, which REQUIRES an explicit connection.prefix
    # (decoupled from the tenant DB name); mirror a real governed repo.
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton

    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _write_coverage_text(*, text: str) -> Path:
    coverage_dir = Path.cwd() / "tests"
    coverage_dir.mkdir(parents=True, exist_ok=True)
    path = coverage_dir / "heading-coverage.json"
    _ = path.write_text(text, encoding="utf-8")
    return path


def _write_coverage(*, test_node: str, gap_id: str = _GAP_ID, scenario: str = _SCENARIO) -> Path:
    entries = [
        {
            "heading": f"## {scenario}",
            "spec_root": "SPECIFICATION",
            "spec_file": "scenarios.md",
            "test": test_node,
            "clauses": [{"gap_id": gap_id, "scenario": scenario}],
            "reason": "fixture",
        }
    ]
    return _write_coverage_text(text=json.dumps(entries, indent=2, ensure_ascii=False) + "\n")


def _item(
    *,
    id_: str,
    status: str = "closed",
    origin: str = "gap-tied",
    gap_id: str | None = _GAP_ID,
    resolution: str | None = "completed",
) -> WorkItem:
    return WorkItem(
        id=id_,
        type="feature",  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        title="t",
        description="d",
        origin=origin,  # type: ignore[arg-type]
        gap_id=gap_id,
        priority=1,
        assignee=None,
        depends_on=(),
        captured_at="2026-06-20T00:00:00Z",
        resolution=resolution,  # type: ignore[arg-type]
        reason="done",
        audit=None,
        superseded_by=None,
    )


def _seed(item: WorkItem) -> None:
    append_work_item(path=_config(), item=item)


# --------------------------------------------------------------------------
# Empty store + trivial pass.
# --------------------------------------------------------------------------


def test_empty_tenant_passes_trivially() -> None:
    _ = _write_coverage(test_node=_REAL_TEST_NODE)
    assert _CHECK.main() == 0


def test_empty_tenant_passes_trivially_in_fail_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _ = _write_coverage(test_node=_REAL_TEST_NODE)
    assert _CHECK.main() == 0


# --------------------------------------------------------------------------
# Out-of-scope items (open, freeform) are ignored.
# --------------------------------------------------------------------------


def test_open_gap_tied_item_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _ = _write_coverage(test_node="TODO")
    _seed(_item(id_="li-open", status="open", resolution=None))
    assert _CHECK.main() == 0


def test_closed_freeform_item_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _ = _write_coverage(test_node="TODO")
    _seed(_item(id_="li-free", origin="freeform", gap_id=None, resolution="wontfix"))
    assert _CHECK.main() == 0


# --------------------------------------------------------------------------
# Offenders — TODO-bound scenario.
# --------------------------------------------------------------------------


def test_todo_bound_scenario_warns_and_exits_zero() -> None:
    _ = _write_coverage(test_node="TODO")
    _seed(_item(id_="li-todo", resolution="completed"))
    assert _CHECK.main() == 0


def test_todo_bound_scenario_errors_in_fail_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _ = _write_coverage(test_node="TODO")
    _seed(_item(id_="li-todo", resolution="completed"))
    assert _CHECK.main() == 1


# --------------------------------------------------------------------------
# Offenders — missing resolution:completed label / unresolvable gap-id.
# --------------------------------------------------------------------------


def test_missing_resolution_label_errors_in_fail_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _ = _write_coverage(test_node=_REAL_TEST_NODE)
    _seed(_item(id_="li-nolabel", resolution=None))
    assert _CHECK.main() == 1


def test_non_completed_resolution_errors_in_fail_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _ = _write_coverage(test_node=_REAL_TEST_NODE)
    _seed(_item(id_="li-wontfix", resolution="wontfix"))
    assert _CHECK.main() == 1


def test_unresolvable_gap_id_errors_in_fail_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _ = _write_coverage(test_node=_REAL_TEST_NODE)
    _seed(_item(id_="li-orphan", gap_id="gap-unlinked", resolution="completed"))
    assert _CHECK.main() == 1


# --------------------------------------------------------------------------
# Fully-proven item emits no finding.
# --------------------------------------------------------------------------


def test_proven_item_passes_in_fail_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _ = _write_coverage(test_node=_REAL_TEST_NODE)
    _seed(_item(id_="li-proven", resolution="completed"))
    assert _CHECK.main() == 0


# --------------------------------------------------------------------------
# Lever resolution.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("fail", "fail"),
        ("warn", "warn"),
        (None, "warn"),
        ("", "warn"),
        ("FAIL", "warn"),
        ("anything-else", "warn"),
    ],
)
def test_resolve_lever(raw: str | None, expected: str) -> None:
    assert _CHECK._resolve_lever(raw=raw) == expected  # noqa: SLF001


def test_unrecognized_lever_value_defaults_to_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "loud")
    _ = _write_coverage(test_node="TODO")
    _seed(_item(id_="li-todo", resolution="completed"))
    assert _CHECK.main() == 0


# --------------------------------------------------------------------------
# clause-map loading edge cases.
# --------------------------------------------------------------------------


def test_load_clause_map_missing_file_is_empty() -> None:
    assert _CHECK.load_clause_map(coverage_path=Path.cwd() / "no-such.json") == {}


def test_load_clause_map_malformed_json_is_empty() -> None:
    path = _write_coverage_text(text="{ not json ")
    assert _CHECK.load_clause_map(coverage_path=path) == {}


def test_load_clause_map_non_list_root_is_empty() -> None:
    path = _write_coverage_text(text='{"a": 1}')
    assert _CHECK.load_clause_map(coverage_path=path) == {}


def test_load_clause_map_resolves_binding() -> None:
    path = _write_coverage(test_node=_REAL_TEST_NODE)
    clause_map = _CHECK.load_clause_map(coverage_path=path)
    binding = clause_map[_GAP_ID]
    assert binding.scenario == _SCENARIO
    assert binding.test_node == _REAL_TEST_NODE
    assert binding.proven is True


def test_load_clause_map_todo_binding_is_unproven() -> None:
    path = _write_coverage(test_node="TODO")
    binding = _CHECK.load_clause_map(coverage_path=path)[_GAP_ID]
    assert binding.proven is False


def test_load_clause_map_clause_without_resolvable_scenario_is_skipped() -> None:
    """A clauses[] link naming a scenario with no live entry is not a link."""
    entries = [
        {
            "heading": "## Scenario 1 — something",
            "spec_root": "SPECIFICATION",
            "spec_file": "scenarios.md",
            "test": _REAL_TEST_NODE,
            "clauses": [{"gap_id": _GAP_ID, "scenario": "Scenario 99 — does not exist"}],
            "reason": "fixture",
        }
    ]
    path = _write_coverage_text(text=json.dumps(entries) + "\n")
    assert _CHECK.load_clause_map(coverage_path=path) == {}


def test_load_clause_map_ignores_malformed_entries() -> None:
    """Non-dict entries, non-list/absent clauses, malformed clause objects,
    non-scenarios.md entries, and non-string heading/test are all skipped."""
    entries = [
        "not-a-dict",
        {"heading": "## Purpose", "spec_file": "spec.md", "test": "TODO"},
        {"heading": "## No clauses", "spec_file": "scenarios.md", "test": "TODO"},
        {"heading": "## Bad clauses", "spec_file": "scenarios.md", "test": "TODO", "clauses": 5},
        {
            "heading": "## Mixed clauses",
            "spec_file": "scenarios.md",
            "test": _REAL_TEST_NODE,
            "clauses": [
                "not-a-dict",
                {"gap_id": 7, "scenario": "Mixed clauses"},
                {"gap_id": "gap-good", "scenario": "Mixed clauses"},
            ],
        },
        {"heading": 123, "spec_file": "scenarios.md", "test": "TODO"},
        {"heading": "## No test", "spec_file": "scenarios.md", "test": None},
    ]
    path = _write_coverage_text(text=json.dumps(entries) + "\n")
    clause_map = _CHECK.load_clause_map(coverage_path=path)
    assert set(clause_map) == {"gap-good"}
    assert clause_map["gap-good"].test_node == _REAL_TEST_NODE


# --------------------------------------------------------------------------
# offender_reason — direct helper coverage.
# --------------------------------------------------------------------------


def test_offender_reason_missing_label() -> None:
    reason = _CHECK.offender_reason(item=_item(id_="x", resolution=None), clause_map={})
    assert reason is not None
    assert "resolution:completed" in reason


def test_offender_reason_no_gap_id() -> None:
    """Defensive: a gap-tied item with no gap-id (off-invariant) is flagged."""
    item = _item(id_="x", gap_id=None, resolution="completed")
    reason = _CHECK.offender_reason(item=item, clause_map={})
    assert reason is not None
    assert "no gap-id" in reason


def test_offender_reason_unresolvable_gap_id() -> None:
    item = _item(id_="x", gap_id="gap-zzz", resolution="completed")
    reason = _CHECK.offender_reason(item=item, clause_map={})
    assert reason is not None
    assert "no acceptance scenario" in reason


def test_offender_reason_todo_scenario() -> None:
    binding = _CHECK.ScenarioBinding(scenario=_SCENARIO, test_node="TODO")
    item = _item(id_="x", resolution="completed")
    reason = _CHECK.offender_reason(item=item, clause_map={_GAP_ID: binding})
    assert reason is not None
    assert "TODO" in reason


def test_offender_reason_proven_returns_none() -> None:
    binding = _CHECK.ScenarioBinding(scenario=_SCENARIO, test_node=_REAL_TEST_NODE)
    item = _item(id_="x", resolution="completed")
    assert _CHECK.offender_reason(item=item, clause_map={_GAP_ID: binding}) is None


def test_scenario_name_strips_heading_prefix() -> None:
    assert _CHECK._scenario_name(heading="## Scenario 1 — x") == "Scenario 1 — x"  # noqa: SLF001
    assert _CHECK._scenario_name(heading="Scenario 1 — x") == "Scenario 1 — x"  # noqa: SLF001


def test_module_main_is_callable() -> None:
    assert callable(_CHECK.main)
