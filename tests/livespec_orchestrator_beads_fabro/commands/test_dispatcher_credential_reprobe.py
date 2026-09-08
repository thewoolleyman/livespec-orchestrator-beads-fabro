"""The bounded credential re-probe that holds the `loop` path open.

Covers the provider-spend-containment clauses `SPECIFICATION/contracts.md`
ratified at v103 — the admission-time credential-probe refusal re-probes
rather than exiting, and its remedy carries no provider timing claim as an
instruction — together with the journey `SPECIFICATION/scenarios.md` states
for them.

Two of the cases here are shaped by what a WRONG implementation would also
pass, so they are worth naming:

- The resume case asserts the probe was called three times AND that the two
  refusals were journaled as two records. Either half alone is satisfied by an
  implementation that never waited: a single usable probe returns a usable
  status too, and a wait that journals nothing is exactly the silent re-probe
  the clause forbids.
- The no-retirement case reads the exhaustion record back through the
  PRODUCTION reader over a REAL on-disk journal, after a usable probe. A test
  that only asserted "no clearance record was written" would pass against an
  implementation that retired the record by some other route; asking the reader
  whether the record still governs is the question the clause actually poses.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    ClaudeCredentialStatus,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    dispatch_provider_exhaustion,
)
from livespec_orchestrator_beads_fabro.commands._drive_config_schema import (
    api_configurable_key_manifest,
)

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_credential_reprobe.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_reprobe"

_TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
_CONFIG_KEY = "credential_reprobe_interval_seconds"
_REFUSED_STAGE = "credential-reprobe-refused"
_CLEARED_STAGE = "provider-exhaustion-cleared"
_OBSERVED_STAGE = "provider-exhaustion-observed"
_NOW = "2026-09-08T00:00:00Z"
_UNEXPIRED = "2099-01-01T00:00:00Z"


def _module() -> ModuleType:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _status(*, condition: str, usable: bool) -> ClaudeCredentialStatus:
    return ClaudeCredentialStatus(
        condition=condition,  # pyright: ignore[reportArgumentType]
        present=True,
        usable=usable,
        http_status=429 if condition == "exhausted" else 401,
        error_type="rate_limit_error" if condition == "exhausted" else "authentication_error",
        input_tokens=None,
        output_tokens=None,
        message=f"{_TOKEN_ENV} probe reported {condition}.",
        remedy="Stand-in remedy.",
    )


def _exhausted() -> ClaudeCredentialStatus:
    return _status(condition="exhausted", usable=False)


def _revoked() -> ClaudeCredentialStatus:
    return _status(condition="revoked", usable=False)


def _usable() -> ClaudeCredentialStatus:
    return _status(condition="usable", usable=True)


@dataclass(kw_only=True)
class _Probe:
    """A probe returning each queued status once, then repeating the last."""

    statuses: list[ClaudeCredentialStatus]
    calls: list[str] = field(default_factory=list)

    def __call__(self, *, token: str) -> ClaudeCredentialStatus:
        self.calls.append(token)
        return self.statuses[min(len(self.calls) - 1, len(self.statuses) - 1)]


@dataclass(kw_only=True)
class _Sleeps:
    seconds: list[float] = field(default_factory=list)

    def __call__(self, *, seconds: float) -> None:
        self.seconds.append(seconds)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _write_config(*, repo: Path, value: object) -> None:
    block = {"livespec-orchestrator-beads-fabro": {"dispatcher": {_CONFIG_KEY: value}}}
    _ = repo.joinpath(".livespec.jsonc").write_text(json.dumps(block), encoding="utf-8")


def test_a_provider_limit_refusal_holds_the_loop_open_until_the_first_usable_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reprobe = _module()
    monkeypatch.setenv(_TOKEN_ENV, "stand-in-token")
    _write_config(repo=tmp_path, value=7)
    probe = _Probe(statuses=[_exhausted(), _exhausted(), _usable()])
    sleeps = _Sleeps()
    journal = _RecordingJournal()

    status = reprobe.await_usable_credential(
        repo=tmp_path,
        journal=journal,
        budget=3,
        probe=probe,
        sleeper=sleeps,
    )

    assert status is not None
    assert status.usable is True
    assert len(probe.calls) == 3
    assert sleeps.seconds == [7, 7]
    assert len(journal.records) == 2
    assert [record["stage"] for record in journal.records] == [_REFUSED_STAGE] * 2
    assert [record["refused_probes"] for record in journal.records] == [1, 2]
    assert {record["condition"] for record in journal.records} == {"exhausted"}
    assert {record["reprobe_interval_seconds"] for record in journal.records} == {7}


def test_a_refusal_that_is_not_a_provider_limit_returns_without_waiting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-probing cannot change a revoked token, so the pass is not held open."""
    reprobe = _module()
    monkeypatch.setenv(_TOKEN_ENV, "stand-in-token")
    probe = _Probe(statuses=[_revoked()])
    sleeps = _Sleeps()
    journal = _RecordingJournal()

    status = reprobe.await_usable_credential(
        repo=tmp_path,
        journal=journal,
        budget=3,
        probe=probe,
        sleeper=sleeps,
    )

    assert status is not None
    assert status.condition == "revoked"
    assert len(probe.calls) == 1
    assert sleeps.seconds == []
    assert journal.records == []


