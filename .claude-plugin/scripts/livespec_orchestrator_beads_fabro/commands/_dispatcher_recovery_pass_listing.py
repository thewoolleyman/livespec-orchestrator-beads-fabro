"""The needs-human identification, taken once for a whole recovery routing pass.

`SPECIFICATION/contracts.md`, in its recovery-from-preserved-work clause, says the
identification of an item's needs-human refs "MUST be taken once per routing pass,
by one listing of the needs-human refs with their tip commit messages, and shared
by every item the pass routes". Two items released for recovery in one pass are
routed from the same origin, so the listing is the pass's and not the item's: a
second `git ls-remote` per released item spends an origin round trip on a question
the first already answered, and each one is a read that can disagree with the
other.

THE SHARING IS DONE AT THE RUNNER SEAM, NOT BY THREADING A LISTING THROUGH EVERY
READER. Five readers ask for the identification — the preference order, the
fresh and seed rulings, the recapture-exhausted route and the resume's passed-over
listing — and each already takes the pass's one `CommandRunner`. Wrapping that
runner means none of them can take a second listing by accident, including one
added later.

ONLY TWO READS ARE MEMOIZED, and both are the identification itself: the listing of
`refs/heads/needs-human/*` and the message of a ref's tip commit. A commit's message
cannot change, so its answer is safe for the pass; the listing is a snapshot the
pass takes once and every item grades against, and a FAILED listing is remembered
too, because a second attempt could answer differently for the next item and leave
the pass holding one item and routing its neighbour off a read the first never saw.
Every other command passes straight through, which includes the ancestry and
committer-time reads: those are asked about a particular set of commits, not about
the listing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)

__all__: list[str] = ["PassListingRunner"]

_LS_REMOTE_ARGC = 4
_NEEDS_HUMAN_GLOB = "refs/heads/needs-human/*"
_TIP_MESSAGE_PREFIX = ["git", "show", "-s", "--format=%B"]


@dataclass(kw_only=True)
class PassListingRunner:
    """A `CommandRunner` that answers the needs-human identification from its first read."""

    inner: CommandRunner
    _answers: dict[tuple[str, ...], CommandResult] = field(default_factory=dict)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        """Run argv through the inner runner, remembering the identification reads."""
        if not _is_identification(argv=argv):
            return self.inner.run(
                argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
            )
        key = tuple(argv)
        if key not in self._answers:
            self._answers[key] = self.inner.run(
                argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
            )
        return self._answers[key]


def _is_identification(*, argv: list[str]) -> bool:
    """Whether argv lists the needs-human refs or reads one ref tip's commit message."""
    if len(argv) == _LS_REMOTE_ARGC and argv[:2] == ["git", "ls-remote"]:
        return argv[3].endswith(_NEEDS_HUMAN_GLOB)
    return len(argv) == len(_TIP_MESSAGE_PREFIX) + 1 and argv[:-1] == _TIP_MESSAGE_PREFIX
