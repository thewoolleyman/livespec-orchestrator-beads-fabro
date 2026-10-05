"""One run's lease on its provider-minted proof credentials: mint, then revoke.

The MINTING half of `SPECIFICATION/contracts.md`'s proof-credential-projection
clause (ratified v114): where a declaration's provider exposes a management
interface, the Dispatcher mints a credential for THIS RUN and revokes it when
the run ends, rather than copying the host's. The interfaces themselves are the
repository's committed declaration (`_dispatcher_proof_credential_management`);
this module is the only place either of them is executed.

THE LEASE CARRIES NO STATE BETWEEN ITS TWO LEGS, and that is the design rather
than an omission. Both legs are addressed by the per-run SCOPE — the dispatch id
— so revoke asks the provider to drop whatever that run holds instead of being
handed a handle the mint produced. Threading a handle would mean the revoke could
only run where the mint's return value reached, which is exactly the shape that
loses a revoke whenever the path between the two takes an early return; keying on
a value both legs derive makes the revoke reachable from the run teardown with
nothing but the repository and the id.

A MINT FAILURE REFUSES THE DISPATCH; A REVOKE FAILURE CANNOT. Minting runs before
the overlay is written, so a failure there still has a decision to change and is
returned as a refusal the dispatch reports. Revoking runs after the run has ended,
where no decision is left — so it never refuses and never raises, and what a
failed revoke needs instead is to be VISIBLE, which is why each attempt is
journaled with its outcome rather than swallowed.

NO REFUSAL AND NO RECORD HERE CARRIES PROVIDER OUTPUT. The mint command's stdout
IS the credential, so a refusal naming the exit code is as much as can be said
about a failure; echoing stdout or stderr to a journal would publish the value
the whole clause exists to keep out of durable artifacts.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_management import (
    MINT_OPERATION,
    PROOF_CREDENTIAL_MANAGEMENT_KEY,
    ProviderManagementInterface,
    management_environment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credentials import (
    ProofCredential,
    resolved_proof_credentials,
)

__all__: list[str] = [
    "PROOF_CREDENTIAL_MANAGEMENT_TIMEOUT_SECONDS",
    "PROOF_CREDENTIAL_REVOKE_JOURNAL_STAGE",
    "mint_proof_credentials",
    "revoke_proof_credentials",
]

_DECLARED_KEY = f"dispatcher.{PROOF_CREDENTIAL_MANAGEMENT_KEY}"

# The ceiling on one provider call. Generous because a management API round trip
# is a network call an adopter does not control, and bounded because an
# unbounded one would hold a dispatch open before any run exists. The runner
# seam surfaces a timeout as a non-zero result, so a hung provider refuses the
# dispatch rather than hanging it.
PROOF_CREDENTIAL_MANAGEMENT_TIMEOUT_SECONDS = 120.0

# The dispatch-journal stage one revoke attempt is recorded under. DISTINCT from
# the projection stage, so a reader asking what a dispatch projected is not
# answered with its teardown.
PROOF_CREDENTIAL_REVOKE_JOURNAL_STAGE = "proof-credential-revoke"


def mint_proof_credentials(
    *, repo: Path, scope: str, runner: CommandRunner
) -> dict[str, str] | str:
    """Mint one credential per managed declaration, or the FIRST refusal it earns.

    Returns the minted values BY NAME, for the projection to render. A repository
    declaring no provider mints nothing and spawns nothing, which is every
    repository in this fleet today.
    """
    minted: dict[str, str] = {}
    for credential, interface in _managed(repo=repo):
        result = _run_management(
            argv=interface.mint_argv,
            repo=repo,
            credential=credential,
            scope=scope,
            runner=runner,
        )
        if result.exit_code != 0:
            return (
                f"{_DECLARED_KEY}[{credential.name}].{MINT_OPERATION} exited "
                f"{result.exit_code}; the provider's management interface could not "
                f"mint a {credential.capability} credential for this run"
            )
        value = result.stdout.strip()
        if not value:
            return (
                f"{_DECLARED_KEY}[{credential.name}].{MINT_OPERATION} exited 0 but "
                "printed no credential on stdout; the mint command must print the "
                "value it minted and nothing else"
            )
        minted[credential.name] = value
    return minted


def revoke_proof_credentials(
    *, repo: Path, scope: str | None, runner: CommandRunner, journal: object = None
) -> None:
    """Revoke every credential this run minted, after the run has ended.

    An ABSENT scope revokes nothing. The two legs address the provider by that
    one value, so with no scope there is nothing to ask the provider to drop —
    and a revoke issued under some other scope would drop another run's
    credential.

    `journal` is optional and is reached through its own `append`, matching the
    gate's seam, so this is callable from a hermetic test and from a caller
    holding none.
    """
    if scope is None:
        return
    append = getattr(journal, "append", None)
    for credential, interface in _managed(repo=repo):
        result = _run_management(
            argv=interface.revoke_argv,
            repo=repo,
            credential=credential,
            scope=scope,
            runner=runner,
        )
        if append is not None:
            append(
                record={
                    "stage": PROOF_CREDENTIAL_REVOKE_JOURNAL_STAGE,
                    "name": credential.name,
                    "scope": scope,
                    "revoked": result.exit_code == 0,
                    "exit_code": result.exit_code,
                }
            )


def _managed(*, repo: Path) -> tuple[tuple[ProofCredential, ProviderManagementInterface], ...]:
    """Each declaration whose provider exposes a management interface, paired with it.

    A declaration the resolution REFUSES yields nothing. The pre-dispatch gate
    has already refused such a repository on every dispatch path, so this arm is
    unreachable in production; it is written this way because the opposite —
    driving a provider from a declaration nobody admitted — is the expensive
    direction to be wrong in.
    """
    resolved = resolved_proof_credentials(block=dispatcher_block(cwd=repo))
    if isinstance(resolved, str):
        return ()
    return tuple(
        (credential, resolved.management[credential.name])
        for credential in resolved.declared
        if credential.name in resolved.management
    )


def _run_management(
    *,
    argv: tuple[str, ...],
    repo: Path,
    credential: ProofCredential,
    scope: str,
    runner: CommandRunner,
) -> CommandResult:
    """One provider command, addressed through the environment rather than argv.

    The argv reaches the provider VERBATIM as committed, and the three run facts
    ride in the environment, so nothing run-specific lands in a command line that
    `/proc` publishes to every local user on the dispatching host.
    """
    return runner.run(
        argv=list(argv),
        cwd=repo,
        timeout_seconds=PROOF_CREDENTIAL_MANAGEMENT_TIMEOUT_SECONDS,
        env=management_environment(
            name=credential.name, capability=credential.capability, scope=scope
        ),
    )
