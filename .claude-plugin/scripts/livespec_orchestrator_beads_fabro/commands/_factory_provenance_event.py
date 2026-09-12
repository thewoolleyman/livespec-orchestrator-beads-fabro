"""The forge-side inputs of the factory-provenance merge gate.

The gate reads exactly two things, and this module is where both come from:
the Actions `pull_request` event payload at `GITHUB_EVENT_PATH` (the author
login, the label names, and the base/head shas), and the pull request's own
changed-path list. Nothing here reads the ledger — that is what "hermetic in
the forge sense" means for R6, and it is why a gate wired into `ci-green` can
never be blocked by a tenant outage.

WHY AN UNREADABLE PAYLOAD IS A REFUSAL, NOT A PASS. `parse_event` returns
`None` for a payload it cannot reduce — a missing file, non-JSON bytes, or an
event that is not a pull request — and its caller turns that into a non-zero
exit naming what it could not read. A gauge that fails OPEN when it cannot
observe its input converts every refusal into a pass the moment someone
breaks the input, which is the standing temptation the repository's own
verification discipline calls out by name. A provenance wall that green-lights
a pull request it never looked at is worse than no wall at all, because the
record then reads as a decision.

WHY THE DIFF RANGE IS `base...head`. The two-dot form compares the two
commits directly, so a head branch that has not been rebased onto a moved base
reports every path the base moved as though the pull request had changed it.
The three-dot form diffs from the MERGE BASE, which is exactly the set of
paths the pull request itself proposes — the same set the forge shows in the
"Files changed" tab. `--changed-file` on the check's CLI bypasses this read
entirely so the decision can be tested without a git repository.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "PullRequestEvent",
    "diff_range",
    "parse_event",
    "read_changed_paths",
    "read_event",
]

_DIFF_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True, kw_only=True)
class PullRequestEvent:
    """A `pull_request` event payload reduced to the fields the gate reasons over."""

    author_login: str
    labels: tuple[str, ...]
    base_sha: str
    head_sha: str


def _mapping(*, value: object) -> dict[str, object]:
    """A nested JSON object as a typed mapping; absent or non-object reads as empty."""
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _text(*, mapping: dict[str, object], key: str) -> str:
    """A string field of a JSON object; absent or non-string reads as empty."""
    value = mapping.get(key)
    return value if isinstance(value, str) else ""


def _label_names(*, pull_request: dict[str, object]) -> tuple[str, ...]:
    """The pull request's label names, in payload order."""
    raw = pull_request.get("labels")
    if not isinstance(raw, list):
        return ()
    return tuple(
        _text(mapping=_mapping(value=entry), key="name") for entry in cast("list[object]", raw)
    )


def parse_event(*, payload_text: str) -> PullRequestEvent | None:
    """Reduce a `pull_request` event payload, or None when it is not one."""
    try:
        parsed: object = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    raw_pull_request = cast("dict[str, object]", parsed).get("pull_request")
    if not isinstance(raw_pull_request, dict):
        return None
    pull_request = cast("dict[str, object]", raw_pull_request)
    return PullRequestEvent(
        author_login=_text(mapping=_mapping(value=pull_request.get("user")), key="login"),
        labels=_label_names(pull_request=pull_request),
        base_sha=_text(mapping=_mapping(value=pull_request.get("base")), key="sha"),
        head_sha=_text(mapping=_mapping(value=pull_request.get("head")), key="sha"),
    )


def read_event(*, path: Path) -> PullRequestEvent | None:
    """Read and reduce the event payload at `path`, or None when unreadable."""
    try:
        payload_text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_event(payload_text=payload_text)


def diff_range(*, event: PullRequestEvent) -> str:
    """The merge-base-relative range naming the paths this pull request proposes."""
    return f"{event.base_sha}...{event.head_sha}"


def read_changed_paths(
    *,
    event: PullRequestEvent,
    repo: Path,
    runner: CommandRunner,
) -> tuple[str, ...] | None:
    """The pull request's changed paths, or None when the diff could not be read."""
    diff = runner.run(
        argv=["git", "diff", "--name-only", diff_range(event=event)],
        cwd=repo,
        timeout_seconds=_DIFF_TIMEOUT_SECONDS,
    )
    if diff.exit_code != 0:
        return None
    return tuple(line.strip() for line in diff.stdout.splitlines() if line.strip())
