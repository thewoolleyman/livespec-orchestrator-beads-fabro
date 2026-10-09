"""The identity each party to the archive completeness leg is computed under.

The leg's whole guarantee is a comparison between two computed identities, so the
cases that matter here are the ones a constant comparand could never have: the
agent-session route, the forge-login route a human at a terminal takes, the
defaults an ordinary in-session call relies on, and the refusal when neither
route answers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._plan_archive_gates import (
    PlanArchiveRefusedError,
)
from livespec_orchestrator_beads_fabro.commands._plan_completeness_identity import (
    ARCHIVING_PARTY,
    completeness_leg_identity,
)

_SESSION_VAR = "CLAUDE_CODE_SESSION_ID"


@dataclass(frozen=True, kw_only=True)
class _Runner:
    """A `CommandRunner` recording every argv it was asked to run."""

    result: CommandResult
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        return self.result


def _result(*, exit_code: int = 0, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr="")


def test_an_agent_session_archives_under_its_own_session_id() -> None:
    """The session id answers, and the forge is never asked.

    The unused-runner assertion is the load-bearing half: a resolver that
    consulted the forge anyway would give the capture and its replay — and here,
    the archiver and its reviewer — the SAME identity on this fleet, because every
    agent session on a host shares one token.
    """
    runner = _Runner(result=_result(stdout="maintainer\n"))

    identity = completeness_leg_identity(
        role=ARCHIVING_PARTY,
        project_root=Path("/repo"),
        env={_SESSION_VAR: "archiving-session"},
        runner=runner,
    )

    assert identity == "archiving-session"
    assert runner.argvs == []


def test_a_human_at_a_terminal_archives_under_the_forge_login() -> None:
    runner = _Runner(result=_result(stdout="maintainer\n"))

    identity = completeness_leg_identity(
        role=ARCHIVING_PARTY, project_root=Path("/repo"), env={}, runner=runner
    )

    assert identity == "maintainer"
    assert runner.argvs == [["gh", "api", "user", "--jq", ".login"]]


def test_the_defaults_read_the_invoking_session_and_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An ordinary in-session call supplies nothing and is still computed.

    This is the path the plan prose's own invocation takes, so it is covered
    rather than left to the explicit-argument form: the defaults are what make
    `archive_thread(...)` work for a session that holds no runner of its own.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(_SESSION_VAR, "ambient-session")

    assert completeness_leg_identity(role=ARCHIVING_PARTY) == "ambient-session"


def test_an_unresolved_identity_refuses_and_names_which_party_went_unnamed() -> None:
    """Fail-closed: a leg comparing two identities has no check while one is unknown.

    The refusal NAMES the party, because both sides raise the same refusal type
    and an operator reading "no identity could be computed" cannot otherwise tell
    whether the archiver or the reviewer is the one that went unresolved.
    """
    runner = _Runner(result=_result(exit_code=1))

    with pytest.raises(PlanArchiveRefusedError) as refused:
        _ = completeness_leg_identity(
            role=ARCHIVING_PARTY, project_root=Path("/repo"), env={}, runner=runner
        )

    assert "no publishing identity could be computed" in str(refused.value)
    assert ARCHIVING_PARTY in str(refused.value)
