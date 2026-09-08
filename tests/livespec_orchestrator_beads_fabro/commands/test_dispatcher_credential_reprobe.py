"""The loop's bounded credential re-probe, and the clock it refuses to obey.

Covers the ratified clauses "The admission-time credential-probe refusal
re-probes rather than exiting" and "The probe refusal's remedy carries no timing
claim as an instruction" in `SPECIFICATION/contracts.md` section "Provider spend
containment".

The new module is reached through `importlib` inside each test body rather than
by a module-level import, so the Red commit of this slice fails on a genuine
assertion (`module_path.is_file()`) instead of dying at collection on a
`ModuleNotFoundError`, which would prove only that the module is missing.

Two controls carry this module and neither is decoration. The
condition-it-does-not-govern case is what separates "the wait engages on a
rate limit" from "the wait engages on any refusal" — a gate that waited on an
absent credential would hang a misconfigured wrapper forever, and every
positive case here would pass just as well against it. And the
exhaustion-record case asserts the record SURVIVES a usable probe, because the
clause's whole point is that this wait adds no retirement route: an
implementation that helpfully cleared the record would satisfy "the loop
resumed" perfectly and quietly delete a containment fact.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_policy_settings
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    ClaudeCredentialStatus,
    ClaudeProbeObservation,
    classify_claude_probe,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    dispatch_provider_exhaustion,
)
from livespec_orchestrator_beads_fabro.commands._drive_config_schema import (
    api_configurable_key_manifest,
    config_key_by_name,
)
from returns.unsafe import unsafe_perform_io

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_reprobe"
_CADENCE_KEY = "credential_reprobe_interval_seconds"
_RATE_LIMITED = ClaudeProbeObservation(
    http_status=429, error_type="rate_limit_error", input_tokens=None, output_tokens=None
)


def _reprobe() -> Any:
    """The module under test, imported inside the body (see the module docstring)."""
    return importlib.import_module(_MODULE)


def _status(*, condition: str, usable: bool) -> ClaudeCredentialStatus:
    return ClaudeCredentialStatus(
        condition=condition,  # pyright: ignore[reportArgumentType]
        present=True,
        usable=usable,
        http_status=429 if condition == "exhausted" else 200,
        error_type="rate_limit_error" if condition == "exhausted" else None,
        input_tokens=None,
        output_tokens=None,
        message="probe stand-in",
        remedy="probe stand-in",
    )


class _Probe:
    """A probe returning one scripted status per call, then repeating the last."""

    def __init__(self, *, statuses: list[ClaudeCredentialStatus]) -> None:
        self.statuses = statuses
        self.calls = 0

    def __call__(self, *, token: str) -> ClaudeCredentialStatus:
        _ = token
        index = min(self.calls, len(self.statuses) - 1)
        self.calls += 1
        return self.statuses[index]


def _repo(*, tmp_path: Path, cadence: int | None = None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    if cadence is not None:
        _ = (repo / ".livespec.jsonc").write_text(
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": '
            f'{{"{_CADENCE_KEY}": {cadence}}}}}}}',
            encoding="utf-8",
        )
    return repo


def _journal(*, repo: Path) -> JournalFile:
    return JournalFile(path=repo / "journal.jsonl")


def _records(*, journal: JournalFile) -> list[dict[str, Any]]:
    import json

    if not journal.path.is_file():
        return []
    return [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(autouse=True)
def _present_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    """A present token, so the assessment reaches the injected probe."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")


def test_the_module_exists_and_publishes_the_wait(tmp_path: Path) -> None:
    """The Red assertion of this slice: the module file itself."""
    module_path = (
        Path(_dispatcher_policy_settings.__file__).parent / "_dispatcher_credential_reprobe.py"
    )

    assert module_path.is_file()
    reprobe = _reprobe()
    assert set(reprobe.__all__) == {
        "CREDENTIAL_REPROBE_STAGE",
        "PROVIDER_LIMIT_CONDITION",
        "await_usable_credential",
    }
    assert reprobe.PROVIDER_LIMIT_CONDITION == "exhausted"
    assert _repo(tmp_path=tmp_path).is_dir()


def test_a_refused_probe_waits_and_resumes_on_the_first_usable_result(tmp_path: Path) -> None:
    """It does not exit: two refusals are journaled, then admission resumes."""
    reprobe = _reprobe()
    repo = _repo(tmp_path=tmp_path, cadence=7)
    journal = _journal(repo=repo)
    probe = _Probe(
        statuses=[
            _status(condition="exhausted", usable=False),
            _status(condition="exhausted", usable=False),
            _status(condition="usable", usable=True),
        ]
    )
    slept: list[float] = []

    result = reprobe.await_usable_credential(
        repo=repo, journal=journal, budget=3, probe=probe, sleep=slept.append
    )

    assert result is None
    assert probe.calls == 3
    assert slept == [7, 7]
    refused = [
        record
        for record in _records(journal=journal)
        if record["stage"] == reprobe.CREDENTIAL_REPROBE_STAGE
    ]
    assert len(refused) == 2
    assert refused[0]["condition"] == "exhausted"
    assert refused[0]["http_status"] == 429
    assert refused[0]["error_type"] == "rate_limit_error"
    assert refused[0]["reprobe_interval_seconds"] == 7


