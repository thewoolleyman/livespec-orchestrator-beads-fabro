"""Whether the Fabro server serving this dispatch can REACH the dispatch target.

The `SPECIFICATION/contracts.md` per-tenant-engine-identity clause: a Fabro
server instance holds exactly ONE App integration, so dispatching an adopter
repository through the fleet's shared server fails -- the fleet App is not
installed for the target -- and adopter dispatch runs against a per-tenant
server instance carrying the adopter's own `app_id` and its own key. That clause
then asks for a dispatch preflight that "verify the serving App can reach the
target repo BEFORE launching, refusing with an actionable diagnostic rather than
failing inside the engine run", and requires the refusal to surface the App
`workflows` read-write grant as one DELIBERATELY WITHHELD from the dispatch
credential, naming the attended-host-session route for work requiring it.

WHY THE TOKEN MINT COULD NOT ALREADY ANSWER THIS. Every dispatch already mints
an App installation token, and that mint refuses a dispatch whose App
environment is absent or unusable. It cannot refuse THIS condition, because an
installation token is App-and-installation scoped rather than repository scoped:
a fleet App installed across the fleet's own repositories mints a perfectly
valid token for a dispatch aimed at a repository it has never been installed on.
The question "can this credential see that repository" is a separate read, and
until this module existed nothing took it.

THE REFUSAL IS A DEFINITE-NEGATIVE GAUGE, AND THAT SCOPE IS DELIBERATE RATHER
THAN A FAIL-OPEN. `reaches` is tri-state and only `False` refuses: a reading the
preflight could not TAKE is journaled, named on the dispatch's own stderr, and
left to the engine run, which is exactly the status quo this clause improves on
rather than a weakening of it. The reason is the blast radius of the other
choice: refusing on an unmeasurable reading would make EVERY dispatch in the
fleet depend on one further forge read succeeding, for a condition that is
structural and stable -- an App either is or is not installed for a repository,
and that does not flicker with a 503. A gauge refusing when blinded would turn
each such flicker into a line stop. What is NOT admitted here is the opposite
move: an unobservable reading is never recorded as reach, so nothing in the
record can read as a verification that was never performed.

THE UNEVALUATED ARM IS A STRUCTURAL ABSENCE AND NOT THE SAME THING. A Dispatcher
holding no App identity at all has no SERVING App whose reach could be verified,
so there is no question to answer and no forge read is spent asking it -- the
same shape the Fabro currency gate takes for a target that declares no server.
It is told apart from an unobservable reading by `app_identity`, which is empty
for exactly one of them.

WHAT IS READ, AND WHY BOTH READS ARE `gh`. The target's own `owner/name` comes
from `gh repo view`, which is the identity the forge itself holds rather than
whatever an origin URL happens to spell; the reach probe is `gh api
repos/<owner>/<name>` carrying the MINTED INSTALLATION TOKEN in the child
environment, so the credential under test is the one the dispatch will project
and not the Dispatcher's ambient login. A `404` there is the definite negative:
the forge answers an installation-scoped read for a repository outside the
installation as though the repository does not exist, which is why the reading
is about REACH rather than about permissions.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_runtime.github_auth.errors import GithubAppAuthError

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    github_token_supplier,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "APP_REACH_STAGE",
    "TARGET_IDENTITY_ARGV",
    "AppReachReading",
    "app_reach_journal_record",
    "app_reach_refusal",
    "app_reach_refusal_detail",
    "read_app_reach",
    "serving_app_token_supplier",
    "target_reach_argv",
]

APP_REACH_STAGE = "app-reach"

# The forge's OWN name for the target, rather than whatever its `origin` URL
# spells: a mirror, a rename or an `ssh` alias all leave the remote naming
# something the installation read would answer `404` for while the repository is
# perfectly reachable, which is the one false definite-negative available here.
TARGET_IDENTITY_ARGV: tuple[str, ...] = (
    "gh",
    "repo",
    "view",
    "--json",
    "nameWithOwner",
    "--jq",
    ".nameWithOwner",
)

# The App id names the SERVING App in the refusal. It is read as the host
# credential environment spells it, which is the same variable
# `load_github_app_config` reads, so the identity a refusal names is the identity
# the mint used.
_APP_ID_ENV = "GITHUB_APP_ID"
_PROBE_TIMEOUT_SECONDS = 30.0
# `gh` prints its HTTP status into stderr rather than setting a distinct exit
# code, so the definite negative is recognised on the status text. Both spellings
# the CLI uses are matched, because a status-only match would also claim a `404`
# appearing in some other diagnostic.
_NOT_FOUND_SIGNATURES: tuple[str, ...] = ("HTTP 404", "Not Found")


@dataclass(frozen=True, kw_only=True)
class AppReachReading:
    """One reading of whether the serving App reaches the dispatch target.

    `app_identity` is empty for exactly one condition -- no serving App identity
    is declared to this Dispatcher at all -- which is what tells the UNEVALUATED
    arm apart from a reading that was attempted and could not be taken.

    `reaches` is tri-state and `None` is never coerced: `True` and `False` are
    measurements, and `None` is the absence of one. A coerced `False` would
    refuse a dispatch on a reading nobody took, and a coerced `True` would record
    a verification that never happened.
    """

    app_identity: str
    target: str
    reaches: bool | None
    detail: str


def serving_app_token_supplier() -> Callable[[], str] | str:
    """The serving App's installation-token accessor, or why there is none.

    A thin pass-through so this module has ONE name the reach probe resolves its
    credential through and a test can stand in, rather than each caller reaching
    for the self-update module's accessor. The `str` arm is that accessor's own
    refusal detail, which this preflight reports as an unobservable reading
    rather than as a refusal: an unusable App environment is a credential fault
    the overlay materializer already refuses, and reporting it here as a reach
    failure would send an operator after a per-tenant server for a fault that has
    nothing to do with one.
    """
    return github_token_supplier()


def target_reach_argv(*, target: str) -> list[str]:
    """The installation-scoped read whose `404` is the definite negative."""
    return ["gh", "api", f"repos/{target}", "--silent"]


def app_reach_refusal_detail(*, reading: AppReachReading) -> str:
    """The ONE diagnostic this preflight renders, carrying all three duties.

    The clause asks for three things in the refusal and they are one message
    rather than three, because an operator reads one: the per-tenant server
    requirement named as the TARGET TENANT's own App identity, the `workflows`
    read-write grant named as deliberately withheld from the dispatch credential,
    and the attended-host-session route for the work that needs it. Splitting
    them would let a build render whichever one it liked and still satisfy a
    reader asserting on either.
    """
    return (
        f"app-reach refusal: the Fabro server serving this dispatch holds GitHub App "
        f"{reading.app_identity}, which cannot reach the dispatch target "
        f"{reading.target}: {reading.detail}. A Fabro server instance holds exactly ONE "
        "App integration, so an adopter dispatch runs against a per-tenant server "
        "instance carrying the target tenant's own GitHub App identity -- its own "
        "app_id, its own private key in the server process environment, and its own "
        "port and authentication -- rather than through a shared server whose App is "
        "not installed for this target. Note also that the App `workflows` read-write "
        "grant is deliberately withheld from the dispatch credential and is NOT a gap "
        "to close by granting it: work whose scope requires that capability is routed "
        "to the attended host session, which already holds it legitimately and where "
        "every diff is reviewed.\n"
    )


def app_reach_journal_record(*, reading: AppReachReading) -> dict[str, object]:
    """One item's app-reach record, for every arm that EVALUATED anything.

    Both arms that refuse nothing still journal -- a verified reading and an
    unobservable one -- because a pass recording only refusals would leave the
    two indistinguishable afterwards, and the unobservable one is precisely the
    state an operator needs to be able to find.

    The UNEVALUATED arm is the exception and `app_reach_refusal` withholds the
    record there. That arm is a property of the INVOCATION rather than of the
    dispatch: it fires for every `dispatcher.py` call made outside the credential
    wrapper, which is every test, every local invocation and every drain pass on
    a host holding no App identity. A per-item row per pass saying "this
    Dispatcher declares no App" informs no action and is the one row an operator
    reading the journal has to learn to skip.
    """
    return {
        "stage": APP_REACH_STAGE,
        "app_identity": reading.app_identity,
        "target": reading.target,
        "reaches": reading.reaches,
        "detail": reading.detail,
    }


def read_app_reach(
    *,
    repo: Path,
    runner: CommandRunner,
    environ: Mapping[str, str],
    token_supplier: Callable[[], str] | str,
) -> AppReachReading:
    """Take the reading, spending no forge read on a question that cannot arise.

    The App-identity test runs FIRST, so a Dispatcher holding no serving App
    identity costs nothing at all: it is the ordinary state of any invocation
    outside the credential wrapper, and a forge read there would be spent
    answering a question that has no possible yes.
    """
    app_identity = environ.get(_APP_ID_ENV, "")
    if not app_identity:
        return AppReachReading(
            app_identity="",
            target="",
            reaches=None,
            detail=(
                f"no serving App identity is declared to this Dispatcher "
                f"({_APP_ID_ENV} is absent), so there is no App whose reach could be "
                "verified"
            ),
        )
    named = runner.run(
        argv=list(TARGET_IDENTITY_ARGV), cwd=repo, timeout_seconds=_PROBE_TIMEOUT_SECONDS
    )
    target = named.stdout.strip()
    if named.exit_code != 0 or not target:
        return AppReachReading(
            app_identity=app_identity,
            target="",
            reaches=None,
            detail=f"the forge did not name the target repository: {named.stderr.strip()}",
        )
    return _probed(
        repo=repo,
        runner=runner,
        app_identity=app_identity,
        target=target,
        token_supplier=token_supplier,
    )


def app_reach_refusal(*, repo: Path, items: Sequence[WorkItem], journal: object) -> str | None:
    """The wall-facing preflight: one reading, one record per item, one refusal.

    The reading is a property of the (serving App, target repository) PAIR rather
    than of any item, so it is taken ONCE and the refusal returned once --
    enumerating it per candidate would read as N faults where there is one. The
    journal records are per item, because each dispatched item gets its own run
    and a reader asking what one item's dispatch verified must not be answered
    with a sibling's; the UNEVALUATED arm writes none, for the reason
    `app_reach_journal_record` records.

    An EMPTY selection returns before anything is read. The drain reaches this
    wall on every pass that finds no ready work, so that is the common case, and
    a forge read there would be spent on a pass that was never going to dispatch.
    """
    if not items:
        return None
    reading = read_app_reach(
        repo=repo,
        runner=ShellCommandRunner(),
        environ=os.environ,
        token_supplier=serving_app_token_supplier(),
    )
    append = getattr(journal, "append", None)
    if append is not None and reading.app_identity:
        for item in items:
            append(record={**app_reach_journal_record(reading=reading), "work_item_id": item.id})
    if reading.reaches is False:
        return app_reach_refusal_detail(reading=reading)
    return None


def _probed(
    *,
    repo: Path,
    runner: CommandRunner,
    app_identity: str,
    target: str,
    token_supplier: Callable[[], str] | str,
) -> AppReachReading:
    """Ask the forge, with the minted installation token, whether it sees `target`."""
    token = _token(token_supplier=token_supplier)
    if isinstance(token, _TokenFault):
        return AppReachReading(
            app_identity=app_identity,
            target=target,
            reaches=None,
            detail=f"the serving App's installation token could not be minted: {token.detail}",
        )
    probe = runner.run(
        argv=target_reach_argv(target=target),
        cwd=repo,
        timeout_seconds=_PROBE_TIMEOUT_SECONDS,
        env={"GH_TOKEN": token, "GITHUB_TOKEN": token},
    )
    if probe.exit_code == 0:
        return AppReachReading(
            app_identity=app_identity,
            target=target,
            reaches=True,
            detail="the serving App's installation token reads the target repository",
        )
    stderr = probe.stderr.strip()
    if any(signature in stderr for signature in _NOT_FOUND_SIGNATURES):
        return AppReachReading(
            app_identity=app_identity,
            target=target,
            reaches=False,
            detail=(
                "an installation-scoped read of the target answered as though the "
                f"repository does not exist ({stderr})"
            ),
        )
    return AppReachReading(
        app_identity=app_identity,
        target=target,
        reaches=None,
        detail=f"the installation-scoped read of the target could not be taken: {stderr}",
    )


@dataclass(frozen=True, kw_only=True)
class _TokenFault:
    """Why the serving App's installation token could not be obtained."""

    detail: str


def _token(*, token_supplier: Callable[[], str] | str) -> str | _TokenFault:
    """The minted token, or the fault that stopped it, as data either way.

    The supplier's two failure shapes are kept apart in their DETAIL and joined
    in their effect: an unresolvable App configuration arrives as the supplier's
    own refusal string, and a mint that reached the forge and failed arrives as
    `GithubAppAuthError`. Both leave the reading unobservable, and neither is
    allowed to escape as a traceback from inside a wall whose whole purpose is
    rendering an actionable refusal.
    """
    if isinstance(token_supplier, str):
        return _TokenFault(detail=token_supplier)
    minted = attempt(action=token_supplier, exceptions=(GithubAppAuthError,))
    if isinstance(minted, AttemptFailure):
        return _TokenFault(detail=str(minted.error))
    return minted
