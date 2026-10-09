"""Tier 0 Enemy Unit Tests for the real Fabro dependency.

This suite is intentionally outside `tests/` so the hermetic `just check`
aggregate never needs a live Fabro server or credentials. Invoke it explicitly:

    just fabro-enemy-tier0
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from _tier0_support import (
    TIMEOUT_SECONDS,
    _assert_success,
    _completed_run_id,
    _FabroTier0Config,
    _inspect_record,
    _mapping,
    _run_records,
    _status_kind,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = []

_WORKFLOW_PATH = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_EXPECTED_PS_FIELDS = frozenset(("run_id", "status", "goal", "total_usd_micros"))
# Measured against the pinned build (0.254.0, 8de6611) on 2026-08-20: a real
# `fabro inspect --json` record carries exactly these keys. `updated_at` is
# NOT among them -- see test_tier0_watchdog_gap.py.
_EXPECTED_INSPECT_FIELDS = frozenset(("status", "run_id", "conclusion"))
# `recorded_at` is the Petri-era envelope field (measured on
# 0.378.0-nightly.0, research note 006, which is why this tier 0 test failed
# against the candidate); the three older names are what 0.254.0 emitted. Kept
# in step with `_tier1_support.EVENT_TIMESTAMP_FIELDS` and with the product
# reader in `_dispatcher_watchdog`, which this set is the live control for.
_EVENT_TIMESTAMP_FIELDS = frozenset(("timestamp", "ts", "at", "recorded_at"))
TERMINAL_STATUS_KINDS = frozenset(
    (
        "blocked",
        "canceled",
        "cancelled",
        "completed",
        "done",
        "error",
        "errored",
        "failed",
        "green",
        "merged",
        "succeeded",
        "success",
    )
)


def test_version_reports_client_and_server_independently(
    *,
    config: _FabroTier0Config,
    port: FabroPort,
) -> None:
    result = port.version(timeout_seconds=TIMEOUT_SECONDS)

    _assert_success(command=result.command)
    text = result.text.lower()
    assert "client" in text
    assert "server" in text
    assert config.expected_client_version in result.text
    assert config.expected_client_commit in result.text
    assert config.expected_client_date in result.text
    assert config.expected_server_version in result.text
    assert config.expected_server_commit in result.text
    assert config.expected_server_date in result.text
    assert config.server_url in result.text


def test_validate_accepts_livespec_workflow_templated_acp_command(
    *,
    port: FabroPort,
) -> None:
    """Zero-spend proof of the `acp.command` templating contract fabro #474 breaks.

    MUST NOT be run with a linked git worktree as the working directory.
    Measured 2026-08-20 on the pinned build: `fabro validate` returns in under
    a second when cwd is the primary checkout or /tmp, and hangs until timeout
    when cwd is a linked worktree (one whose `.git` is a gitlink file). The
    workflow path makes no difference -- an absolute path hangs too -- so the
    trigger is the working directory, not the argument.
    """
    workflow_text = _WORKFLOW_PATH.read_text()

    # The single `acp_adapter` input was split into per-node adapter inputs by
    # the ACP-node-adapter-layering refactor (master `8cb60236`); the fabro #474
    # contract the EUT guards is that `acp.command` stays templated on every ACP
    # node, so assert the templated form on each per-node adapter rather than a
    # now-absent single input name.
    for adapter in ("implement_adapter", "fix_adapter", "pr_adapter", "review_adapter"):
        assert 'acp.command="{{ inputs.' + adapter + ' }}"' in workflow_text
    result = port.validate(workflow_toml=_WORKFLOW_PATH, timeout_seconds=TIMEOUT_SECONDS)

    _assert_success(command=result.command)
    assert result.payload is not None


def test_ps_records_carry_reader_field_set(*, port: FabroPort) -> None:
    result = port.ps(timeout_seconds=TIMEOUT_SECONDS)

    _assert_success(command=result.command)
    records = _run_records(payload=result.payload)
    assert records
    assert result.runs
    for record in records:
        assert set(record) >= _EXPECTED_PS_FIELDS
        assert isinstance(record["run_id"], str)
        assert record["run_id"]
        assert _status_kind(record=record) is not None


def test_server_flag_is_per_subcommand(*, port: FabroPort) -> None:
    suffixed = port.ps(timeout_seconds=TIMEOUT_SECONDS)
    top_level = port.top_level_server_parse_probe(
        subcommand=("ps", "-a", "--json"),
        timeout_seconds=TIMEOUT_SECONDS,
    )

    _assert_success(command=suffixed.command)
    assert top_level.command.exit_code != 0
    parse_error_text = f"{top_level.command.stdout}\n{top_level.command.stderr}".lower()
    assert "--server" in parse_error_text


def test_inspect_and_events_completed_run_field_sets(
    *,
    config: _FabroTier0Config,
    port: FabroPort,
) -> None:
    run_id = config.completed_run_id or _completed_run_id(port=port)
    inspect = port.inspect(run_id=run_id, timeout_seconds=TIMEOUT_SECONDS)
    events = port.events(run_id=run_id, timeout_seconds=TIMEOUT_SECONDS)

    _assert_success(command=inspect.command)
    _assert_success(command=events.command)
    # `fabro inspect --json` returns a single-element LIST on the pinned build,
    # not a bare mapping. Asserting the mapping shape here is what caught the
    # production parser guarding on isinstance(payload, dict) and silently
    # returning None for every real payload.
    inspect_record = _inspect_record(value=inspect.payload)
    assert set(inspect_record) >= _EXPECTED_INSPECT_FIELDS
    assert inspect.status_kind is not None
    event_records = _event_records(stdout=events.command.stdout, payload=events.payload)
    assert event_records
    assert any(_has_event_timestamp(event=event) for event in event_records)


def _event_records(*, stdout: str, payload: object | None) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [_mapping(value=item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        events = payload.get("events")
        if isinstance(events, list):
            return [_mapping(value=item) for item in events if isinstance(item, dict)]
        return [cast("dict[str, Any]", payload)]
    records: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if line.strip() == "":
            continue
        decoded = json.loads(line)
        if isinstance(decoded, dict):
            records.append(cast("dict[str, Any]", decoded))
    return records


def _has_event_timestamp(*, event: dict[str, Any]) -> bool:
    for key in _EVENT_TIMESTAMP_FIELDS:
        value = event.get(key)
        if isinstance(value, str):
            return bool(value)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return True
    return False
