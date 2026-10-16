"""The release-repository resolution ladder the archive gate reads records through.

The plan-record clause of `SPECIFICATION/contracts.md` (v148) enumerates five
conditions, and this module is the ladder that decides which one a record meets:
the explicitly named repository, the bare name the forge reports, the bare name it
does not, the record naming no identifier at all, and every read that could not be
taken. `_plan_release_repository` owns the forms and the reading vocabulary,
`_plan_release_forge` owns the three reads, and `_plan_proof_leg` grades what comes
back — so the arms live here, where they can be exercised without a forge.

THE SAME FORGE ANSWER HAS OPPOSITE CONSEQUENCES ON TWO ARMS, which is the whole
reason the ladder is a ladder. A `404` for a BARE `<repository>` means "this word
is not a repository of the governed owner", and the clause routes it to the
governed repository. A `404` for an EXPLICIT `<owner>/<repository>` rejects, and
the clause says so twice — it "MUST NOT fall back to the governed repository".
Collapsing them in either direction is a silent defect: the first direction
rejects every record whose identifier opens with a version string, and the second
judges a record against a repository whose releases its steps never ran.

EVERY ARM THAT CANNOT MEASURE REJECTS, AND NONE FALLS BACK. An unreadable governed
identity, an unanswerable existence probe and a refused tag read all produce
`UnreadableRelease`. That is the reversal this clause landed: the retired reading
returned an empty tag set for a failure, and an empty set MEANS "no release
applies", so a blinded gauge admitted every record. A gauge that falls back when
blinded is the same defect wearing the fallback's clothes — it would make an
unreachable forge the cheapest way to have a sibling's release judged against the
governed repository's tags.

THE GOVERNED IDENTITY IS READ ONCE, AT CONSTRUCTION. Every arm needs it — the
governed repository's own tag read, and the owner a bare name resolves under — and
two reads of it taken at different moments can disagree while both look
well-formed. It is also the one read whose failure settles every record on the
timeline at once, so resolving it first is what lets that refusal be raised before
any other read is aimed anywhere.

WHY THE MEMO IS KEYED ON THE RECORD'S OWN WORD AND NOT ON THE RESOLVED REPOSITORY.
A timeline carries one record per capture and per replay, each naming the same
build identifier, so the memo's job is to stop N records costing N resolutions.
Keying it on the RESOLVED repository would require performing the resolution to
find the key, which is the thing being memoized. The cost of keying on the word is
that two different words resolving to the governed repository read its tags twice
— at most one extra read per distinct word on one timeline, and the empty key the
no-identifier arm uses cannot collide with any word, since a bare word is
non-empty by construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._plan_release_forge import (
    ForgeReadFailure,
    governed_repository_identity,
    repository_exists,
    repository_release_tags,
)
from livespec_orchestrator_beads_fabro.commands._plan_release_repository import (
    BareRepository,
    ExplicitRepository,
    ReleaseReading,
    ReleaseTags,
    UnreadableRelease,
    release_repository_in,
)

__all__: list[str] = [
    "ForgeReleaseReader",
    "forge_release_reader",
]

# The memo key for a record naming no release repository of its own. It cannot
# collide with a word's key: a bare `<repository>` is non-empty by construction and
# an `<owner>/<repository>` carries a separator.
_GOVERNED_KEY = ""


@dataclass(frozen=True, kw_only=True)
class ForgeReleaseReader:
    """One archive's release readings, resolved from the forge and memoized.

    FROZEN with a mutable `readings` map, which is the usual shape here: the
    reader's inputs are fixed for the life of one archive and only the memo
    accumulates. `governed` is resolved by `forge_release_reader` rather than
    inside `reading`, so one unreadable identity settles every record on the
    timeline from one read.
    """

    project_root: Path
    runner: CommandRunner
    governed: ExplicitRepository | ForgeReadFailure
    readings: dict[str, ReleaseReading] = field(default_factory=dict)

    def reading(self, *, body: str) -> ReleaseReading:
        """What the forge says about the release repository this record body names."""
        named = release_repository_in(body=body)
        key = _memo_key(named=named)
        memoized = self.readings.get(key)
        if memoized is not None:
            return memoized
        resolved = _resolved_reading(reader=self, named=named)
        self.readings[key] = resolved
        return resolved


def forge_release_reader(*, project_root: Path, runner: CommandRunner) -> ForgeReleaseReader:
    """A reader for one archive, with the governed repository's identity resolved.

    The identity read happens HERE rather than lazily inside `reading`, because it
    is the one input every arm shares: resolving it once is the resolve-once
    discipline this package applies to every other multi-consumer fact, and two
    readings of it taken a moment apart could disagree while both parsed.
    """
    return ForgeReleaseReader(
        project_root=project_root,
        runner=runner,
        governed=governed_repository_identity(project_root=project_root, runner=runner),
    )


def _memo_key(*, named: ExplicitRepository | BareRepository | None) -> str:
    """The key one record's own claim about its release repository is memoized under."""
    if named is None:
        return _GOVERNED_KEY
    if isinstance(named, ExplicitRepository):
        return named.name
    return named.repository


