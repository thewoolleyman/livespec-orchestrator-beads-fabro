"""The publishing identity a proof record carries, COMPUTED and never accepted.

The host-leg clause of `SPECIFICATION/contracts.md` (v115) requires the posting
primitive to "compute the publishing identity itself — the invoking agent session's
id, or the forge login for a human — and MUST NOT accept it as a caller-supplied
string". The plan-record clause imposes the same rule on plan records. This module
is that computation, and it is deliberately the ONLY route to a record's third
header field.

WHY THE PROHIBITION IS THE POINT AND NOT A DETAIL. The independence refusal — a
`host_verified` post whose computed identity equals the `host_recorded` record's is
refused — is the whole of the "independent party" guarantee. An identity a caller
could NAME is an identity a caller could RENAME, so a self-replay would be one flag
away from passing, and the refusal would be theatre. There is therefore no
parameter here that a caller can put an identity in, and that signature is itself
asserted by this module's tests.

WHY THE AGENT SESSION IS ASKED BEFORE THE FORGE, which is the one ordering decision
in the module. A forge login is a property of the TOKEN, not of the session: on this
fleet every agent session on a host shares one token, so resolving a session's
identity from the forge would give the capture and its replay the SAME identity.
That breaks the rule in the direction that is hardest to notice — the refusal fires
on a genuinely independent replay, the operator reads "you cannot replay your own
record", and there is in fact no way to publish a replay from that host at all. The
session id is what actually distinguishes the two parties, so it answers first; the
forge login answers only for a human at a terminal, who has no agent session.

WHY `None` RATHER THAN A FALLBACK MARK. `_dispatcher_invoker` resolves an
`unattributed:<user>@<host>` mark when no identity is asserted, which is right for a
journal record — it records that nobody claimed the act. It is wrong here, in both
directions at once: two posts carrying the mark compare EQUAL, so an honest replay
from the same host is refused as a self-replay, while a genuine self-replay across
two hosts whose marks differ slips past. A record that cannot name its publisher is
not publishable, so the computation is partial and the primitive refuses.

WHY THE VARIABLE SET IS A DECLARED CONSTANT. A runtime absent from it falls through
to the shared forge login, which is the failure above. Adding a runtime to the fleet
therefore means adding its session variable here — and the set is exercised entry by
entry in the tests so that an entry added without a test cannot pass.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "AGENT_SESSION_ENV_VARS",
    "HUMAN_KIND",
    "SESSION_KIND",
    "PublishingIdentity",
    "computed_publishing_identity",
    "forge_login_argv",
]

# The two identity KINDS the ratified header grammar admits for a host or plan
# record. `run` is the third, and it is deliberately absent: a run id is stamped by
# the factory onto a factory record, and nothing a session invokes may claim one.
SESSION_KIND = "session"
HUMAN_KIND = "human"
# The agent-session variable each runtime this fleet dogfoods exports into the
# session's own environment. Order is irrelevant — a process runs under exactly one
# of these — so the first non-empty one found is the answer.
AGENT_SESSION_ENV_VARS = ("CLAUDE_CODE_SESSION_ID", "CODEX_SESSION_ID", "PI_SESSION_ID")

_LOGIN_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, kw_only=True)
class PublishingIdentity:
    """One computed publishing identity, and the input it was computed from.

    `source` is carried for the same reason `InvokerIdentity.invoker_source` is: a
    refusal that names only the identity leaves an operator unable to tell a session
    id from a forge login that happens to look like one, and the posting primitive
    journals the source so a later audit can see WHICH route attributed the record.
    """

    kind: str
    identity: str
    source: str

    @property
    def header_field(self) -> str:
        """The record header's third field, introducer included.

        Rendered here rather than by the renderer because the introducer and the
        kind are one decision: the reader strips the introducer to recover the
        identity, so a record whose kind and introducer disagreed would read as an
        identity with a word glued to it.
        """
        return f"{self.kind} {self.identity}"


def forge_login_argv() -> list[str]:
    """The read that resolves the forge login of whoever holds the token.

    Published so the posting primitive's own tests and journal can name the exact
    read, rather than reconstructing an argv that might differ from the one run.
    """
    return ["gh", "api", "user", "--jq", ".login"]


def computed_publishing_identity(
    *, repo: Path, env: Mapping[str, str], runner: CommandRunner
) -> PublishingIdentity | None:
    """The identity this invocation publishes under, or `None` when none resolves.

    `env` is passed in rather than read from `os.environ` here so the computation
    stays a function of its inputs; the entry point hands it the real environment.
    That is not a caller-supplied identity route — an environment is the SESSION's
    own property, which is exactly what the clause asks the primitive to read.
    """
    session = _agent_session(env=env)
    if session is not None:
        return session
    return _forge_login(repo=repo, runner=runner)


def _agent_session(*, env: Mapping[str, str]) -> PublishingIdentity | None:
    for name in AGENT_SESSION_ENV_VARS:
        value = env.get(name, "").strip()
        if value:
            return PublishingIdentity(kind=SESSION_KIND, identity=value, source=name)
    return None


def _forge_login(*, repo: Path, runner: CommandRunner) -> PublishingIdentity | None:
    argv = forge_login_argv()
    result = runner.run(argv=argv, cwd=repo, timeout_seconds=_LOGIN_TIMEOUT_SECONDS)
    login = result.stdout.strip()
    if result.exit_code != 0 or not login:
        return None
    return PublishingIdentity(kind=HUMAN_KIND, identity=login, source=" ".join(argv))
