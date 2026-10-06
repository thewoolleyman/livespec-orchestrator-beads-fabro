"""The re-based plugin-currency gate: no ambient block, one deliberate floor.

Covers the three paths the v089 self-update contract re-bases this gate onto:
ambient release-staleness NEVER blocks, a committed `dispatcher.minimum_release`
floor is the sole blocking form, and unobservable currency is recorded as
UNDETERMINED and proceeds.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_staleness_gate as gate
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_RELEASE_SHA = "9532efb793bc1d2c3a4b5c6d7e8f901234567890"
_BUILD_ID = "b6e4012cafed"


@dataclass(kw_only=True)
class _Runner:
    results: dict[tuple[str, ...], CommandResult]
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        key = tuple(argv)
        self.calls.append(key)
        return self.results.get(key, CommandResult(exit_code=1, stdout="", stderr="missing"))


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _ls_remote(*, ref: str, sha: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=f"{sha}\t{ref}\n", stderr="")


def _release_head_runner() -> _Runner:
    """A runner whose `release` and `master` heads both differ from the build id."""
    return _Runner(
        results={
            gate.latest_release_ref_argv(): _ls_remote(
                ref="refs/heads/release",
                sha=_RELEASE_SHA,
            ),
            gate.master_ref_argv(): _ls_remote(ref="refs/heads/master", sha=_RELEASE_SHA),
        }
    )


def _cache_root(*, tmp_path: Path, version: str | None = None) -> Path:
    root = tmp_path / _BUILD_ID
    root.mkdir()
    if version is not None:
        _ = (root / "plugin.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    return root


def _write_floor(*, tmp_path: Path, floor: object) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {"livespec-orchestrator-beads-fabro": {"dispatcher": {"minimum_release": floor}}}
        ),
        encoding="utf-8",
    )


def test_ambient_release_lag_never_refuses_and_surfaces_the_remedy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A build behind the live `release` head proceeds — the homelab 2026-08-29 case.

    Plugin builds bind at SESSION START while this gate probes a MOVING ref at
    DISPATCH TIME, so refusing on that comparison bricked every live session the
    moment a release was published. With no `dispatcher.minimum_release` floor
    committed, the gate has no blocking authority at all: the lag is surfaced.
    """
    monkeypatch.chdir(tmp_path)
    cache_root = _cache_root(tmp_path=tmp_path)

    decision = gate.dispatcher_staleness_decision(
        plugin_root=cache_root,
        executing_payload=cache_root,
        runner=_release_head_runner(),
    )

    assert decision.refusal is None
    assert len(decision.warnings) == 1
    lag = decision.warnings[0]
    assert _BUILD_ID in lag.detail
    assert _RELEASE_SHA[:12] in lag.detail
    assert "ambient staleness is surfaced, not enforced" in lag.detail
    assert (
        "claude plugin update "
        "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro" in lag.detail
    )


def test_release_below_a_committed_floor_refuses_fail_closed_naming_the_floor(
    tmp_path: Path,
) -> None:
    _write_floor(tmp_path=tmp_path, floor="0.98.0")
    cache_root = _cache_root(tmp_path=tmp_path, version="0.97.1")

    decision = gate.dispatcher_staleness_decision(
        plugin_root=cache_root,
        executing_payload=cache_root,
        runner=_release_head_runner(),
        cwd=tmp_path,
    )

    assert decision.refusal is not None
    assert decision.refusal.stage == gate.MINIMUM_RELEASE_REFUSED_STAGE
    assert "dispatcher.minimum_release floor 0.98.0" in decision.refusal.detail
    assert "0.97.1" in decision.refusal.detail
    assert decision.warnings == ()


def test_release_at_the_committed_floor_proceeds_to_ambient_surfacing(tmp_path: Path) -> None:
    _write_floor(tmp_path=tmp_path, floor="0.97.1")
    cache_root = _cache_root(tmp_path=tmp_path, version="0.97.1")

    decision = gate.dispatcher_staleness_decision(
        plugin_root=cache_root,
        executing_payload=cache_root,
        runner=_release_head_runner(),
        cwd=tmp_path,
    )

    assert decision.refusal is None
    assert len(decision.warnings) == 1
    assert decision.warnings[0].stage == "dispatcher-staleness-warning"


def test_unobservable_executing_release_under_a_floor_records_undetermined_currency(
    tmp_path: Path,
) -> None:
    """A floor that cannot be EVALUATED proceeds — never a false refusal, never a silent pass."""
    _write_floor(tmp_path=tmp_path, floor="0.98.0")
    cache_root = _cache_root(tmp_path=tmp_path)

    decision = gate.dispatcher_staleness_decision(
        plugin_root=cache_root,
        executing_payload=cache_root,
        runner=_release_head_runner(),
        cwd=tmp_path,
    )

    assert decision.refusal is None
    assert len(decision.warnings) == 1
    assert decision.warnings[0].stage == gate.CURRENCY_UNDETERMINED_STAGE
    assert "currency could not be determined" in decision.warnings[0].detail
    assert "the executing release is unobservable" in decision.warnings[0].detail


