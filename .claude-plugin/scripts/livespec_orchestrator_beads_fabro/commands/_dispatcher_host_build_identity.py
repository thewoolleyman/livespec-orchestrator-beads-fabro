"""The BUILD IDENTITY a host-leg Proof of Done record names, written and read.

The host-leg clause of `SPECIFICATION/contracts.md` (v115) requires a host record
to name, beyond the record structure every proof record shares, "the BUILD
IDENTITY exercised: the release tag and the installed build identifier, or, where
no release applies, the default-branch commit exercised". The host-captured leg of
its post-merge acceptance section then makes that identity load-bearing: "the
named release tag MUST contain the merge commit on the default branch ... where no
release applies the record names the default-branch commit exercised and the pass
verifies the same ancestry", while "the installed build identifier is recorded,
not verified".

WHY ONE MODULE OWNS BOTH DIRECTIONS. The posting primitive RENDERS this section
and the acceptance pass PARSES it back out of a published comment. Splitting the
two would let a renderer and a reader disagree about a label's spelling, and the
disagreement is invisible in the direction that matters: every record would still
be published, every record would still parse as naming NO build, and the pass
would report perfectly good host proof as not evidence — a refusal indistinguishable
from the one a genuinely unidentified build earns.

WHY `containment_ref` IS A PROPERTY AND NOT THE CALLER'S CHOICE. The clause names
the ref the pass checks against in two arms — the release tag where a release
applies, the default-branch commit where none does — and the installed build
identifier in NEITHER. A caller picking the ref itself would eventually aim the
check at the installed identifier, which is not a git ref at all and would make
the containment read fail for a reason that reads like a missing build. The arms
live here, next to the parse that recovers them.

WHY A MISSING SECTION IS `None` RATHER THAN AN EMPTY VALUE. The evidence rule
treats a record naming no build as not evidence, and that refusal has to be
distinguishable from a record whose labels were present but blank — the first is
a record published without the clause's required field, the second a publisher
who wrote the field and left it empty. Both are refused, but an operator reading
the refusal needs to know which one to fix, so the reader answers `None` for the
first and a value object for the second.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__: list[str] = [
    "BUILD_IDENTITY_HEADING",
    "COMMIT_LABEL",
    "INSTALLED_BUILD_LABEL",
    "NO_RELEASE",
    "RELEASE_TAG_LABEL",
    "BuildIdentity",
    "build_identity_in",
]

BUILD_IDENTITY_HEADING = "Build identity"
RELEASE_TAG_LABEL = "Release tag"
INSTALLED_BUILD_LABEL = "Installed build"
COMMIT_LABEL = "Commit"
# The literal the clause reserves for "no release applies to this work". It is
# matched case-insensitively on read and written lower-case, because a record is
# prose and a publisher who capitalised the sentence should not thereby have
# named a release tag called `None`.
NO_RELEASE = "none"

# The closed label set the reader recognises. Any other bullet in the body is
# prose — the record carries bullets for the proof mode, the governing scenario
# and the reproduction verdict too — and must not become a build-identity field.
_LABELS = frozenset({RELEASE_TAG_LABEL, INSTALLED_BUILD_LABEL, COMMIT_LABEL})

# A bullet is the whole of the grammar: `- <label>: <value>`, anchored at the
# start of its own line. Matching a label ANYWHERE in the body would read a
# reproduction step's narrative — "confirm the commit ... is installed" — as the
# build identity, which is the fail-OPEN direction: the containment check would
# then be aimed at whatever ref the prose happened to mention.
_BULLET = re.compile(r"^\s*-\s+(?P<label>[^:]+):(?P<value>.*)$")


@dataclass(frozen=True, kw_only=True)
class BuildIdentity:
    """One host record's claim about which build its steps exercised.

    `release_tag` is `None` both for a record that states `release: none` and for
    one that names no release bullet at all. The two are the same fact for the
    containment check — there is no tag to check against, so the commit is the ref
    — and they are told apart by the record's own text, which is where a reader
    looking for a malformed publish should be looking anyway.
    """

    release_tag: str | None
    installed_build: str | None
    commit: str | None

    @property
    def containment_ref(self) -> str | None:
        """The git ref the acceptance pass checks the merge commit against.

        `None` when the record names neither a release tag nor a commit, which the
        pass treats as not evidence rather than as containment it may skip: a check
        with nothing to aim at has not passed.
        """
        if self.release_tag is not None:
            return self.release_tag
        return self.commit

    def render(self) -> str:
        """The section's own text, with no trailing newline.

        The release bullet is ALWAYS written, carrying the reserved literal where
        no release applies, so a reader can tell a record that declared no release
        from one whose publisher omitted the field. The other two bullets are
        written only when there is something to say, because an empty bullet
        asserts nothing and the clause asks for the identity exercised rather than
        for a fixed form.
        """
        bullets = (
            (RELEASE_TAG_LABEL, NO_RELEASE if self.release_tag is None else self.release_tag),
            (INSTALLED_BUILD_LABEL, self.installed_build),
            (COMMIT_LABEL, self.commit),
        )
        lines = [f"## {BUILD_IDENTITY_HEADING}", ""]
        lines.extend(f"- {label}: {value}" for label, value in bullets if value is not None)
        return "\n".join(lines)


def build_identity_in(*, body: str) -> BuildIdentity | None:
    """The build identity one record body names, or `None` when it names none.

    The FIRST bullet carrying each label wins. A record is append-only and a
    correction is a new record, so a second bullet with the same label inside the
    proof of a later assertion is quoted output rather than a revision of the
    identity this record claims.
    """
    fields = _bullet_fields(body=body)
    if not fields:
        return None
    release = fields.get(RELEASE_TAG_LABEL)
    return BuildIdentity(
        release_tag=None if release is None or release.casefold() == NO_RELEASE else release,
        installed_build=fields.get(INSTALLED_BUILD_LABEL),
        commit=fields.get(COMMIT_LABEL),
    )


def _bullet_fields(*, body: str) -> dict[str, str]:
    """Every build-identity label the body carries as its own bullet, first wins.

    A label whose value is blank is DROPPED rather than recorded as an empty
    string: the caller distinguishes "no build identity" from "a build identity
    with nothing in it" on whether this mapping is empty, and a blank value
    recorded as present would make a record that named only empty labels look like
    one that named a build.
    """
    fields: dict[str, str] = {}
    for line in body.splitlines():
        bullet = _BULLET.match(line)
        if bullet is None:
            continue
        label = bullet.group("label").strip()
        value = bullet.group("value").strip()
        if label not in _LABELS or not value or label in fields:
            continue
        fields[label] = value
    return fields
