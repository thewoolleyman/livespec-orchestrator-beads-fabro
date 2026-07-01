"""Tests for the beads-private `status_conformance` doctor check.

The check wires the Dispatcher's `status-conformance` Ledger invariant into
`just check` / `/livespec:doctor`: every LIVE (non-`done`) work-item's stored
beads status MUST be one of `ALLOWED_BEADS_STATUSES` — the canonical 7-state
lifecycle projected through the adapter's `done` → `closed` rename, DERIVED
from the `WorkItemStatus` Literal. The pure `status_conformance_findings`
surface is exercised directly with constructed work-items (a conforming row,
an out-of-lifecycle row that IS flagged, and a row that yields a NON-status
Ledger finding which is filtered out); `main()` is driven hermetically
through the in-memory `FakeBeadsClient` for the exit-code + structlog
branches. A derivation test pins `ALLOWED_BEADS_STATUSES` to the
`WorkItemStatus` Literal so a stale hand-typed set (PR #227's failure mode)
cannot regress silently.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import get_args

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "status_conformance.py"


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("status_conformance_under_test", _CHECK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so any dataclass can resolve its own module via
    # `cls.__module__` under Python 3.10's kw_only detection.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The check imports `livespec_orchestrator_beads_fabro.*`; those resolve via the pytest
# pythonpath. Loading the module once at collection time is enough.
_CHECK = _load_check()

from livespec_orchestrator_beads_fabro.store import (  # noqa: E402
    ALLOWED_BEADS_STATUSES,
    append_work_item,
)
from livespec_orchestrator_beads_fabro.types import (  # noqa: E402
    DependsOnRaw,
    StoreConfig,
    WorkItem,
    WorkItemStatus,
)


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
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton

    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _item(
    *,
    id_: str,
    status: str = "ready",
    depends_on: tuple[DependsOnRaw, ...] = (),
) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status=status,  # type: ignore[arg-type]
        title="t",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=depends_on,
        captured_at="2026-06-11T00:00:00Z",
        resolution="completed" if status == "done" else None,
        reason="done" if status == "done" else None,
        audit=None,
        superseded_by=None,
    )


def _seed(item: WorkItem) -> None:
    append_work_item(path=_config(), item=item)


# -- derivation: the allowed set tracks the WorkItemStatus Literal ---------


def test_allowed_beads_statuses_derives_from_work_item_status() -> None:
    """`done` maps to beads `closed`; every other state appears verbatim.

    Pins `ALLOWED_BEADS_STATUSES` to the canonical 7-state `WorkItemStatus`
    Literal at runtime, so a stale hand-typed set (PR #227) fails here.
    """
    livespec_states = set(get_args(WorkItemStatus))
    assert livespec_states == {
        "backlog",
        "pending-approval",
        "ready",
        "active",
        "acceptance",
        "blocked",
        "done",
    }
    assert (livespec_states - {"done"}) | {"closed"} == ALLOWED_BEADS_STATUSES


# -- status_conformance_findings: keep vs drop -----------------------------


def test_findings_flag_out_of_lifecycle_and_drop_non_status_findings() -> None:
    items = [
        _item(id_="ok", status="ready"),
        _item(id_="bad-open", status="open"),
        # A malformed depends_on yields a `depends-on-ref-wellformedness`
        # Ledger finding, which this check filters OUT (non-status).
        _item(id_="dep", status="ready", depends_on=({"bad": True},)),
    ]
    findings = _CHECK.status_conformance_findings(items=items)
    assert [f.item_id for f in findings] == ["bad-open"]
    assert findings[0].check == "status-conformance"
    assert "status 'open' is outside the livespec lifecycle" in findings[0].message


def test_findings_empty_when_all_conforming() -> None:
    items = [_item(id_="a", status="ready"), _item(id_="b", status="active")]
    assert _CHECK.status_conformance_findings(items=items) == []


# -- main(): exit-code + structlog branches via the fake -------------------


def test_main_empty_tenant_passes_trivially() -> None:
    assert _CHECK.main() == 0


def test_main_conforming_tenant_exits_zero() -> None:
    _seed(_item(id_="li-ready", status="ready"))
    assert _CHECK.main() == 0


def test_main_out_of_lifecycle_status_exits_nonzero() -> None:
    """A live item stored with beads-native `open` is out-of-lifecycle."""
    _seed(_item(id_="li-open", status="open"))
    assert _CHECK.main() == 1