def _resolved_reading(
    *, reader: ForgeReleaseReader, named: ExplicitRepository | BareRepository | None
) -> ReleaseReading:
    """Which repository this record is judged against, and what the forge said of it.

    The unreadable-identity arm comes FIRST and names the CHECKOUT rather than a
    repository: with no identity, the forge that hosts the governed repository is
    unknown, so there is no repository name to cite and no later read that could be
    aimed anywhere. The clause still requires the refusal to name what the gate
    tried to read, and the checkout is what it tried to read it from.
    """
    governed = reader.governed
    if isinstance(governed, ForgeReadFailure):
        return UnreadableRelease(repository=reader.project_root.name, failure=governed.detail)
    if named is None:
        return _tags_reading(reader=reader, repository=governed.name)
    return _named_reading(reader=reader, named=named, governed=governed)


def _named_reading(
    *,
    reader: ForgeReleaseReader,
    named: ExplicitRepository | BareRepository,
    governed: ExplicitRepository,
) -> ReleaseReading:
    """Resolve a record that NAMED a repository, by asking the forge whether it exists.

    A bare name is resolved under the governed repository's own forge owner, which
    is what the clause means by "the bare form denoting the same forge owner as the
    governed repository's `origin` remote".

    The probe's three answers are kept apart deliberately. An unanswerable probe is
    `UnreadableRelease` and never a fallback, because "I could not ask" and "the
    forge says no" support opposite conclusions and only the second is the clause's
    fallback condition. And a `404` on an EXPLICIT name rejects naming that
    repository — never the governed one — so the refusal points at the repository
    the record actually claimed.
    """
    explicit = (
        named
        if isinstance(named, ExplicitRepository)
        else ExplicitRepository(owner=governed.owner, repository=named.repository)
    )
    exists = repository_exists(
        repository=explicit.name, project_root=reader.project_root, runner=reader.runner
    )
    if isinstance(exists, ForgeReadFailure):
        return UnreadableRelease(repository=explicit.name, failure=exists.detail)
    if exists:
        return _tags_reading(reader=reader, repository=explicit.name)
    if isinstance(named, ExplicitRepository):
        return UnreadableRelease(
            repository=explicit.name,
            failure=(
                f"the forge reports no repository {explicit.name}, which this record"
                " names explicitly, so no release repository could be read and the"
                " governed repository is not judged in its place"
            ),
        )
    return _tags_reading(reader=reader, repository=governed.name)


def _tags_reading(*, reader: ForgeReleaseReader, repository: str) -> ReleaseReading:
    """One repository's release tags as the forge reports them, or why it could not.

    The empty set rides through as a successful `ReleaseTags`, because the forge
    saying a repository carries no tag is the clause's "no release applies"
    condition — the one answer that must stay distinguishable from a failed read.
    """
    tags = repository_release_tags(
        repository=repository, project_root=reader.project_root, runner=reader.runner
    )
    if isinstance(tags, ForgeReadFailure):
        return UnreadableRelease(repository=repository, failure=tags.detail)
    return ReleaseTags(repository=repository, tags=tags)
