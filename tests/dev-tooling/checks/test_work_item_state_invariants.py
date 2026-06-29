"""Tests for the beads-private `work_item_state_invariants` doctor check.

The check walks every materialized work-item and applies the L1a S6
work-item-state invariants: a fail-soft non-sentinel-`rank` WARNING and a
rank-key-length WARNING for live heads, plus the hard `active ⟹ assignee`
and stored `blocked ⟹ blocked_reason` ERRORs. The pure `item_findings`
surface is exercised directly with constructed work-items (full
per-invariant branch coverage, including the bottom-sentinel rank a store
append cannot easily seed); `main()` is driven hermetically through the
in-memory `FakeBeadsClient` for the exit-code + structlog branches.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "work_item_state_invariants.py"


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "work_item_state_invariants_under_test", _CHECK_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so the `Finding` dataclass can resolve its own
    # module via `cls.__module__` (Python 3.10's `kw_only` KW_ONLY detection
    # reads `sys.modules[cls.__module__].__dict__`, which is None for an
    # unregistered synthetic module name).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The check imports `livespec_orchestrator_beads_fabro.*`; those resolve via the pytest
# pythonpath. Loading the module once at collection time is enough.
_CHECK = _load_check()

from livespec_orchestrator_beads_fabro.store import append_work_item  # noqa: E402
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem  # noqa: E402
from livespec_runtime.work_items.rank import BOTTOM_SENTINEL  # noqa: E402


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
    rank: str = "a2",
    assignee: str | None = None,
    blocked_reason: str | None = None,
) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status=status,  # type: ignore[arg-type]
        title="t",
        description="d",
        origin="freeform",
        gap_id=None,
        rank=rank,
        assignee=assignee,
        depends_on=(),
        captured_at="2026-05-19T00:00:00Z",
        resolution="completed" if status == "done" else None,
        reason="done" if status == "done" else None,
        audit=None,
        superseded_by=None,
        blocked_reason=blocked_reason,  # type: ignore[arg-type]
    )


def _seed(item: WorkItem) -> None:
    append_work_item(path=_config(), item=item)


# -- item_findings: rank invariants (live heads only) --------------------


def test_done_item_is_exempt_from_rank_checks() -> None:
    findings = _CHECK.item_findings(item=_item(id_="x", status="done", rank=BOTTOM_SENTINEL))
    assert findings == []


def test_live_sentinel_rank_emits_non_sentinel_warning() -> None:
    findings = _CHECK.item_findings(item=_item(id_="x", status="ready", rank=BOTTOM_SENTINEL))
    assert len(findings) == 1
    assert findings[0].invariant == "non-sentinel-rank"
    assert findings[0].severity == "warning"


def test_live_long_rank_emits_rank_key_length_warning() -> None:
    findings = _CHECK.item_findings(item=_item(id_="x", status="ready", rank="a" * 11))
    assert len(findings) == 1
    assert findings[0].invariant == "rank-key-length"
    assert findings[0].severity == "warning"


def test_live_normal_rank_has_no_rank_finding() -> None:
    findings = _CHECK.item_findings(item=_item(id_="x", status="ready", rank="a2"))
    assert findings == []


# -- item_findings: active ⟹ assignee (hard ERROR) -----------------------


def test_active_without_assignee_is_error() -> None:
    findings = _CHECK.item_findings(item=_item(id_="x", status="active", assignee=None))
    assert [f.invariant for f in findings] == ["active-requires-assignee"]
    assert findings[0].severity == "error"


def test_active_with_empty_assignee_is_error() -> None:
    findings = _CHECK.item_findings(item=_item(id_="x", status="active", assignee=""))
    assert [f.invariant for f in findings] == ["active-requires-assignee"]


def test_active_with_assignee_passes() -> None:
    findings = _CHECK.item_findings(item=_item(id_="x", status="active", assignee="someone"))
    assert findings == []


# -- item_findings: stored blocked ⟹ blocked_reason (hard ERROR) ---------


def test_blocked_without_reason_is_error() -> None:
    findings = _CHECK.item_findings(item=_item(id_="x", status="blocked", blocked_reason=None))
    assert [f.invariant for f in findings] == ["blocked-requires-reason"]
    assert findings[0].severity == "error"


@pytest.mark.parametrize("reason", ["needs-human", "infra-external"])
def test_blocked_with_valid_reason_passes(reason: str) -> None:
    findings = _CHECK.item_findings(item=_item(id_="x", status="blocked", blocked_reason=reason))
    assert findings == []


def test_blocked_with_derived_dependency_reason_is_error() -> None:
    """`dependency` is a DERIVED lane reason and is never a stored reason."""
    findings = _CHECK.item_findings(
        item=_item(id_="x", status="blocked", blocked_reason="dependency")
    )
    assert [f.invariant for f in findings] == ["blocked-requires-reason"]


# -- main(): exit-code + structlog branches via the fake -----------------


def test_main_empty_tenant_passes_trivially() -> None:
    assert _CHECK.main() == 0


def test_main_warning_only_exits_zero() -> None:
    """A live head with an over-long rank warns (NAMED) but never fails."""
    _seed(_item(id_="li-long", status="ready", rank="a" * 12))
    assert _CHECK.main() == 0


def test_main_error_exits_nonzero() -> None:
    """An active work-item without an assignee is a hard invariant breach."""
    _seed(_item(id_="li-active", status="active", assignee=None))
    assert _CHECK.main() == 1
