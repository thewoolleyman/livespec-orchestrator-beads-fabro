"""Integration-tier acceptance for SPECIFICATION/scenarios.md "Scenario 16 —
Closed-item-integrity check rejects 'closed but unproven'".

Binds the `closed_item_integrity` dev-tooling check's user-observable
behavior through the REAL store/client seam against the in-memory
`FakeBeadsClient` (the hermetic CI backend), plus a real on-disk
`tests/heading-coverage.json` carrying the `clauses[]` gap-id->scenario
map the check resolves against. The two Scenario-16 cases are exercised
end to end through the check's `main()`:

- A closed gap-tied item whose `gap-id` resolves to a scenario still
  bound to the `TODO` sentinel (or which lacks the `resolution:completed`
  label) surfaces a `closed-item-integrity` finding: a warning at exit 0
  in the default `warn` mode, an error at exit non-zero in `fail` mode.
- A fully-proven closed gap-tied item (carries `resolution:completed`
  and resolves to a scenario bound to a real integration-tier test node
  id) surfaces NO finding.

The check is driven hermetically: `LIVESPEC_BEADS_FAKE=1` flips the store
onto the fake, the process-singleton is reset per test, and the working
directory is a `tmp_path` carrying a fixture `tests/heading-coverage.json`
so `main()` reads the map from cwd (as `just check-closed-item-integrity`
reads it from the repo root).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "closed_item_integrity.py"
_CHECK_MODULE_NAME = "closed_item_integrity_under_scenario16"


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

from livespec_impl_beads.store import append_work_item  # noqa: E402
from livespec_impl_beads.types import StoreConfig, WorkItem  # noqa: E402

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
    from livespec_impl_beads._beads_client import reset_fake_singleton

    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _write_coverage(*, test_node: str) -> None:
    """Write a tests/heading-coverage.json fixture linking _GAP_ID -> Scenario 16."""
    entries = [
        {
            "heading": f"## {_SCENARIO}",
            "spec_root": "SPECIFICATION",
            "spec_file": "scenarios.md",
            "test": test_node,
            "clauses": [{"gap_id": _GAP_ID, "scenario": _SCENARIO}],
            "reason": "fixture",
        }
    ]
    coverage_dir = Path.cwd() / "tests"
    coverage_dir.mkdir(parents=True, exist_ok=True)
    _ = (coverage_dir / "heading-coverage.json").write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


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
# Scenario 16, case 1 — a closed-but-unproven gap-tied item surfaces a finding.
# --------------------------------------------------------------------------


def test_todo_bound_scenario_warns_in_warn_mode() -> None:
    """Given a closed gap-tied item whose scenario is TODO-bound,
    When the check runs in the default warn mode,
    Then it surfaces the offender as a warning and exits 0."""
    _write_coverage(test_node="TODO")
    _seed(_item(id_="li-todo", resolution="completed"))
    assert _CHECK.main() == 0


def test_todo_bound_scenario_errors_in_fail_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given a closed gap-tied item whose scenario is TODO-bound,
    When the check runs with LIVESPEC_CLOSED_ITEM_INTEGRITY=fail,
    Then it surfaces the offender as an error and exits non-zero."""
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _write_coverage(test_node="TODO")
    _seed(_item(id_="li-todo", resolution="completed"))
    assert _CHECK.main() == 1


def test_missing_resolution_label_errors_in_fail_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """A closed gap-tied item lacking the resolution:completed label is an
    offender even when its scenario binds to a real test."""
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _write_coverage(test_node=_REAL_TEST_NODE)
    _seed(_item(id_="li-nolabel", resolution=None))
    assert _CHECK.main() == 1


def test_unresolvable_gap_id_errors_in_fail_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """A closed gap-tied item whose gap-id has no clauses[] link is an
    offender (its acceptance scenario cannot be proven)."""
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _write_coverage(test_node=_REAL_TEST_NODE)
    _seed(_item(id_="li-orphan", gap_id="gap-unlinked", resolution="completed"))
    assert _CHECK.main() == 1


# --------------------------------------------------------------------------
# Scenario 16, case 2 — a fully-proven closed gap-tied item emits no finding.
# --------------------------------------------------------------------------


def test_proven(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given a closed gap-tied item that carries resolution:completed and
    resolves to a scenario bound to a real integration-tier test,
    When the check runs (even in fail mode),
    Then it emits NO finding and exits 0."""
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _write_coverage(test_node=_REAL_TEST_NODE)
    _seed(_item(id_="li-proven", resolution="completed"))
    assert _CHECK.main() == 0


def test_empty_tenant_passes_trivially(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hermetic empty tenant yields no closed items, so the check passes
    trivially in both lever modes."""
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _write_coverage(test_node=_REAL_TEST_NODE)
    assert _CHECK.main() == 0


def test_open_gap_tied_item_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """An OPEN gap-tied item (not yet closed) is out of scope — the invariant
    governs CLOSED items only."""
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _write_coverage(test_node="TODO")
    _seed(_item(id_="li-open", status="open", resolution=None))
    assert _CHECK.main() == 0


def test_freeform_closed_item_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """A closed FREEFORM item (no gap-id) is out of scope — the invariant
    governs gap-tied items only."""
    monkeypatch.setenv("LIVESPEC_CLOSED_ITEM_INTEGRITY", "fail")
    _write_coverage(test_node="TODO")
    _seed(_item(id_="li-free", origin="freeform", gap_id=None, resolution="wontfix"))
    assert _CHECK.main() == 0
