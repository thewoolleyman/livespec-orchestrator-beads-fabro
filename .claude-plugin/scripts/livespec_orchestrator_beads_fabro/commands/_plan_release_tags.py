"""Which release tags a governed repository carries — the archive gate's one input.

The plan-record clause of `SPECIFICATION/contracts.md` (v115) makes the release
identity CONDITIONAL on the repository: "where a release applies to the plan's
work — the governed repository carries at least one release tag — a `captured`
record taken against an unreleased tree is not evidence ... and the archive gate
MUST reject a record that states `release: none` for such a repository, or names
a release tag the repository does not carry". Both halves of that rule need the
same fact, so it is read once, here, and handed to the pure proof leg.

WHY THE WHOLE TAG SET AND NOT A COUNT. The clause asks two questions of one
input: does this repository carry at least one release tag, and is the tag this
record names one of them. A count answers only the first, after which the second
needs a second read — and two reads of a repository's tags taken at different
moments can disagree, which is the resolve-once discipline this package applies
to every other multi-consumer fact.

WHY AN UNREADABLE GIT RETURNS AN EMPTY SET, AND WHAT THAT DOES NOT WAIVE. An
empty set means "no release applies", so the release-identity half of the rule
does not fire. That is the UNMEASURED direction, and it is chosen deliberately:
the alternative — treating an unreadable tag list as "some release applies, but I
cannot say which" — rejects EVERY record as naming an unknown tag, which makes a
repository with a broken or absent git unarchivable for a reason that has nothing
to do with its proof. What the empty answer does NOT waive is the proof leg
itself: a verified plan Proof of Done record covering every assertion is still
required, so the cheap mistake here costs the release check and never the proof.

A repository with no tags at all reaches the same empty answer by a different
route, and the two are deliberately not distinguished: the clause's condition is
"carries at least one release tag", and both answers are "no".
"""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__: list[str] = [
    "release_tags_argv",
    "repository_release_tags",
]

_TAG_READ_TIMEOUT_SECONDS = 30.0


def release_tags_argv(*, project_root: Path) -> list[str]:
    """The read that enumerates one repository's tags.

    Published so a caller's own journal and tests can name the exact read rather
    than reconstructing an argv that might differ from the one run.
    """
    return ["git", "-C", str(project_root), "tag", "--list"]


def repository_release_tags(*, project_root: Path) -> frozenset[str]:
    """Every tag the repository carries, or the empty set when none can be read."""
    try:
        completed = subprocess.run(  # noqa: S603 — fixed argv, no shell.
            release_tags_argv(project_root=project_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=_TAG_READ_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    if completed.returncode != 0:
        return frozenset()
    return frozenset(line.strip() for line in completed.stdout.splitlines() if line.strip())
