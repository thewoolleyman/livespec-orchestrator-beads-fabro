"""Re-resolving the projected worker credential through the configured wrapper.

The seam behind the Definition-of-Done assertion "a dispatch loop parked on
credential-reprobe-refused resumes admission on its next probe after the Claude
credential is rotated in the configured wrapper, without being restarted". The
wait itself is covered by `test_dispatcher_credential_reprobe`; this module
covers the one thing that makes a rotation OBSERVABLE to it.

The new module is reached through `importlib` inside each test body rather than
by a module-level import, so the Red commit of this slice fails on a genuine
assertion (`module_path.is_file()`) instead of dying at collection on a
`ModuleNotFoundError`, which would prove only that the module is missing.

TWO ASSERTIONS HERE ARE LOAD-BEARING RATHER THAN DECORATION, and both are about
the QUERY rather than the answer. The argv is asserted element by element,
because a runner double answers whatever it is asked and cannot tell a correct
invocation from a plausible one — a re-resolution that asked the wrapper for the
wrong variable name would return a perfectly well-formed `None` and read as a
wrapper that is simply not injecting. And the child environment is asserted to
carry the credential name EMPTIED, because the 1Password wrapper this fleet runs
stores the DIFF between its caller's environment and what it injected: a nested
caller that already holds the value produces a near-empty diff, which both hides
the rotation from this reading and poisons the host-wide wrapper cache for every
other caller (`AGENTS.md`, the wrapper-cache entry, measured 2026-10-01).
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands import _dispatcher_policy_settings
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_rotation"
_MODULE_FILE = "_dispatcher_credential_rotation.py"
_WRAPPER = ("/usr/local/bin/with-livespec-env.sh", "--")
_LAUNCH_TOKEN = "launch-time-token"
_ROTATED_TOKEN = "rotated-token"


def _rotation() -> Any:
    """The module under test, imported inside the body (see the module docstring)."""
    module_path = Path(_dispatcher_policy_settings.__file__).parent / _MODULE_FILE

    assert module_path.is_file()
    return importlib.import_module(_MODULE)


@dataclass(kw_only=True)
class _Runner:
    """A CommandRunner double returning one scripted result per call."""

    results: list[CommandResult]
    calls: list[dict[str, object]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        self.calls.append(
            {
                "argv": list(argv),
                "cwd": cwd,
                "timeout_seconds": timeout_seconds,
                "env": env,
                "stdin": stdin,
            }
        )
        return self.results[min(len(self.calls) - 1, len(self.results) - 1)]


def _repo(*, tmp_path: Path, wrapper: tuple[str, ...] | None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    if wrapper is not None:
        tokens = ", ".join(f'"{part}"' for part in wrapper)
        _ = (repo / ".livespec.jsonc").write_text(
            f'{{"credential_wrapper": [{tokens}]}}', encoding="utf-8"
        )
    return repo


def _resolved(
    *, tmp_path: Path, runner: _Runner, wrapper: tuple[str, ...] | None = _WRAPPER
) -> Any:
    rotation = _rotation()
    return rotation.resolve_rotated_credential(
        repo=_repo(tmp_path=tmp_path, wrapper=wrapper),
        env_name=CLAUDE_OAUTH_TOKEN_ENV,
        launch_token=_LAUNCH_TOKEN,
        runner=runner,
    )


def test_the_module_exists_and_publishes_the_rotation_seam() -> None:
    """The Red assertion of this slice: the module file itself."""
    rotation = _rotation()

    assert set(rotation.__all__) == {
        "CREDENTIAL_ROTATION_TIMEOUT_SECONDS",
        "LAUNCH_ENVIRONMENT_NO_WRAPPER",
        "LAUNCH_ENVIRONMENT_WRAPPER_UNRESOLVABLE",
        "RotatedCredential",
        "WRAPPER_RESOLVED",
        "credential_identity",
        "resolve_rotated_credential",
    }
    assert rotation.CREDENTIAL_ROTATION_TIMEOUT_SECONDS > 0


def test_a_declared_wrapper_is_asked_for_the_projected_name(tmp_path: Path) -> None:
    """The rotated value wins over the launch-time one, and the QUERY is exact."""
    rotation = _rotation()
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=f"{_ROTATED_TOKEN}\n", stderr="")])

    resolved = _resolved(tmp_path=tmp_path, runner=runner)

    assert resolved.token == _ROTATED_TOKEN
    assert resolved.rotatable is True
    assert resolved.source == rotation.WRAPPER_RESOLVED
    assert len(runner.calls) == 1
    assert runner.calls[0]["argv"] == [*_WRAPPER, "printenv", CLAUDE_OAUTH_TOKEN_ENV]
    assert runner.calls[0]["timeout_seconds"] == rotation.CREDENTIAL_ROTATION_TIMEOUT_SECONDS
    # The inherited value is EMPTIED for the child, so the wrapper's own diff is
    # genuine rather than near-empty (see the module docstring).
    assert runner.calls[0]["env"] == {CLAUDE_OAUTH_TOKEN_ENV: ""}


def test_no_declared_wrapper_resolves_the_launch_value_and_spawns_nothing(
    tmp_path: Path,
) -> None:
    """A repository declaring no wrapper has no rotation to observe."""
    rotation = _rotation()
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_ROTATED_TOKEN, stderr="")])

    resolved = _resolved(tmp_path=tmp_path, runner=runner, wrapper=None)

    assert resolved.token == _LAUNCH_TOKEN
    assert resolved.rotatable is False
    assert resolved.source == rotation.LAUNCH_ENVIRONMENT_NO_WRAPPER
    assert runner.calls == []


def test_a_wrapper_that_refuses_falls_back_to_the_launch_value(tmp_path: Path) -> None:
    """A non-zero wrapper exit is an unresolvable reading, never an empty credential.

    Falling back rather than reporting absence is what keeps a transient wrapper
    fault from being reported as a revoked credential — the two have opposite
    remedies, and the wait's own bound is what stops a persistent fault.
    """
    rotation = _rotation()
    runner = _Runner(results=[CommandResult(exit_code=1, stdout="", stderr="sudo: not found")])

    resolved = _resolved(tmp_path=tmp_path, runner=runner)

    assert resolved.token == _LAUNCH_TOKEN
    assert resolved.rotatable is False
    assert resolved.source == rotation.LAUNCH_ENVIRONMENT_WRAPPER_UNRESOLVABLE


def test_a_wrapper_printing_nothing_is_also_unresolvable(tmp_path: Path) -> None:
    """Exit 0 with no value injected is a wrapper that did not inject anything."""
    rotation = _rotation()
    runner = _Runner(results=[CommandResult(exit_code=0, stdout="\n", stderr="")])

    resolved = _resolved(tmp_path=tmp_path, runner=runner)

    assert resolved.token == _LAUNCH_TOKEN
    assert resolved.rotatable is False
    assert resolved.source == rotation.LAUNCH_ENVIRONMENT_WRAPPER_UNRESOLVABLE


def test_the_identity_is_one_way_and_separates_two_values() -> None:
    """The journal's non-secret identity: equal for one value, different across two."""
    rotation = _rotation()

    identity = rotation.credential_identity(token=_ROTATED_TOKEN)

    assert identity == rotation.credential_identity(token=_ROTATED_TOKEN)
    assert identity != rotation.credential_identity(token=_LAUNCH_TOKEN)
    assert _ROTATED_TOKEN not in identity
    assert rotation.credential_identity(token="") is None
