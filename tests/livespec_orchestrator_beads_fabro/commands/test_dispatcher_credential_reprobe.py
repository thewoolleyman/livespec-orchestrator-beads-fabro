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

THE ROTATION CASE KEYS ITS PROBE ON THE TOKEN RATHER THAN THE CALL INDEX, which
is the one shape that can fail for the right reason. A probe scripted by call
order returns `usable` on its second call whatever value it was handed, so it
passes identically against a wait that re-reads the wrapper and against the
launch-time-environment wait this slice repairs — the defect being closed is
precisely that the second probe asked about the FIRST credential. Keying on the
token means the wait can only resume by having observed the rotated value, and
the launch-time value is left provider-limited for the whole wait so no other
route to `usable` exists.

THE RECORDED-IDENTITY CASES COME AS A PAIR, and the stale one is what gives the
rotated one meaning. Taken alone, "two rows carry different identities" is
satisfied by anything that varies per row — a timestamp, a counter, a random
value — so the sibling case holds the wrapper's value STILL and asserts the two
rows carry ONE identity. Both are taken with the same probe verdict on every
round, so nothing about the refusal itself can be doing the distinguishing.

THE RETIREMENT-SIGNAL CASES COME AS A PAIR, and both run at a budget of ONE
because that is the budget this fleet actually dispatches with: `_drive_impl_
dispatch` spawns every `drive --action impl:<id>` loop as `loop --budget 1`, so a
bound keyed on the budget retires the wait after a SINGLE round, and the 2026-10-08
incident this slice repairs was four such loops. One case re-resolves the wrapper
on every round and one cannot re-resolve it at all; both are held on the same
provider-limit verdict and both must run to the probe's own `usable` result,
because a provider rate limit clears WITHOUT the credential changing. So an
unresolvable wrapper is not a retirement signal, and neither case may be ended by
anything that is not a probe result. Both use a sleep double that FAILS past a
ceiling rather than letting an unbounded wait hang the suite into a stage timeout.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_policy_settings
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
    ClaudeCredentialStatus,
    ClaudeProbeObservation,
    classify_claude_probe,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_rotation import (
    LAUNCH_ENVIRONMENT_WRAPPER_UNRESOLVABLE,
    WRAPPER_RESOLVED,
    credential_identity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
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
_WRAPPER = ("/usr/local/bin/with-livespec-env.sh", "--")
# Comfortably past every bound any case here expects, so a wait that reaches it
# has failed to terminate rather than merely taken one round more than planned.
_UNBOUNDED_WAIT_CEILING = 12
# The launch-time value stays provider-limited for every wait below, so the only
# route to a usable probe is the wrapper's rotated value.
_STALE_TOKEN = "stale-launch-time-token"
_ROTATED_TOKEN = "rotated-wrapper-token"


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


@dataclass(kw_only=True)
class _Runner:
    """A CommandRunner double standing in for the wrapper re-resolution."""

    results: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(list(argv))
        return self.results[min(len(self.calls) - 1, len(self.results) - 1)]


def _wrapper_printing(*, tokens: list[str]) -> _Runner:
    """A wrapper that injects each token in turn, then repeats the last."""
    return _Runner(
        results=[CommandResult(exit_code=0, stdout=token, stderr="") for token in tokens]
    )


def _misconfigured_wrapper() -> _Runner:
    """A declared wrapper that cannot run — the shape `sudo: command not found` takes."""
    return _Runner(results=[CommandResult(exit_code=127, stdout="", stderr="not found")])


@dataclass(kw_only=True)
class _BoundedSleep:
    """A sleep that FAILS past its ceiling rather than letting the wait hang.

    A wait that does not terminate would otherwise hang the suite until the
    node's own timeout, which reports as a stage timeout rather than as the
    unbounded wait it is. Failing on the ceiling turns the same defect into one
    named assertion.
    """

    ceiling: int
    calls: list[float] = field(default_factory=list)

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        if len(self.calls) > self.ceiling:
            pytest.fail(f"the wait ran {len(self.calls)} rounds without terminating")


def _repo(
    *, tmp_path: Path, cadence: int | None = None, wrapper: tuple[str, ...] | None = None
) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    config: dict[str, Any] = {}
    if cadence is not None:
        config["livespec-orchestrator-beads-fabro"] = {"dispatcher": {_CADENCE_KEY: cadence}}
    if wrapper is not None:
        config["credential_wrapper"] = list(wrapper)
    if config:
        _ = (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    return repo


def _journal(*, repo: Path) -> JournalFile:
    return JournalFile(path=repo / "journal.jsonl")


def _records(*, journal: JournalFile) -> list[dict[str, Any]]:
    if not journal.path.is_file():
        return []
    return [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]


def _refusals(*, journal: JournalFile, reprobe: Any) -> list[dict[str, Any]]:
    return [
        record
        for record in _records(journal=journal)
        if record["stage"] == reprobe.CREDENTIAL_REPROBE_STAGE
    ]


def _token_keyed_probe(*, usable_token: str, probed: list[str]) -> Any:
    """A probe whose verdict follows the TOKEN it was handed (see the docstring)."""

    def probe(*, token: str) -> ClaudeCredentialStatus:
        probed.append(token)
        return _status(
            condition="usable" if token == usable_token else "exhausted",
            usable=token == usable_token,
        )

    return probe


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


def test_a_rotation_in_the_wrapper_retires_a_parked_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect this slice repairs: a rotation reaches the wait un-restarted.

    `os.environ` keeps the stale value for the whole wait, exactly as a parked
    loop's process does, so the resumption can only have come from the wrapper.
    """
    reprobe = _reprobe()
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _STALE_TOKEN)
    repo = _repo(tmp_path=tmp_path, cadence=11, wrapper=_WRAPPER)
    journal = _journal(repo=repo)
    probed: list[str] = []
    runner = _wrapper_printing(tokens=[_STALE_TOKEN, _ROTATED_TOKEN])
    slept: list[float] = []

    reprobe.await_usable_credential(
        repo=repo,
        journal=journal,
        budget=2,
        probe=_token_keyed_probe(usable_token=_ROTATED_TOKEN, probed=probed),
        sleep=slept.append,
        runner=runner,
    )

    assert probed == [_STALE_TOKEN, _ROTATED_TOKEN]
    assert slept == [11]
    assert runner.calls == [[*_WRAPPER, "printenv", CLAUDE_OAUTH_TOKEN_ENV]] * 2
    refused = _refusals(journal=journal, reprobe=reprobe)
    assert len(refused) == 1
    assert refused[0]["credential_source"] == WRAPPER_RESOLVED


def test_two_consecutive_rows_show_a_rotation_by_their_recorded_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each refused row names the credential it probed, and the names differ.

    The two rows are taken with the SAME probe verdict, so nothing about the
    refusal itself distinguishes them: the recorded identity is the only thing
    that says a rotation reached the wait between them.
    """
    reprobe = _reprobe()
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _STALE_TOKEN)
    repo = _repo(tmp_path=tmp_path, cadence=3, wrapper=_WRAPPER)
    journal = _journal(repo=repo)
    probe = _Probe(
        statuses=[
            _status(condition="exhausted", usable=False),
            _status(condition="exhausted", usable=False),
            _status(condition="usable", usable=True),
        ]
    )

    reprobe.await_usable_credential(
        repo=repo,
        journal=journal,
        budget=3,
        probe=probe,
        sleep=lambda _seconds: None,
        runner=_wrapper_printing(tokens=[_STALE_TOKEN, _ROTATED_TOKEN]),
    )

    rows = _refusals(journal=journal, reprobe=reprobe)
    assert [row for row in rows if "credential_identity" in row] == rows
    identities = [row["credential_identity"] for row in rows]
    assert identities == [
        credential_identity(token=_STALE_TOKEN),
        credential_identity(token=_ROTATED_TOKEN),
    ]
    assert identities[0] != identities[1]
    assert _STALE_TOKEN not in json.dumps(_records(journal=journal))
    assert _ROTATED_TOKEN not in json.dumps(_records(journal=journal))


def test_two_consecutive_rows_show_a_stale_credential_by_one_repeated_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other direction, and the one the incident needed: an unchanged value.

    Without this case a recorded identity could be anything that varies per row
    — a timestamp, a counter — and the rotation case above would still pass.
    """
    reprobe = _reprobe()
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _STALE_TOKEN)
    repo = _repo(tmp_path=tmp_path, cadence=3, wrapper=_WRAPPER)
    journal = _journal(repo=repo)
    probe = _Probe(
        statuses=[
            _status(condition="exhausted", usable=False),
            _status(condition="exhausted", usable=False),
            _status(condition="usable", usable=True),
        ]
    )

    reprobe.await_usable_credential(
        repo=repo,
        journal=journal,
        budget=3,
        probe=probe,
        sleep=lambda _seconds: None,
        runner=_wrapper_printing(tokens=[_STALE_TOKEN]),
    )

    rows = _refusals(journal=journal, reprobe=reprobe)
    assert [row for row in rows if "credential_identity" in row] == rows
    assert [row["credential_identity"] for row in rows] == [
        credential_identity(token=_STALE_TOKEN)
    ] * 2


def test_the_bounded_sleep_guard_fails_once_past_its_ceiling() -> None:
    """The HARNESS guard, proved to fire — a guard that cannot fire proves nothing.

    The two cases below pass if the wait terminates, and they also pass if this
    guard never fires for any reason: a ceiling it can never reach, a counter
    that does not increment, a `pytest.fail` the double stopped calling. So the
    guard is exercised directly, exactly as a mutation has to be shown to land
    before a surviving-mutant reading means anything.
    """
    sleeps = _BoundedSleep(ceiling=1)

    sleeps(5)

    assert sleeps.calls == [5]
    with pytest.raises(pytest.fail.Exception, match="2 rounds without terminating"):
        sleeps(5)


def test_an_unresolvable_wrapper_still_waits_for_the_probes_own_next_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ratified clause, at the ONE budget this fleet dispatches with.

    The declared wrapper cannot run, so every round falls back to the same
    launch-time value. That makes the wait unable to observe a ROTATION — and
    a rotation is not the only thing that retires it: the condition this wait
    governs is a provider rate limit, which clears on its own with the
    credential unchanged. So `contracts.md` section "Provider spend
    containment" governs unchanged — the loop "MUST NOT exit on that refusal
    while its `--budget` is unspent", and "the probe's OWN next result is the
    retirement signal for the loop's wait, not a clock".

    The budget is ONE because that is what `_drive_impl_dispatch` passes on
    the fleet's primary path, so a bound keyed on it would end this wait after
    a single round — and a transient `sudo` or network fault in the wrapper
    would cost a whole drain. Here the wait runs three refused rounds against
    an unresolvable wrapper and resumes only when the probe says usable.
    """
    reprobe = _reprobe()
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _STALE_TOKEN)
    repo = _repo(tmp_path=tmp_path, cadence=2, wrapper=_WRAPPER)
    journal = _journal(repo=repo)
    probe = _Probe(
        statuses=[
            _status(condition="exhausted", usable=False),
            _status(condition="exhausted", usable=False),
            _status(condition="exhausted", usable=False),
            _status(condition="usable", usable=True),
        ]
    )
    sleeps = _BoundedSleep(ceiling=_UNBOUNDED_WAIT_CEILING)

    reprobe.await_usable_credential(
        repo=repo,
        journal=journal,
        budget=1,
        probe=probe,
        sleep=sleeps,
        runner=_misconfigured_wrapper(),
    )

    assert sleeps.calls == [2, 2, 2]
    assert probe.calls == 4
    rows = _refusals(journal=journal, reprobe=reprobe)
    assert len(rows) == 3
    assert {row["credential_source"] for row in rows} == {LAUNCH_ENVIRONMENT_WRAPPER_UNRESOLVABLE}


