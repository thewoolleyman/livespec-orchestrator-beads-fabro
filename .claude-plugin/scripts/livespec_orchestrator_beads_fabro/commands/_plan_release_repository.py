"""Which repository a plan Proof of Done record's release rule is judged against.

The plan-record clause of `SPECIFICATION/contracts.md` (v148) moved the release
rule's subject off the governed repository and onto the record: "The release rule
is judged against the RELEASE REPOSITORY of each record. Except where a later
sentence of this paragraph names the governed repository instead, the release
repository is named by the first whitespace-delimited word of the first installed
build identifier the record names when that word has the form
`<owner>/<repository>` (exactly one `/`, neither part empty) or the form of a bare
`<repository>` (no `/`), the bare form denoting the same forge owner as the
governed repository's `origin` remote."

This module owns that CONCEPT end to end on the pure side: which repository one
record names, and the vocabulary a reading of that repository comes back in. The
forge reads live in `_plan_release_forge` and the resolution ladder that composes
them in `_plan_release_reader`, for the usual reason — a parse that reached for a
subprocess could not be exercised across the forms the clause distinguishes.

WHY THE RECORD NAMES THE REPOSITORY AND NOT A CONFIGURATION KEY. A plan's work can
ship as a sibling repository's release — the livespec plan
`k3s-on-gmktec-for-vps-usage` shipped as `livespec-dev-tooling` v1.95.12 and
v1.96.1 — and the record is the only artifact that knows WHICH artifact its steps
ran. A configured release repository would be one value for a whole plan, so a
plan whose two records exercised two artifacts could state only one of them, and
the gate would judge the other against a repository its steps never touched.

WHY `None` IS AN ANSWER AND NOT A FAILURE. Three conditions share it — no
installed build identifier at all, a first word of neither form, and (downstream,
after the forge has been asked) a bare word that is no repository of the governed
owner — and the clause gives all three the same consequence: "the release
repository is the plan's governed repository". So the parse answers `None` for the
two it can settle on its own, and the resolution answers the third.

WHY THE BARE AND NEITHER-FORM ANSWERS ARE DISTINCT VALUES EVEN THOUGH BOTH CAN
END AT THE GOVERNED REPOSITORY. A bare word is a repository NAME the forge must be
ASKED about, and the answer decides between the sibling and the governed
repository; a word of neither form is not a name, so there is nothing to ask. A
parse that collapsed them would have to either ask the forge about `/repo` —
inventing a refusal out of a word the clause already excluded — or stop asking
about `livespec-dev-tooling`, which is the whole case this rule exists for.

WHY A READING IS A TWO-MEMBER UNION RATHER THAN AN OPTIONAL TAG SET. "This
repository carries no release tag, so no release applies" and "the gate could not
read this repository's release tags" are opposite facts with opposite
consequences — the first admits every record, the second rejects every record —
and an empty-set-or-`None` encoding spells them close enough that one default
turns the second into the first. That is exactly the fail-open this clause
reversed: the retired local read "returned an empty set on any failure", so an
unreadable git made every `release: none` record evidence. Both members name their
repository, because every refusal the clause requires names the repository the
gate judged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeAlias

from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    build_identity_in,
)

__all__: list[str] = [
    "BareRepository",
    "ExplicitRepository",
    "ReleaseReader",
    "ReleaseReading",
    "ReleaseTags",
    "UnreadableRelease",
    "release_repository_in",
]

# The clause's own separator, and the only one either form admits. Spelled once so
# the count test and the split cannot come to disagree about what they are
# counting.
_SEPARATOR = "/"


@dataclass(frozen=True, kw_only=True)
class ExplicitRepository:
    """A first word of the form `<owner>/<repository>`: both parts named.

    The owner is the record's own, NOT the governed repository's, which is what
    lets a record name a release on a repository of a different owner — and what
    makes a repository the forge reports does not exist a REFUSAL here rather
    than a fallback, since a name this explicit cannot have been meant as
    something else.
    """

    owner: str
    repository: str

    @property
    def name(self) -> str:
        """The `<owner>/<repository>` name every forge read and refusal cites.

        A property rather than something each caller re-joins: the name reaches
        a forge endpoint, a journal line and a refusal sentence, and a caller
        that re-joined it with the wrong separator would ask about a repository
        nobody named while reporting the one that was.
        """
        return f"{self.owner}{_SEPARATOR}{self.repository}"


@dataclass(frozen=True, kw_only=True)
class BareRepository:
    """A first word of the form `<repository>`, under the governed forge owner.

    The owner is deliberately ABSENT rather than filled in with the governed
    owner at parse time: the governed owner is read from a remote, so filling it
    in here would make this pure parse depend on a reading that can fail — and
    the failure's refusal has to name the repository, which is this value.
    """

    repository: str


@dataclass(frozen=True, kw_only=True)
class ReleaseTags:
    """The release tags one repository carries, read from its forge remote.

    An EMPTY set is a successful reading and means the clause's condition — "the
    release repository carries at least one release tag" — was not met, so no
    release applies and the rule does not fire. It is never the encoding of a
    failed read; that is `UnreadableRelease`.
    """

    repository: str
    tags: frozenset[str]


@dataclass(frozen=True, kw_only=True)
class UnreadableRelease:
    """Why the gate could not read one release repository's release tags.

    `failure` is one line naming what the read did, because the clause requires
    the rejection to name "the repository it tried to read and the failure" —
    and because the three conditions it covers (no `origin` remote, an
    unreachable forge, credentials the forge does not accept) have three
    different remedies.
    """

    repository: str
    failure: str


ReleaseReading: TypeAlias = ReleaseTags | UnreadableRelease


class ReleaseReader(Protocol):
    """The seam the proof leg reads one record's release repository through.

    A PROTOCOL rather than a callable because every argument in this tree is
    keyword-only and a `Callable` type cannot express that. It takes the record
    BODY rather than a parsed repository, so the leg never has to know that a
    repository name is parsed out of a build identity at all — which is what
    keeps the leg a pure function of records and one reader.
    """

    def reading(self, *, body: str) -> ReleaseReading:
        """What the forge said about the release repository this body names."""
        ...


def release_repository_in(*, body: str) -> ExplicitRepository | BareRepository | None:
    """The release repository one record body names, or `None` for the governed one.

    The word is taken from the FIRST installed build identifier the record names —
    `build_identity_in`'s own first-bullet-wins rule, which is the record's claim
    about the build its steps ran — and then from that identifier's first
    whitespace-delimited word, which is where a `<repository> <version>` identifier
    carries the repository.

    A word carrying more than one separator, or either part empty, has NEITHER
    form and therefore names no repository. Those are refused HERE rather than
    passed on as a repository the forge would 404: a word the clause excluded must
    not be able to produce a refusal, because the clause's answer for it is the
    governed repository.
    """
    build = build_identity_in(body=body)
    installed = None if build is None else build.installed_build
    if installed is None:
        return None
    word = installed.split()[0]
    owner, separator, repository = word.partition(_SEPARATOR)
    if separator == "":
        return BareRepository(repository=word)
    if _SEPARATOR in repository or owner == "" or repository == "":
        return None
    return ExplicitRepository(owner=owner, repository=repository)