def test_the_default_cadence_is_three_hundred_seconds(tmp_path: Path) -> None:
    """No committed key, so the ratified default is what the wait sleeps."""
    reprobe = _reprobe()
    repo = _repo(tmp_path=tmp_path)
    slept: list[float] = []
    probe = _Probe(
        statuses=[
            _status(condition="exhausted", usable=False),
            _status(condition="usable", usable=True),
        ]
    )

    reprobe.await_usable_credential(
        repo=repo, journal=_journal(repo=repo), budget=1, probe=probe, sleep=slept.append
    )

    assert slept == [300]
    assert _dispatcher_policy_settings.DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS == 300


def test_the_cadence_read_reports_the_default_and_the_committed_value(tmp_path: Path) -> None:
    """The dial itself: absent is an answer, a committed positive integer wins."""
    resolve = _dispatcher_policy_settings.resolve_credential_reprobe_interval_seconds

    assert unsafe_perform_io(resolve(cwd=_repo(tmp_path=tmp_path)).unwrap()) == 300
    assert unsafe_perform_io(resolve(cwd=_repo(tmp_path=tmp_path, cadence=45)).unwrap()) == 45


def test_an_unreadable_cadence_falls_back_to_the_default(tmp_path: Path) -> None:
    """An unparseable config is a FAILURE, and the wait still has a cadence."""
    reprobe = _reprobe()
    repo = tmp_path / "broken"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text("{ not json", encoding="utf-8")
    resolve = _dispatcher_policy_settings.resolve_credential_reprobe_interval_seconds
    slept: list[float] = []
    probe = _Probe(
        statuses=[
            _status(condition="exhausted", usable=False),
            _status(condition="usable", usable=True),
        ]
    )

    reprobe.await_usable_credential(
        repo=repo, journal=_journal(repo=repo), budget=1, probe=probe, sleep=slept.append
    )

    assert resolve(cwd=repo).failure() is not None
    assert slept == [300]


def test_the_cadence_is_committed_only_and_not_api_configurable() -> None:
    """It is absent from the manifest, which is the mechanism, not a note."""
    assert config_key_by_name(key=_CADENCE_KEY) is None
    manifest_keys = {entry["key"] for entry in api_configurable_key_manifest()["keys"]}
    assert _CADENCE_KEY not in manifest_keys
    assert "ready_aging_threshold_hours" in manifest_keys


def test_a_condition_the_wait_does_not_govern_returns_at_once(tmp_path: Path) -> None:
    """The control: a revoked credential is a fault waiting cannot repair."""
    reprobe = _reprobe()
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    probe = _Probe(statuses=[_status(condition="revoked", usable=False)])
    slept: list[float] = []

    reprobe.await_usable_credential(
        repo=repo, journal=journal, budget=3, probe=probe, sleep=slept.append
    )

    assert probe.calls == 1
    assert slept == []
    assert _records(journal=journal) == []


def test_a_spent_budget_never_enters_the_wait(tmp_path: Path) -> None:
    """Nothing to dispatch is nothing to wait for, so no probe is even run."""
    reprobe = _reprobe()
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    probe = _Probe(statuses=[_status(condition="exhausted", usable=False)])
    slept: list[float] = []

    reprobe.await_usable_credential(
        repo=repo, journal=journal, budget=0, probe=probe, sleep=slept.append
    )

    assert probe.calls == 0
    assert slept == []
    assert _records(journal=journal) == []


def test_a_usable_probe_does_not_retire_an_unexpired_exhaustion_record(tmp_path: Path) -> None:
    """The wait adds no retirement route; the record outlives the resumed loop."""
    reprobe = _reprobe()
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    journal.append(
        record={
            "stage": "provider-exhaustion-observed",
            "work_item_id": "bd-ib-held",
            "provider": "anthropic",
            "governing_condition": "provider_usage_limit",
            "record_expires_at": "2099-01-01T00:00:00Z",
        }
    )
    probe = _Probe(
        statuses=[
            _status(condition="exhausted", usable=False),
            _status(condition="usable", usable=True),
        ]
    )

    reprobe.await_usable_credential(
        repo=repo, journal=journal, budget=1, probe=probe, sleep=lambda _seconds: None
    )

    held = dispatch_provider_exhaustion(journal_path=journal.path, now_iso="2026-09-08T00:00:00Z")
    assert held is not None
    assert held.provider == "anthropic"
    stages = {record["stage"] for record in _records(journal=journal)}
    assert "provider-exhaustion-cleared" not in stages


def test_the_provider_limit_remedy_states_the_reprobe_and_no_clock() -> None:
    """The remedy names the cadence dial and forbids the wait-until-clock reading."""
    status = classify_claude_probe(observation=_RATE_LIMITED)

    assert status.condition == "exhausted"
    assert _CADENCE_KEY in status.remedy
    assert "unverified provider claim" in status.remedy
    assert "never an instruction" in status.remedy
    assert "wait before retrying" not in status.remedy