def test_unorderable_floor_records_undetermined_currency(tmp_path: Path) -> None:
    _write_floor(tmp_path=tmp_path, floor="unreleased")
    cache_root = _cache_root(tmp_path=tmp_path, version="0.97.1")

    decision = gate.dispatcher_staleness_decision(
        plugin_root=cache_root,
        executing_payload=cache_root,
        runner=_release_head_runner(),
        cwd=tmp_path,
    )

    assert decision.refusal is None
    assert decision.warnings[0].stage == gate.CURRENCY_UNDETERMINED_STAGE
    assert "'unreleased'" in decision.warnings[0].detail


def test_unorderable_executing_release_records_undetermined_currency(tmp_path: Path) -> None:
    _write_floor(tmp_path=tmp_path, floor="0.98.0")
    cache_root = _cache_root(tmp_path=tmp_path, version="dev")

    decision = gate.dispatcher_staleness_decision(
        plugin_root=cache_root,
        executing_payload=cache_root,
        runner=_release_head_runner(),
        cwd=tmp_path,
    )

    assert decision.refusal is None
    assert decision.warnings[0].stage == gate.CURRENCY_UNDETERMINED_STAGE


def test_a_floor_value_the_setting_cannot_accept_records_undetermined_currency(
    tmp_path: Path,
) -> None:
    """An UNREADABLE floor is not an unconfigured one — it is recorded, not swallowed."""
    _write_floor(tmp_path=tmp_path, floor="")
    cache_root = _cache_root(tmp_path=tmp_path, version="0.97.1")

    decision = gate.dispatcher_staleness_decision(
        plugin_root=cache_root,
        executing_payload=cache_root,
        runner=_release_head_runner(),
        cwd=tmp_path,
    )

    assert decision.refusal is None
    assert decision.warnings[0].stage == gate.CURRENCY_UNDETERMINED_STAGE
    assert "could not be read" in decision.warnings[0].detail
    assert "a non-empty released-version identifier string" in decision.warnings[0].detail


def test_an_unparseable_config_records_undetermined_currency(tmp_path: Path) -> None:
    """A config that will not PARSE cannot answer "is a floor committed?" either."""
    _ = (tmp_path / ".livespec.jsonc").write_text("{ not json", encoding="utf-8")
    cache_root = _cache_root(tmp_path=tmp_path, version="0.97.1")

    decision = gate.dispatcher_staleness_decision(
        plugin_root=cache_root,
        executing_payload=cache_root,
        runner=_release_head_runner(),
        cwd=tmp_path,
    )

    assert decision.refusal is None
    assert decision.warnings[0].stage == gate.CURRENCY_UNDETERMINED_STAGE
    assert "could not be read" in decision.warnings[0].detail
    assert ".livespec.jsonc does not parse" in decision.warnings[0].detail


def test_apply_gate_returns_the_precondition_exit_only_under_a_committed_floor(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_floor(tmp_path=tmp_path, floor="0.98.0")
    cache_root = _cache_root(tmp_path=tmp_path, version="0.97.1")
    journal = _Journal()

    exit_code = gate.apply_dispatcher_staleness_gate(
        plugin_root=cache_root,
        executing_payload=cache_root,
        journal=journal,
        runner=_release_head_runner(),
        cwd=tmp_path,
    )

    assert exit_code == 3
    assert journal.records == [
        {
            "stage": gate.MINIMUM_RELEASE_REFUSED_STAGE,
            "detail": journal.records[0]["detail"],
            "blocking": True,
        }
    ]
    assert "0.98.0" in capsys.readouterr().err


def test_apply_gate_no_longer_returns_the_precondition_exit_for_ambient_staleness(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The retired refusal: a build behind the release head is journaled non-blocking."""
    cache_root = _cache_root(tmp_path=tmp_path)
    journal = _Journal()

    exit_code = gate.apply_dispatcher_staleness_gate(
        plugin_root=cache_root,
        executing_payload=cache_root,
        journal=journal,
        runner=_release_head_runner(),
        cwd=tmp_path,
    )

    assert exit_code is None
    assert [record["blocking"] for record in journal.records] == [False]
    assert journal.records[0]["stage"] == "dispatcher-staleness-warning"
    assert "dispatcher-staleness-refused" not in str(journal.records)
    assert _BUILD_ID in capsys.readouterr().err