def test_a_pass_with_no_budget_to_spend_probes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wait exists to keep an UNSPENT budget alive; zero has none to keep."""
    reprobe = _module()
    monkeypatch.setenv(_TOKEN_ENV, "stand-in-token")
    probe = _Probe(statuses=[_exhausted()])
    sleeps = _Sleeps()
    journal = _RecordingJournal()

    status = reprobe.await_usable_credential(
        repo=tmp_path,
        journal=journal,
        budget=0,
        probe=probe,
        sleeper=sleeps,
    )

    assert status is None
    assert probe.calls == []
    assert sleeps.seconds == []
    assert journal.records == []


def test_the_cadence_defaults_to_300_seconds_and_is_committed_only(tmp_path: Path) -> None:
    """Default 300, and ABSENT from the declared-API-configurable manifest."""
    reprobe = _module()

    assert reprobe.DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS == 300
    assert reprobe.credential_reprobe_interval_seconds(cwd=tmp_path) == 300
    declared = {str(entry["key"]) for entry in api_configurable_key_manifest()["keys"]}
    assert _CONFIG_KEY not in declared
    # The control: the manifest IS the surface a declared key appears on, so an
    # empty or unreachable manifest would satisfy the assertion above for the
    # wrong reason.
    assert "wip_cap" in declared


@pytest.mark.parametrize(
    ("committed", "expected"),
    [
        (600, 600),
        (1, 1),
        (0, 300),
        (-5, 300),
        (True, 300),
        ("600", 300),
        (None, 300),
    ],
)
def test_only_a_committed_positive_integer_moves_the_cadence(
    tmp_path: Path,
    committed: object,
    expected: int,
) -> None:
    reprobe = _module()
    _write_config(repo=tmp_path, value=committed)

    assert reprobe.credential_reprobe_interval_seconds(cwd=tmp_path) == expected


def test_a_usable_probe_does_not_retire_an_unexpired_exhaustion_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wait adds no fourth retirement route to the three ratified ones."""
    reprobe = _module()
    monkeypatch.setenv(_TOKEN_ENV, "stand-in-token")
    journal_path = tmp_path / "fabro-dispatch-journal.jsonl"
    observed = {
        "at": _NOW,
        "stage": _OBSERVED_STAGE,
        "work_item_id": "bd-ib-stand-in",
        "provider": "anthropic",
        "governing_condition": "provider_usage_limit",
        "record_expires_at": _UNEXPIRED,
    }
    _ = journal_path.write_text(json.dumps(observed) + "\n", encoding="utf-8")
    journal = JournalFile(path=journal_path)
    probe = _Probe(statuses=[_exhausted(), _usable()])

    status = reprobe.await_usable_credential(
        repo=tmp_path,
        journal=journal,
        budget=1,
        probe=probe,
        sleeper=_Sleeps(),
    )

    assert status is not None
    assert status.usable is True
    held = dispatch_provider_exhaustion(journal_path=journal_path, now_iso=_NOW)
    assert held is not None
    assert held.provider == "anthropic"
    assert held.record_expires_at == _UNEXPIRED
    written = [
        json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines() if line
    ]
    assert [record["stage"] for record in written] == [_OBSERVED_STAGE, _REFUSED_STAGE]
    assert not any(record["stage"] == _CLEARED_STAGE for record in written)


def test_the_default_sleeper_waits_the_configured_cadence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production wait is a real sleep of the resolved interval."""
    reprobe = _module()
    monkeypatch.setenv(_TOKEN_ENV, "stand-in-token")
    slept: list[float] = []
    monkeypatch.setattr(reprobe.time, "sleep", slept.append)
    probe = _Probe(statuses=[_exhausted(), _usable()])
    journal = _RecordingJournal()

    status = reprobe.await_usable_credential(
        repo=tmp_path,
        journal=journal,
        budget=1,
        probe=probe,
    )

    assert status is not None
    assert status.usable is True
    assert slept == [300]
