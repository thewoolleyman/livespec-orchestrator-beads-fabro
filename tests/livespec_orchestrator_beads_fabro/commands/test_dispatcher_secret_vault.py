"""Handing a credential to a factory leaves it on no observable surface.

The THIRD Definition-of-Done assertion of work-item bd-ib-4ipmub: `inspect`,
`dump`, `events`, `logs` and the persisted run state of a canary run carry no
projected secret value. The bundle half of that is the routing rewrite; this
module is the OTHER half, and it is the one that is easy to get wrong while the
bundle looks immaculate.

A `fabro secret set` invocation is a host subprocess. An argument is visible in
the host process table to every user on the box for as long as the call runs, it
is what a command runner echoes into a log or a journal, and it is what a
timeout or not-found diagnostic quotes back. So the VALUE must never be an
argument: it is delivered on the child's standard input, from a descriptor whose
file has no name in the filesystem at all.

The failure path gets the same treatment. A server's own rejection text is
untrusted here -- it may quote what it was sent -- so the refusal message is
scrubbed of the value before it is returned to a dispatch that will journal it.
`SPECIFICATION/contracts.md` section "Proof credential projection" states the
rule this implements: journals and records MUST carry names, never values.

The module under test is imported through `importlib` inside each test body
rather than at module top, so the first Red of this slice fails on a genuine
assertion about the module's own absence instead of dying at collection.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import cast

import livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets as _commands_anchor
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    VaultSecret,
    vault_secret_name,
)

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_secret_vault"
_COMMANDS_DIR = Path(cast("str", _commands_anchor.__file__)).parent
_MODULE_PATH = _COMMANDS_DIR / "_dispatcher_secret_vault.py"

_SERVER = "https://hp-xubuntu.example.invalid:32278"
_FABRO_BIN = "/home/operator/.fabro-candidate/bin/fabro"
_SCOPE = "dispatch-vault-sink"

# An opaque non-secret placeholder carrying a shape worth asserting against: it
# is long enough that a substring match is meaningful, and it is the string the
# refusal path must scrub out of an echoing server message.
_VALUE = "vault-sink-placeholder-0123456789"
_SECRET = VaultSecret(
    env_name="CLAUDE_CODE_OAUTH_TOKEN",
    secret_name=vault_secret_name(env_name="CLAUDE_CODE_OAUTH_TOKEN", scope=_SCOPE),
    value=_VALUE,
)


@dataclass(kw_only=True)
class _RecordingRunner:
    """A runner that records each invocation and reads whatever stdin it is given."""

    exit_code: int = 0
    stderr: str = ""
    argvs: list[list[str]] = field(default_factory=list)
    envs: list[dict[str, str] | None] = field(default_factory=list)
    stdin_texts: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds
        self.argvs.append(list(argv))
        self.envs.append(env)
        self.stdin_texts.append("" if stdin is None else os.read(stdin, 4096).decode("utf-8"))
        return CommandResult(exit_code=self.exit_code, stdout="", stderr=self.stderr)


def _module() -> ModuleType:
    return importlib.import_module(_MODULE_NAME)


def test_the_value_is_delivered_on_standard_input_and_appears_in_no_argument() -> None:
    """The credential reaches the child on stdin; argv names it and nothing more."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    module = _module()
    runner = _RecordingRunner()
    sink = module.FabroVaultSink(
        fabro_bin=_FABRO_BIN, server_url=_SERVER, runner=runner, cwd=Path("/workspace/repo")
    )
    assert sink.set(secret=_SECRET) is None
    assert runner.stdin_texts == [_VALUE]
    argv = runner.argvs[0]
    assert argv[:3] == [_FABRO_BIN, "secret", "set"]
    assert _SECRET.secret_name in argv
    assert "--value-stdin" in argv
    # The whole argv as one string, so a value spliced into any argument -- or
    # into a `--value=` form -- is caught rather than only an exact element.
    assert _VALUE not in " ".join(argv)


def test_the_value_is_in_no_environment_the_child_inherits() -> None:
    """stdin is the ONLY channel: an env entry would reach every grandchild too."""
    module = _module()
    runner = _RecordingRunner()
    sink = module.FabroVaultSink(
        fabro_bin=_FABRO_BIN, server_url=_SERVER, runner=runner, cwd=Path("/workspace/repo")
    )
    _ = sink.set(secret=_SECRET)
    env = runner.envs[0]
    assert _VALUE not in "".join((env or {}).values())


def test_the_server_is_named_per_subcommand() -> None:
    """`--server` is a per-subcommand flag on this CLI, so it rides the argv tail."""
    module = _module()
    runner = _RecordingRunner()
    sink = module.FabroVaultSink(
        fabro_bin=_FABRO_BIN, server_url=_SERVER, runner=runner, cwd=Path("/workspace/repo")
    )
    _ = sink.set(secret=_SECRET)
    argv = runner.argvs[0]
    assert argv[-2:] == ["--server", _SERVER]


def test_a_rejected_write_refuses_with_the_value_scrubbed_out() -> None:
    """The server's own message is untrusted: it may quote what it was sent.

    The refusal is journaled by the dispatch that receives it, so a message
    carrying the value back would put the credential in the one record written
    specifically to say that the credential could not be stored.
    """
    module = _module()
    runner = _RecordingRunner(exit_code=1, stderr=f"rejected value {_VALUE} for key")
    sink = module.FabroVaultSink(
        fabro_bin=_FABRO_BIN, server_url=_SERVER, runner=runner, cwd=Path("/workspace/repo")
    )
    message = cast("str", sink.set(secret=_SECRET))
    assert _SECRET.secret_name in message
    assert _VALUE not in message
    # The server's reason survives the scrub, minus the value, so an operator
    # still learns WHY rather than only that something failed.
    assert "rejected" in message


def test_a_factory_with_no_server_url_names_none() -> None:
    """An ambient-target port passes no `--server`, exactly as every other verb."""
    module = _module()
    runner = _RecordingRunner()
    sink = module.FabroVaultSink(
        fabro_bin=_FABRO_BIN,
        server_url=None,
        runner=runner,
        cwd=Path("/workspace/repo"),
    )
    _ = sink.set(secret=_SECRET)
    assert "--server" not in runner.argvs[0]
