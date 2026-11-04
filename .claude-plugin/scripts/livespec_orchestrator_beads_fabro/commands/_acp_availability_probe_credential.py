"""The projected worker credential one availability confirmation turn carries.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Availability is re-confirmed after expiry": availability is
confirmed only by a successfully completed ACP prompt turn using "the
candidate's pinned adapter version, requested model and effort, and projected
worker credential identity". `_acp_availability_probe` argues the first three
from `render_adapter`'s byte equality and `_acp_availability_probe_run` places
the turn in the factory's declared environment; this module supplies the fourth
property's other half, the credential itself.

A TURN LAUNCHED WITH NO CREDENTIAL CAN NEVER CONFIRM. The factory's environment
selects WHERE the turn runs, and nothing in a bare manifest puts a token in it:
the adapter answered `session/prompt` with `Authentication required` three
seconds in, so every attempt ran the probe, failed authentication and left
admission refusing exactly as before (`bd-ib-3pfauo`, measured on the
git-jsonl tenant 2026-10-29). The credential is therefore projected the way a
dispatch projects it, and by the same function: `select_factory_credential`
names the env var, so the probe, the session-headroom gate, the credential
status command and a dispatch all name ONE account, and the value travels under
the standard `CLAUDE_CODE_OAUTH_TOKEN` name the adapter reads.

THE TRANSPORT IS THE FACTORY'S DECLARED ONE. The inline channel puts the value
in the manifest the engine reads, and the native channel stores it in the
factory vault under the stable key a dispatch uses and renders only the
reference. The routing is `route_secrets_through_vault` itself rather than a
second rewrite, so a Petri-era server, which persists a manifest in an immutable
workflow version, never receives an inline credential from a probe either. The
vault store holds the per-factory launch lock, and the performing half releases
it as the turn ends: a lock kept past the turn would block the next dispatch to
that factory for the life of the process.

ONLY A CLAUDE CANDIDATE IS HANDED THIS CREDENTIAL. Coverage follows the
provenance question `headroom_covers_candidate` already answers -- the resolved
`claude-acp` agent id, or a built-in identity keyed on exact rendered bytes --
because handing an Anthropic token to an adapter that never asked for it is
exposure for nothing. A candidate for another vendor is launched exactly as it
was, and the Codex credential's own projection is not this module's.

TWO ABSENCES ARE KEPT APART. A process environment holding no value for the
selected name projects nothing and launches anyway: the turn then fails
authentication and is graded as that ending, which is the honest record, where a
refusal here would hide the gap behind a skipped candidate. A credential WITH no
catalog environment to key its table under is a refusal, because the engine reads
an env table only under the environment the run selected, so launching would
spend an allowance on a turn whose credential was dropped silently.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    headroom_covers_candidate,
)
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    ANTHROPIC_CREDENTIAL_ENV,
    SecretChannelRefusal,
    resolve_secret_channel,
    route_secrets_through_vault,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_vault import FabroVaultSink
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroRunner
from livespec_orchestrator_beads_fabro.io import write_stderr

__all__: list[str] = [
    "NO_PROBE_CREDENTIAL",
    "ProbeCredential",
    "project_probe_credential",
]


@dataclass(frozen=True, kw_only=True)
class ProbeCredential:
    """What one confirmation turn's manifest gains, and what must be released after it.

    `manifest_tail` is the env table appended to the probe's manifest, empty for
    a turn that carries no credential. `sink` is the vault the value was stored
    in, held so the launch lock it took can be released when the turn ends, and
    `None` whenever nothing was stored.
    """

    manifest_tail: str
    sink: FabroVaultSink | None

    def release(self) -> None:
        """Let the next dispatch to the same factory refresh the stable vault names."""
        if self.sink is not None:
            self.sink.release_launch_guard()


NO_PROBE_CREDENTIAL = ProbeCredential(manifest_tail="", sink=None)


def project_probe_credential(  # noqa: PLR0913 — kw-only probe inputs; each is one INDEPENDENT operand of the one projection (which repository, factory, server, binary, environment, candidate and runner), and grouping any pair would invent a relationship the projection does not have.
    *,
    repo: Path,
    factory_name: str,
    server: str,
    fabro_bin: str,
    environment: str | None,
    candidate: AcpCandidate,
    builtin: bool,
    runner: FabroRunner,
) -> ProbeCredential | str:
    """The credential this candidate's turn carries, or why the turn cannot run.

    A string is a refusal and is the clause's "any other probe failure": the
    candidate is skipped for this evaluation with no hold. It never carries the
    credential value.
    """
    if not _is_claude_candidate(candidate=candidate, builtin=builtin):
        return NO_PROBE_CREDENTIAL
    choice = select_factory_credential(
        environ=os.environ,
        home=Path.home(),
        warn=lambda message: write_stderr(text=f"livespec-dispatch: {message}\n"),
    )
    token = os.environ.get(choice.env_name, "")
    if token == "":
        return NO_PROBE_CREDENTIAL
    if environment is None:
        return (
            f"factory {factory_name!r} declares no catalog environment, and the engine "
            "reads a credential table only under the environment a run selected, so a "
            "turn launched here would drop its credential and could not authenticate"
        )
    channel = resolve_secret_channel(block=dispatcher_block(cwd=repo), factory=factory_name)
    if isinstance(channel, SecretChannelRefusal):
        return channel.message
    table = (
        f"\n[environments.{environment}.env]\n{ANTHROPIC_CREDENTIAL_ENV} = {json.dumps(token)}\n"
    )
    return _routed(
        table=table,
        channel=channel,
        factory_name=factory_name,
        server=server,
        fabro_bin=fabro_bin,
        repo=repo,
        runner=runner,
    )


def _routed(  # noqa: PLR0913 — kw-only routing inputs; each is one INDEPENDENT operand of the one store-then-render step, and grouping any pair would invent a relationship the step does not have.
    *,
    table: str,
    channel: str,
    factory_name: str,
    server: str,
    fabro_bin: str,
    repo: Path,
    runner: FabroRunner,
) -> ProbeCredential | str:
    """Route the env table onto the declared channel, storing any displaced value first."""
    routed = route_secrets_through_vault(
        overlay_text=table, channel=channel, env_names=(ANTHROPIC_CREDENTIAL_ENV,)
    )
    if isinstance(routed, SecretChannelRefusal):
        return routed.message
    if not routed.secrets:
        return ProbeCredential(manifest_tail=routed.overlay_text, sink=None)
    sink = FabroVaultSink(fabro_bin=fabro_bin, server_url=server, runner=runner, cwd=repo)
    for secret in routed.secrets:
        failure = sink.set(secret=secret)
        if failure is not None:
            sink.release_launch_guard()
            return (
                f"storing {secret.secret_name} in factory {factory_name!r}'s vault failed "
                f"({failure}), so the turn would authenticate with a stale or absent value"
            )
    return ProbeCredential(manifest_tail=routed.overlay_text, sink=sink)


def _is_claude_candidate(*, candidate: AcpCandidate, builtin: bool) -> bool:
    """Whether this candidate's adapter authenticates with the Claude credential."""
    identity = candidate.identity
    builtin_pairs: frozenset[tuple[str, str]] = frozenset()
    if builtin and identity is not None:
        builtin_pairs = frozenset({identity.pair})
    return headroom_covers_candidate(candidate=candidate, builtin_pairs=builtin_pairs)
