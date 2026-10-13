"""Re-resolving the dispatch credential through the wrapper, round by round.

Covers the fix for the defect measured 2026-10-08 on this host: four dispatch
loops parked on `credential-reprobe-refused` kept journaling `exhausted` for
more than twenty minutes after the Claude credential had been rotated, because
every probe re-read the value the wrapper had injected when the loop LAUNCHED.

The new module is reached through `importlib` inside each test body rather than
by a module-level import, so the Red commit of this slice fails on a genuine
assertion (`module_path.is_file()`) instead of dying at collection on a
`ModuleNotFoundError`, which would prove only that the module is missing.

Two controls carry this file and neither is decoration. The rotation case
asserts the refreshed value lands in the PROCESS ENVIRONMENT and not merely in
the probe, because `_dispatcher_credentials` renders the sandbox overlay from
`os.environ[<credential name>]` — a rotation that reached only the probe would
resume admission and then project the dead value into the run the resume was
for. And the unreadable-wrapper cases assert the launch-time value SURVIVES,
because every positive case here would pass just as well against an
implementation that cleared the environment whenever the wrapper misbehaved —
which would turn one stalled secret-backend call into a credential-less
dispatch.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_policy_settings
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
    ClaudeCredentialStatus,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_refresh"
_REPROBE = "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_reprobe"
_WRAPPER = ("/usr/local/bin/with-livespec-env.sh", "--")
_FINGERPRINT_DOMAIN = "livespec-dispatch-credential/v1"
_FINGERPRINT_HEX_LENGTH = 32
_DEAD = "dead-token"
_ROTATED = "rotated-token"


def _refresh() -> Any:
    """The module under test, imported inside the body (see the module docstring)."""
    return importlib.import_module(_MODULE)


def _reprobe() -> Any:
    """The wait that consumes the refresh, imported the same way for the same reason."""
    return importlib.import_module(_REPROBE)


def _status(*, usable: bool) -> ClaudeCredentialStatus:
    return ClaudeCredentialStatus(
        condition="usable" if usable else "exhausted",
        present=True,
        usable=usable,
        http_status=200 if usable else 429,
        error_type=None if usable else "rate_limit_error",
        input_tokens=None,
        output_tokens=None,
        message="probe stand-in",
        remedy="probe stand-in",
    )


class _TokenProbe:
    """A probe that classifies by the token it is HANDED, not by call order.

    Call-order scripting cannot tell "the probe saw the rotated value" from
    "the probe was called a third time", which is the whole question here.
    """

    def __init__(self, *, usable: frozenset[str]) -> None:
        self.usable = usable
        self.tokens: list[str] = []

    def __call__(self, *, token: str) -> ClaudeCredentialStatus:
        self.tokens.append(token)
        return _status(usable=token in self.usable)


class _WrapperRunner:
    """A `CommandRunner` stand-in: one scripted read-back per call, last repeating."""

    def __init__(self, *, results: list[tuple[int, str]]) -> None:
        self.results = results
        self.argvs: list[list[str]] = []
        self.timeouts: list[float] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, env, stdin)
        self.argvs.append(argv)
        self.timeouts.append(timeout_seconds)
        exit_code, stdout = self.results[min(len(self.argvs) - 1, len(self.results) - 1)]
        return CommandResult(exit_code=exit_code, stdout=stdout, stderr="")


def _repo(*, tmp_path: Path, wrapper: tuple[str, ...] | None, cadence: int = 5) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    config: dict[str, Any] = {
        "livespec-orchestrator-beads-fabro": {
            "dispatcher": {"credential_reprobe_interval_seconds": cadence}
        }
    }
    if wrapper is not None:
        config["credential_wrapper"] = list(wrapper)
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    return repo


def _records(*, journal: JournalFile) -> list[dict[str, Any]]:
    if not journal.path.is_file():
        return []
    return [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(autouse=True)
def _hermetic_host(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A home with no caam selection record, and a present launch-time token."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _DEAD)


def test_the_module_exists_and_publishes_the_refresh(tmp_path: Path) -> None:
    """The Red assertion of this slice: the module file itself."""
    module_path = (
        Path(_dispatcher_policy_settings.__file__).parent / "_dispatcher_credential_refresh.py"
    )

    assert module_path.is_file()
    refresh = _refresh()
    assert set(refresh.__all__) == {
        "CREDENTIAL_REFRESH_TIMEOUT_SECONDS",
        "LAUNCH_ENVIRONMENT_SOURCE",
        "WRAPPER_SOURCE",
        "CredentialRefresh",
        "credential_refresh_argv",
        "fingerprint_credential",
        "refresh_host_credential",
    }
    assert refresh.WRAPPER_SOURCE == "wrapper"
    assert refresh.LAUNCH_ENVIRONMENT_SOURCE == "launch-environment"
    assert _repo(tmp_path=tmp_path, wrapper=_WRAPPER).is_dir()


def test_a_rotated_credential_reaches_the_next_probe_and_the_environment(tmp_path: Path) -> None:
    """The parked loop resumes on the ROTATED value, without being restarted."""
    reprobe = _reprobe()
    repo = _repo(tmp_path=tmp_path, wrapper=_WRAPPER)
    journal = JournalFile(path=repo / "journal.jsonl")
    probe = _TokenProbe(usable=frozenset({_ROTATED}))
    runner = _WrapperRunner(results=[(0, f"{_DEAD}\n"), (0, f"{_ROTATED}\n")])
    slept: list[float] = []

    reprobe.await_usable_credential(
        repo=repo,
        journal=journal,
        budget=3,
        probe=probe,
        sleep=slept.append,
        runner=runner,
    )

    assert probe.tokens == [_DEAD, _ROTATED]
    assert os.environ[CLAUDE_OAUTH_TOKEN_ENV] == _ROTATED
    assert slept == [5]
    assert runner.argvs == [
        [*_WRAPPER, "printenv", CLAUDE_OAUTH_TOKEN_ENV],
        [*_WRAPPER, "printenv", CLAUDE_OAUTH_TOKEN_ENV],
    ]
    assert len(_records(journal=journal)) == 1


def test_no_declared_wrapper_leaves_the_launch_value_standing(tmp_path: Path) -> None:
    """No wrapper is no command to run, so nothing is re-resolved and nothing changes."""
    refresh = _refresh()
    runner = _WrapperRunner(results=[(0, f"{_ROTATED}\n")])

    outcome = refresh.refresh_host_credential(
        repo=_repo(tmp_path=tmp_path, wrapper=None), environ=os.environ, runner=runner
    )

    assert runner.argvs == []
    assert outcome.env_name == CLAUDE_OAUTH_TOKEN_ENV
    assert outcome.source == refresh.LAUNCH_ENVIRONMENT_SOURCE
    assert outcome.fingerprint == refresh.fingerprint_credential(value=_DEAD)
    assert os.environ[CLAUDE_OAUTH_TOKEN_ENV] == _DEAD
    assert refresh.credential_refresh_argv(wrapper=(), env_name=CLAUDE_OAUTH_TOKEN_ENV) is None


@pytest.mark.parametrize(
    ("exit_code", "stdout"),
    [(127, ""), (124, ""), (1, "boom"), (0, "   \n")],
    ids=["absent-wrapper", "timed-out", "non-zero", "printed-nothing"],
)
def test_an_unreadable_wrapper_read_leaves_the_launch_value_standing(
    tmp_path: Path, exit_code: int, stdout: str
) -> None:
    """Every unreadable arm degrades to the pre-existing behaviour, never to no credential."""
    refresh = _refresh()
    runner = _WrapperRunner(results=[(exit_code, stdout)])

    outcome = refresh.refresh_host_credential(
        repo=_repo(tmp_path=tmp_path, wrapper=_WRAPPER), environ=os.environ, runner=runner
    )

    assert len(runner.argvs) == 1
    assert outcome.source == refresh.LAUNCH_ENVIRONMENT_SOURCE
    assert outcome.fingerprint == refresh.fingerprint_credential(value=_DEAD)
    assert os.environ[CLAUDE_OAUTH_TOKEN_ENV] == _DEAD


def test_an_absent_credential_has_no_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No value in hand is a different fact from a read that failed over a present one."""
    refresh = _refresh()
    monkeypatch.delenv(CLAUDE_OAUTH_TOKEN_ENV)

    outcome = refresh.refresh_host_credential(
        repo=_repo(tmp_path=tmp_path, wrapper=None),
        environ=os.environ,
        runner=_WrapperRunner(results=[(0, "")]),
    )

    assert outcome.source == refresh.LAUNCH_ENVIRONMENT_SOURCE
    assert outcome.fingerprint is None


