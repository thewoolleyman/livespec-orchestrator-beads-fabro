"""Tests for the publishing identity a record carries, which the primitive COMPUTES.

The host-leg clause of `SPECIFICATION/contracts.md` (v115) is explicit about both
halves: the posting primitive "MUST compute the publishing identity itself — the
invoking agent session's id, or the forge login for a human — and MUST NOT accept
it as a caller-supplied string". The plan-record clause says the same. These tests
bind the computation AND the absence of a caller-supplied route, because the second
half is what makes the independence refusal mean anything: an identity a caller can
name is an identity a caller can rename, and a self-replay would then be one flag
away from passing.

WHY THE AGENT SESSION IS CONSULTED BEFORE THE FORGE. A forge login is a property of
the TOKEN, not of the session, so two agent sessions on one host — which is the
ordinary case for a capture and its replay — would compute the SAME human identity.
The independence check would then refuse a genuinely independent replay, and, worse,
the fleet would have no way to publish one at all. The session id is what actually
distinguishes the two parties, so it is asked first, and the forge login is the
answer only for a human at a terminal, who has no agent session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_identity import (
    AGENT_SESSION_ENV_VARS,
    HUMAN_KIND,
    SESSION_KIND,
    PublishingIdentity,
    computed_publishing_identity,
    forge_login_argv,
)

_REPO = Path("/repo")
_SESSION = "1f0b5a2c-7d41-4e9a-9c3b-0a1b2c3d4e5f"
_LOGIN = "thewoolleyman"


@dataclass(kw_only=True)
class _Runner:
    """A `CommandRunner` double recording every argv it was handed."""

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


def test_an_agent_session_publishes_under_its_own_session_id() -> None:
    """The session id wins, and the forge is never asked.

    The unused-runner assertion is the load-bearing half: a computation that
    consulted the forge anyway would produce the right answer here while costing a
    round trip per post and, on a host whose token is unavailable, failing for a
    reason that has nothing to do with the identity it already had.
    """
    runner = _Runner(result=_result(stdout=f"{_LOGIN}\n"))
    identity = computed_publishing_identity(
        repo=_REPO, env={AGENT_SESSION_ENV_VARS[0]: _SESSION}, runner=runner
    )
    assert identity == PublishingIdentity(
        kind=SESSION_KIND, identity=_SESSION, source=AGENT_SESSION_ENV_VARS[0]
    )
    assert identity.header_field == f"{SESSION_KIND} {_SESSION}"
    assert runner.argvs == []


def test_every_declared_agent_session_variable_is_consulted() -> None:
    """Each runtime in the declared set resolves, so no runtime is silently human.

    A runtime absent from the set falls through to the forge login, which is a
    SHARED identity — so an unrecognised runtime would make every session on the
    host indistinguishable, and the independence refusal would start firing on
    genuinely independent replays. The whole set is therefore exercised rather than
    the first entry alone.
    """
    for name in AGENT_SESSION_ENV_VARS:
        identity = computed_publishing_identity(
            repo=_REPO, env={name: _SESSION}, runner=_Runner(result=_result())
        )
        assert identity == PublishingIdentity(kind=SESSION_KIND, identity=_SESSION, source=name)


def test_a_human_at_a_terminal_publishes_under_the_forge_login() -> None:
    """With no agent session, the identity is the forge login the token resolves."""
    runner = _Runner(result=_result(stdout=f"{_LOGIN}\n"))
    identity = computed_publishing_identity(repo=_REPO, env={}, runner=runner)
    assert identity == PublishingIdentity(
        kind=HUMAN_KIND, identity=_LOGIN, source=" ".join(forge_login_argv())
    )
    assert identity.header_field == f"{HUMAN_KIND} {_LOGIN}"
    assert runner.argvs == [forge_login_argv()]


def test_a_blank_session_value_is_not_an_identity() -> None:
    """An empty or whitespace variable asserts nothing, so the forge answers instead.

    A runtime that exports the variable unset is the common shape of "not running
    under that runtime", and treating the empty string as a session id would
    publish every such post under one blank identity — which the independence check
    would then read as a self-replay for every pair.
    """
    runner = _Runner(result=_result(stdout=f"{_LOGIN}\n"))
    identity = computed_publishing_identity(
        repo=_REPO, env={AGENT_SESSION_ENV_VARS[0]: "   "}, runner=runner
    )
    assert identity is not None
    assert identity.kind == HUMAN_KIND


def test_an_unresolvable_forge_login_computes_no_identity_at_all() -> None:
    """`None` refuses the post rather than inventing an identity.

    This is the fail-closed direction and it is the whole reason the function is
    partial. A fallback mark — the shape the journal invoker resolution uses — would
    be a publishable identity that names no party, and two posts carrying it would
    compare EQUAL: the independence refusal would fire on an honest replay, and a
    genuine self-replay under two different unresolvable hosts would slip past.
    """
    runner = _Runner(result=_result(exit_code=1, stdout=""))
    assert computed_publishing_identity(repo=_REPO, env={}, runner=runner) is None


def test_a_forge_login_that_prints_nothing_computes_no_identity() -> None:
    """A zero-exit read that produced no login is still no identity."""
    runner = _Runner(result=_result(stdout="\n"))
    assert computed_publishing_identity(repo=_REPO, env={}, runner=runner) is None


def test_the_identity_cannot_be_supplied_by_a_caller() -> None:
    """The computation's own signature is the guarantee, so it is asserted here.

    The clause forbids accepting the identity "as a caller-supplied string", and the
    only mechanical reading of that is that no parameter of this computation can
    carry one. A later refactor that added an `identity` or `session` override would
    satisfy every other test in this file while retiring the independence rule
    entirely, so the parameter set is pinned.
    """
    import inspect

    parameters = set(inspect.signature(computed_publishing_identity).parameters)
    assert parameters == {"repo", "env", "runner"}
