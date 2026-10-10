"""The two scrub arms a healthy dispatch cannot reach, kept because of their cost.

Neither case below should occur in production: every projection skips a
credential whose value is absent, and the three required ones are verified
non-empty before the overlay is rendered at all. They are implemented and
asserted anyway, because both fail in the direction that puts credential
material -- or an unreadable message where credential material should have been
reported -- into a dispatch journal row, and a journal row cannot be edited
afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    VaultSecret,
    vault_secret_name,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_vault import FabroVaultSink

_KEY = vault_secret_name(env_name="GITHUB_TOKEN")


@dataclass(kw_only=True)
class _FailingRunner:
    """A runner that fails, reporting on whichever stream it was configured with."""

    stdout: str = ""
    stderr: str = ""
    stdins: list[int | None] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = argv, cwd, timeout_seconds, env
        self.stdins.append(stdin)
        return CommandResult(exit_code=2, stdout=self.stdout, stderr=self.stderr)


def _sink(*, runner: _FailingRunner) -> FabroVaultSink:
    return FabroVaultSink(
        fabro_bin="/usr/local/bin/fabro",
        server_url=None,
        runner=runner,
        cwd=Path("/workspace/repo"),
    )


def test_a_server_reporting_on_stdout_is_still_quoted_back() -> None:
    """The reason is read from whichever stream carried it, not from stderr alone.

    A refusal that reported nothing because the server wrote to stdout would
    send an operator looking for a cause that was there all along.
    """
    runner = _FailingRunner(stdout="vault is read-only")
    message = cast("str", _sink(runner=runner).set(secret=_pass_through_secret()))
    assert "vault is read-only" in message
    assert _KEY in message


def test_an_empty_value_leaves_the_server_message_readable() -> None:
    """An empty credential does not turn the message into per-character noise.

    `str.replace` with an empty needle inserts its replacement between every
    character, so scrubbing an empty value would destroy the one diagnostic the
    refusal exists to carry while protecting nothing.
    """
    runner = _FailingRunner(stderr="vault rejected the write")
    secret = VaultSecret(env_name="GITHUB_TOKEN", secret_name=_KEY, value="")
    message = cast("str", _sink(runner=runner).set(secret=secret))
    assert "vault rejected the write" in message


def _pass_through_secret() -> VaultSecret:
    """One secret whose opaque placeholder value appears in no assertion above."""
    return VaultSecret(env_name="GITHUB_TOKEN", secret_name=_KEY, value="scrub-arms-placeholder")