def test_the_fingerprint_is_a_truncated_domain_separated_digest() -> None:
    """A one-way digest answers "did the value change", and nothing else."""
    refresh = _refresh()
    expected = hashlib.sha256(f"{_FINGERPRINT_DOMAIN}:{_DEAD}".encode()).hexdigest()[
        :_FINGERPRINT_HEX_LENGTH
    ]

    fingerprint = refresh.fingerprint_credential(value=_DEAD)

    assert fingerprint == expected
    assert len(fingerprint) == _FINGERPRINT_HEX_LENGTH
    assert _DEAD not in fingerprint
    assert fingerprint != refresh.fingerprint_credential(value=_ROTATED)


def test_the_wrapper_read_is_bounded(tmp_path: Path) -> None:
    """An unbounded read is how one stalled secret-backend call wedges the loop."""
    refresh = _refresh()
    runner = _WrapperRunner(results=[(0, f"{_ROTATED}\n")])

    outcome = refresh.refresh_host_credential(
        repo=_repo(tmp_path=tmp_path, wrapper=_WRAPPER), environ=os.environ, runner=runner
    )

    assert runner.timeouts == [refresh.CREDENTIAL_REFRESH_TIMEOUT_SECONDS]
    assert refresh.CREDENTIAL_REFRESH_TIMEOUT_SECONDS > 0
    assert outcome.source == refresh.WRAPPER_SOURCE