def test_a_working_wrapper_is_retired_by_the_same_one_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sibling: the same budget, the same verdicts, a wrapper that resolves.

    The pair is what says the retirement signal is the PROBE and nothing else.
    Taken alone, the case above is satisfied by an implementation that keys its
    bound on a re-resolution it happens to get right; taken together, the two
    differ only in whether the wrapper could be read, and neither wait ends
    before the probe itself reports the credential usable.
    """
    reprobe = _reprobe()
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _STALE_TOKEN)
    repo = _repo(tmp_path=tmp_path, cadence=2, wrapper=_WRAPPER)
    journal = _journal(repo=repo)
    probe = _Probe(
        statuses=[
            _status(condition="exhausted", usable=False),
            _status(condition="exhausted", usable=False),
            _status(condition="exhausted", usable=False),
            _status(condition="usable", usable=True),
        ]
    )
    sleeps = _BoundedSleep(ceiling=_UNBOUNDED_WAIT_CEILING)

    reprobe.await_usable_credential(
        repo=repo,
        journal=journal,
        budget=1,
        probe=probe,
        sleep=sleeps,
        runner=_wrapper_printing(tokens=[_STALE_TOKEN]),
    )

    assert probe.calls == 4
    assert sleeps.calls == [2, 2, 2]
    assert len(_refusals(journal=journal, reprobe=reprobe)) == 3


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
    """The wait adds no retirement route; the record outlives the resumed loop.

    The usable probe is asserted to have been REACHED, because this repository
    declares no wrapper in the fixture and the reading therefore falls back to
    the launch environment on every round: a bound keyed on rounds that could
    not re-resolve would end this wait at the first refusal, and the record
    would then survive a resumption that never happened.
    """
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

    assert probe.calls == 2
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
