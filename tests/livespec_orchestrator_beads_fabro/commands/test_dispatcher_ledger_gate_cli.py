"""CLI + fail-soft wiring of the `ledger-normalize --gate` pre-push gate.

The pure verdict function is covered in the sibling
`test_dispatcher_ledger_gate.py`. This file drives the gate through
`dispatcher.main(argv=[...])` against the hermetic fake tenant and asserts the
auto-heal-loud contract: the CLEAN / HEALED / DRIFT / SKIP markers, the 0/0/1/2
exit codes, the in-place heal (an `open` row is remapped to `backlog` and the
store IS written), the residual human-lane block (a healed row is still written
even when a residual row blocks the push), and the two fail-soft
could-not-check paths — an expected tenant-READ error and an expected heal-WRITE
error both SKIP (exit 2), never a false block.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_ledger_close,
    _dispatcher_ledger_gate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_gate import (
    LEDGER_GATE_CLEAN_MARKER,
    LEDGER_GATE_DRIFT_MARKER,
    LEDGER_GATE_SKIP_MARKER,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

# The stdout marker the gate prints when it heals in place. Asserted by literal
# so this file imports only the markers that predate the auto-heal change (the
# import block therefore stays valid at the Red commit's pre-change module).
_HEALED_MARKER = "LIVESPEC_LEDGER_GATE: HEALED"

_PREFIX_ONLY_CONFIG = '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}'


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="livespec-impl-beads-t1",
        type="task",
        status="ready",
        title="A ready task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _current_statuses(*, config: StoreConfig) -> dict[str, str]:
    materialized = materialize_work_items(records=read_work_items(path=config))
    return {item.id: str(item.status) for item in materialized.values()}


def _write_config(*, tmp_path: Path, text: str) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(text, encoding="utf-8")


def test_gate_clean_tenant_exits_zero_with_clean_marker(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _write_config(tmp_path=tmp_path, text=_PREFIX_ONLY_CONFIG)
    append_work_item(path=_config(), item=_item(id="ready-1", status="ready"))

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path), "--gate"])

    assert exit_code == 0
    assert LEDGER_GATE_CLEAN_MARKER in capsys.readouterr().out


def test_gate_open_item_heals_in_place_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _write_config(tmp_path=tmp_path, text=_PREFIX_ONLY_CONFIG)
    config = _config()
    append_work_item(path=config, item=_item(id="native-open", status="open"))

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path), "--gate"])

    # Auto-heal-loud: the safe transient remap is applied IN PLACE and the push
    # proceeds (exit 0), with the heal printed loud and the store actually
    # written — never blocked, never silent.
    assert exit_code == 0
    out = capsys.readouterr().out
    assert _HEALED_MARKER in out
    assert "native-open: open -> backlog" in out
    assert LEDGER_GATE_DRIFT_MARKER not in out
    assert _current_statuses(config=config) == {"native-open": "backlog"}


def test_gate_deferred_item_blocks_with_human_decision_message(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _write_config(tmp_path=tmp_path, text=_PREFIX_ONLY_CONFIG)
    append_work_item(path=_config(), item=_item(id="stuck-deferred", status="deferred"))

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path), "--gate"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert LEDGER_GATE_DRIFT_MARKER in out
    assert "stuck-deferred" in out
    assert "bd update <id> --status" in out
    assert "will NOT fix these" in out


def test_gate_open_and_deferred_heals_open_but_blocks_on_deferred(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _write_config(tmp_path=tmp_path, text=_PREFIX_ONLY_CONFIG)
    config = _config()
    append_work_item(path=config, item=_item(id="native-open", status="open"))
    append_work_item(path=config, item=_item(id="stuck-deferred", status="deferred"))

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path), "--gate"])

    # The open row heals in place (loud + written), but the residual deferred
    # row still blocks the push: the auto-heal is committed even though exit 1.
    assert exit_code == 1
    out = capsys.readouterr().out
    assert LEDGER_GATE_DRIFT_MARKER in out
    assert "native-open: open -> backlog" in out
    assert "stuck-deferred" in out
    statuses = _current_statuses(config=config)
    assert statuses["native-open"] == "backlog"
    assert statuses["stuck-deferred"] == "deferred"


def test_gate_fail_soft_skips_and_exits_two_on_tenant_read_error(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(tmp_path=tmp_path, text=_PREFIX_ONLY_CONFIG)

    def _raise(*, repo: Path) -> list[WorkItem]:
        _ = repo
        raise BeadsConnectionError(detail="connection refused")

    monkeypatch.setattr(_dispatcher_ledger_gate, "load_items", _raise)

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path), "--gate"])

    # Could-not-check must SKIP (exit 2), NEVER falsely block (exit 1).
    assert exit_code == 2
    captured = capsys.readouterr()
    assert LEDGER_GATE_SKIP_MARKER in captured.err
    assert "connection refused" in captured.err
    assert LEDGER_GATE_DRIFT_MARKER not in captured.out


def test_gate_fail_soft_skips_and_exits_two_on_heal_write_error(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(tmp_path=tmp_path, text=_PREFIX_ONLY_CONFIG)
    append_work_item(path=_config(), item=_item(id="native-open", status="open"))

    def _raise(*, path: StoreConfig, item_id: str, status: str) -> None:
        _ = (path, item_id, status)
        raise BeadsConnectionError(detail="write refused")

    # The heal WRITE seam raises an expected beads error mid-heal.
    monkeypatch.setattr(_dispatcher_ledger_close, "update_work_item_status", _raise)

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path), "--gate"])

    # A heal write that raises an expected beads error is could-not-check: SKIP
    # (exit 2), never a false block and never a crash.
    assert exit_code == 2
    captured = capsys.readouterr()
    assert LEDGER_GATE_SKIP_MARKER in captured.err
    assert "write refused" in captured.err
    assert LEDGER_GATE_DRIFT_MARKER not in captured.out


def test_gate_partial_heal_prints_each_written_remap_before_skipping(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(tmp_path=tmp_path, text=_PREFIX_ONLY_CONFIG)
    config = _config()
    append_work_item(path=config, item=_item(id="open-a", status="open"))
    append_work_item(path=config, item=_item(id="open-b", status="open"))

    real = _dispatcher_ledger_close.update_work_item_status
    calls = {"n": 0}

    def _flaky(*, path: StoreConfig, item_id: str, status: str) -> None:
        calls["n"] += 1
        if calls["n"] >= 2:
            raise BeadsConnectionError(detail="write refused mid-heal")
        real(path=path, item_id=item_id, status=status)

    monkeypatch.setattr(_dispatcher_ledger_close, "update_work_item_status", _flaky)

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path), "--gate"])

    # The FIRST remap was written to the shared tenant before the second write
    # failed. The loud-audit guarantee must hold on a partial heal: every remap
    # that reached the store is printed, even though the gate then skips.
    assert exit_code == 2
    captured = capsys.readouterr()
    assert LEDGER_GATE_SKIP_MARKER in captured.err
    statuses = _current_statuses(config=config)
    written = [item_id for item_id in ("open-a", "open-b") if statuses[item_id] == "backlog"]
    assert len(written) == 1
    other = "open-b" if written[0] == "open-a" else "open-a"
    assert statuses[other] == "open"
    assert f"{written[0]}: open -> backlog" in captured.out


def test_gate_fresh_mappable_arrival_during_heal_does_not_block(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(tmp_path=tmp_path, text=_PREFIX_ONLY_CONFIG)
    # The initial read sees one open item; a concurrent session's raw `bd create`
    # lands a fresh open item during the heal window (staged as a second read).
    # The gate must NOT block on that fresh MAPPABLE status: it computes residual
    # over the PROJECTION of the initial snapshot, never a live reload.
    initial = [_item(id="native-open", status="open")]
    injected = [
        _item(id="native-open", status="backlog"),
        _item(id="fresh-open", status="open"),
    ]
    calls = {"n": 0}

    def _staged_load(*, repo: Path) -> list[WorkItem]:
        _ = repo
        calls["n"] += 1
        return list(injected) if calls["n"] >= 2 else list(initial)

    monkeypatch.setattr(_dispatcher_ledger_gate, "load_items", _staged_load)

    def _noop_write(*, path: StoreConfig, item_id: str, status: str) -> None:
        _ = (path, item_id, status)

    # The heal write is a no-op here (reads are stubbed, so there is no store).
    monkeypatch.setattr(_dispatcher_ledger_close, "update_work_item_status", _noop_write)

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path), "--gate"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert LEDGER_GATE_DRIFT_MARKER not in out
    assert "native-open: open -> backlog" in out
    assert "fresh-open" not in out
