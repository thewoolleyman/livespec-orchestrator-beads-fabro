"""CLI + fail-soft wiring of the `ledger-normalize --gate` pre-push gate.

The pure verdict function is covered in the sibling
`test_dispatcher_ledger_gate.py`. This file drives the gate through
`dispatcher.main(argv=[...])` against the hermetic fake tenant and asserts the
0/1/2 exit-code contract, the marker lines, the credential-wrapper heal
command, the dry-run (never-mutates) guarantee, and the fail-soft
could-not-check path (an expected tenant-read error → SKIP + exit 2, never a
false block).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_ledger_gate
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

_PREFIX_ONLY_CONFIG = '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}'
_WRAPPER = "/usr/local/bin/with-livespec-env.sh"
_WRAPPER_CONFIG = (
    '{"credential_wrapper": ["' + _WRAPPER + '", "--"],'
    ' "livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}'
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


def test_gate_open_item_blocks_with_auto_mappable_heal_command_and_no_mutation(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _write_config(tmp_path=tmp_path, text=_WRAPPER_CONFIG)
    config = _config()
    append_work_item(path=config, item=_item(id="native-open", status="open"))

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path), "--gate"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert LEDGER_GATE_DRIFT_MARKER in out
    assert "native-open: open -> backlog" in out
    # The heal command carries the configured credential-wrapper prefix.
    assert f"{_WRAPPER} -- python3 .claude-plugin/scripts/bin/dispatcher.py ledger-normalize" in out
    # --gate implies dry-run: the store is never mutated.
    assert _current_statuses(config=config) == {"native-open": "open"}


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


def test_gate_bare_config_prints_wrapperless_heal_command(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    # No top-level credential_wrapper key → the bare `python3 …` heal form.
    _write_config(tmp_path=tmp_path, text=_PREFIX_ONLY_CONFIG)
    append_work_item(path=_config(), item=_item(id="native-open", status="open"))

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path), "--gate"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "python3 .claude-plugin/scripts/bin/dispatcher.py ledger-normalize" in out
    assert _WRAPPER not in out


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
