"""The reads the Fabro currency predicate is handed: engine, forge, cache.

The IMPURE half of the Fabro-currency-admission clause of
`SPECIFICATION/contracts.md`. `_dispatcher_fabro_currency` owns the RULE — what a
serving commit, a base and an observation decide — and this module owns
everything that rule needs gathered first: the target's own serving integration
commit, one observation of the upstream releases surface, and which published
release tag is the latest-published ancestor of that commit.

WHY THE SERVING COMMIT IS ASKED OF THE TARGET'S OWN SERVER. `fabro --version`
run locally reports the LOCAL CLIENT, which on this fleet is routinely a
different build from the engine a dispatch lands on — the two hosts are re-pinned
one at a time, so they diverge for as long as a rollout takes. A local client
reading would therefore report a fleet-global surrogate, which the clause forbids
in as many words: each configured target is evaluated against its own serving
commit. The port is constructed on the target's server url, so `fabro version`
addresses that server rather than the ambient one.

WHY THE FORGE IS ASKED FOR ANCESTRY RATHER THAN A LOCAL CLONE. This repository
holds no clone of the upstream engine at all, so there is no local object to run
`merge-base` against; a local probe would report an unresolvable ref for every tag
that plainly exists, and the refusal would have been manufactured by the
instrument rather than earned by the build.

THE ANCESTRY WALK IS BOUNDED BY THE OBSERVATION, AND SAYS SO. Each candidate
costs one forge round trip, so the walk examines each release the observation
carries exactly once and the refusal it may then produce STATES THE SCOPE IT
SEARCHED. An absence asserted over an unstated population is the shape that turns
a bounded search into a false impossibility.

THE BOUND IS THE OBSERVATION AND NOT A SMALLER NUMBER, and that is a correctness
requirement rather than a preference. A candidate cap below the observation size
does not merely miss a base — it MISDIAGNOSES one. The 30-day rule exists to
refuse a base that is OLD, so the base has to be found before it can be judged;
a cap that hides it reports `no-release-tag-ancestor`, which is a different
condition with a different corrective route, asserted over a population that
excluded the answer. Measured against the live forge on 2026-10-11: `v0.254.0` is
`identical` to the carrier commit `497aaba6` and sits at publication-order index
80 of the 147 releases `fabro-sh/fabro` has published, so a 40-candidate cap
refused the very carrier the ratified transition must ADMIT, and refused it for a
reason that reads like an unidentifiable build.

THE COST SCALES WITH STALENESS, which is the right direction. The walk stops at
the first ancestor in publication order, so a current build — the case this gate
exists to wave through — costs one or two round trips. Only a build with no
published release-tag ancestor at all pays the full observation, and that build is
being refused regardless.

AN UNREADABLE COMPARISON DOES NOT PROMOTE A TAG TO BASE. `_is_ancestor` answers
`False` for a failed command and for a status it does not recognise, so a blinded
comparison leaves the walk running and, if nothing else answers, ends in a
refusal. The opposite default would make an unreachable forge the cheapest way to
have any tag accepted as the base.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency import (
    FABRO_UPSTREAM_REPO,
    FabroCurrencySubject,
    FabroRelease,
    FabroReleaseObservation,
    releases_by_publication,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "ObservationReading",
    "compare_argv",
    "fabro_currency_subject",
    "parse_releases",
    "releases_argv",
    "resolved_base",
    "serving_integration_commit",
]

_COMPARE_TIMEOUT_SECONDS = 30.0
_VERSION_TIMEOUT_SECONDS = 30.0

# The comparison statuses that mean `head` carries `base`: `base` is `head`
# itself, or `head` has commits beyond it.
_CONTAINING_STATUSES = frozenset({"ahead", "identical"})

# A build commit as `fabro version --json` reports it under `git_sha`: an
# abbreviated or full hex object name. Anchored at both ends so a build date or
# any other non-commit text in that field reads as unobserved, not as a commit.
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")

# The server's own section of that output. The client section sits beside it,
# and reading the client's commit would report the LOCAL client build as the
# serving one — the exact fleet-global surrogate the clause forbids.
_SERVER_KEY = "server"


@dataclass(frozen=True, kw_only=True)
class ObservationReading:
    """One attempt to observe the upstream releases surface.

    TWO FIELDS RATHER THAN AN OPTIONAL ONE, because a STALE cached observation
    whose refresh failed must be carried FORWARD: the clause requires the refusal
    to name that stale observation, and an attempt that returned only `None`
    could not.
    """

    observation: FabroReleaseObservation | None
    failure: str | None


def releases_argv() -> list[str]:
    """The forge read of every published upstream release, newest first.

    Paginated because upstream publishes nightly tags, so one page cannot be
    assumed to reach back past the window. The endpoint returns releases in
    creation order, newest first, which is the order the ancestry walk consumes.

    The `--jq` projection is what makes the paginated answer parseable: without
    it `gh api --paginate` emits one JSON ARRAY PER PAGE, concatenated, so a
    single document parse succeeds on a one-page answer and fails on every
    multi-page one — a reader that works until upstream grows. With it, each
    release arrives as one compact object on its own line.

    THE METHOD IS DECLARED BECAUSE THE PAGE SIZE IS A PARAMETER, and leaving it
    inferred inverted this read into a write. `gh api`'s own help states the
    rule: "The default HTTP request method is `GET` normally and `POST` if any
    parameters were added." So `-F per_page=100` with no `--method` is sent to
    `POST repos/fabro-sh/fabro/releases` — the CREATE-A-RELEASE endpoint of a
    third party's repository — carrying `{"per_page":100}` as a request body.
    That cannot return releases, so the gather reports the upstream surface as
    unobservable, and because this gate is first in the pre-dispatch wall and
    fails closed, EVERY dispatch in this repository is refused before claim
    while each attempt issues an unauthorized write against upstream. Measured
    2026-10-11 off `gh`'s own transport error, which names the verb it chose:
    the unqualified form reported `Post "…/repos/fabro-sh/fabro/releases"` and
    this form reports `Get "…/repos/fabro-sh/fabro/releases?per_page=100"`.
    Declaring the method also moves the page size into the QUERY STRING, which
    is where this endpoint reads it from.

    `compare_argv` next door needs no such declaration because it carries no
    parameters, and a deliberate WRITE declares its verb the same way this read
    does — see `_dispatcher_publish_branch_preserve.create_ref_argv`. The rule
    to preserve is the relationship, not this spelling: a `gh api` argv carrying
    body parameters MUST declare its method, because inference resolves them to
    a POST.
    """
    return [
        "gh",
        "api",
        "--method",
        "GET",
        f"repos/{FABRO_UPSTREAM_REPO}/releases",
        "--paginate",
        "-F",
        "per_page=100",
        "--jq",
        ".[] | {tag: .tag_name, published_at: .published_at}",
    ]


def compare_argv(*, base: str, head: str) -> list[str]:
    """The forge comparison that answers whether `head` carries `base`.

    The repository is NAMED rather than left to `gh`'s `{owner}`/`{repo}`
    placeholders: those resolve against the repository the command runs in, which
    is the governed tenant, not the upstream engine.
    """
    return [
        "gh",
        "api",
        f"repos/{FABRO_UPSTREAM_REPO}/compare/{base}...{head}",
        "--jq",
        ".status",
    ]


def serving_integration_commit(
    *, factory: FactoryTarget, fabro_bin: str, runner: CommandRunner, cwd: Path
) -> str | None:
    """The integration commit `factory`'s own server reports serving, else `None`.

    `None` is an honest unobserved answer in three cases that share one remedy:
    the client did not run, it ran and printed nothing this parser recognises, or
    its output carried no server section. Falling back to the CLIENT section
    instead would answer the wrong question with perfect confidence.
    """
    port = FabroPort(
        fabro_bin=fabro_bin,
        target=FabroTarget(server_url=factory.server),
        runner=runner,
        cwd=cwd,
    )
    result = port.version(timeout_seconds=_VERSION_TIMEOUT_SECONDS)
    if result.command.exit_code != 0:
        return None
    return _server_commit(text=result.text)


def parse_releases(*, stdout: str) -> tuple[FabroRelease, ...] | None:
    """The releases in a `--jq`-projected paginated response, in arrival order.

    `None` for a line that is not one of those objects, because a payload this
    parser only partly understood would yield a SHORT release list, and a short
    list is how a genuinely-ancestral tag disappears and a current build gets
    refused for having no base.
    """
    releases: list[FabroRelease] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        release = _release(entry=_decoded(text=stripped))
        if release is None:
            return None
        releases.append(release)
    return tuple(releases)


def resolved_base(
    *,
    observation: FabroReleaseObservation,
    serving_commit: str,
    runner: CommandRunner,
    cwd: Path,
) -> FabroRelease | None:
    """The latest-published release tag that is an ancestor of `serving_commit`.

    Candidates are consumed newest-PUBLISHED first and the FIRST ancestor found
    is the answer, because the first ancestor in that order is by construction
    the latest-published one.

    THE WALK RANGES OVER THE WHOLE OBSERVATION. The clause selects the base from
    the published release tags, full stop, so any narrower candidate set reports a
    base-less build where a base exists — see this module's docstring for the
    measured carrier case a 40-candidate cap mis-refused.

    THE SORT STILL RUNS BEFORE THE WALK, and that order remains load-bearing even
    with nothing truncated: publication order is what makes the FIRST ancestor
    found the LATEST-PUBLISHED one, which is the base the clause names. Walking
    the forge's own enumeration instead would return whichever ancestor happened
    to be created first.
    """
    for release in releases_by_publication(releases=observation.releases):
        if _is_ancestor(tag=release.tag, head=serving_commit, runner=runner, cwd=cwd):
            return release
    return None


def fabro_currency_subject(
    *,
    factory: FactoryTarget,
    fabro_bin: str,
    runner: CommandRunner,
    cwd: Path,
    reading: ObservationReading,
) -> FabroCurrencySubject:
    """Assemble one target's subject from the engine read and a release reading.

    The release reading is passed IN rather than taken here because it is SHARED
    across every target in one dispatch: two targets are evaluated against their
    own serving commits, but there is only one upstream, and re-reading it per
    target would spend the same paginated round trip twice for one answer.
    """
    commit = serving_integration_commit(
        factory=factory, fabro_bin=fabro_bin, runner=runner, cwd=cwd
    )
    # A READING THAT FAILED RESOLVES NO BASE, even when it carries releases.
    # That is the whole point of checking `failure` here rather than only
    # `observation`: a STALE record is handed back populated, so an ancestry
    # walk over it finds a perfectly plausible base and the window comparison
    # then passes on expired evidence. Refusing to resolve a base from it is
    # what keeps the staleness decisive instead of advisory.
    if reading.observation is None or reading.failure is not None or commit is None:
        return FabroCurrencySubject(
            target=factory.name,
            serving_commit=commit,
            base=None,
            observation=reading.observation,
            unobservable_detail=_gather_detail(factory=factory, reading=reading),
            observation_failure=reading.failure,
        )
    base = resolved_base(
        observation=reading.observation, serving_commit=commit, runner=runner, cwd=cwd
    )
    return FabroCurrencySubject(
        target=factory.name,
        serving_commit=commit,
        base=base,
        observation=reading.observation,
        unobservable_detail=(
            None
            if base is not None
            else _no_ancestor_detail(examined=len(reading.observation.releases))
        ),
        observation_failure=None,
    )


def _gather_detail(*, factory: FactoryTarget, reading: ObservationReading) -> str:
    """Which measurement stopped the gather, naming the observation fault first.

    The release reading is named ahead of the serving build because an absent
    observation makes the base question unanswerable for EVERY target, while an
    unidentified serving build is a fault in one — so reporting the per-target
    fault while the shared one stands would send the operator to the wrong host.
    """
    if reading.failure is not None:
        return reading.failure
    return _unidentified_detail(factory=factory)


def _unidentified_detail(*, factory: FactoryTarget) -> str:
    return (
        "the selected factory's serving build could not be identified:"
        f" `fabro version` against {factory.server or 'the ambient server'} reported no"
        " server build commit"
    )


def _no_ancestor_detail(*, examined: int) -> str:
    """The absence, stated over the population that was actually searched.

    `examined` is the observation's own size rather than a constant, because the
    scope sentence has to move with what the walk looked at — a fixed number here
    would keep reading correct after a narrower candidate set made it false.
    """
    return (
        "the serving integration commit has no published release-tag ancestor among the"
        f" {examined} {FABRO_UPSTREAM_REPO} releases in the current observation"
    )


def _is_ancestor(*, tag: str, head: str, runner: CommandRunner, cwd: Path) -> bool:
    result = runner.run(
        argv=compare_argv(base=tag, head=head),
        cwd=cwd,
        timeout_seconds=_COMPARE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return False
    return result.stdout.strip() in _CONTAINING_STATUSES


def _server_commit(*, text: str) -> str | None:
    decoded = _decoded(text=text)
    if not isinstance(decoded, dict):
        return None
    server = cast("dict[str, object]", decoded).get(_SERVER_KEY)
    if not isinstance(server, dict):
        return None
    commit = cast("dict[str, object]", server).get("git_sha")
    if not isinstance(commit, str) or _COMMIT_PATTERN.match(commit) is None:
        return None
    return commit


def _decoded(*, text: str) -> object:
    decoded = attempt(action=lambda: json.loads(text), exceptions=(ValueError,))
    return None if isinstance(decoded, AttemptFailure) else decoded


def _release(*, entry: object) -> FabroRelease | None:
    if not isinstance(entry, Mapping):
        return None
    fields = cast("Mapping[str, object]", entry)
    tag = fields.get("tag")
    published_at = _instant(value=fields.get("published_at"))
    if not isinstance(tag, str) or published_at is None:
        return None
    return FabroRelease(tag=tag, published_at=published_at)


def _instant(*, value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    parsed = attempt(action=lambda: datetime.fromisoformat(normalized), exceptions=(ValueError,))
    if isinstance(parsed, AttemptFailure):
        return None
    return None if parsed.tzinfo is None else parsed
