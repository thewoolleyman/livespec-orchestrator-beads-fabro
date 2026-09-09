"""The factory-bypass audit's `gh` transport and wire-shape reduction.

One injectable seam (`GhSeam`) plus the two reads the audit makes through it:
the merged-PR window (`gh pr list`) and the audited repository's own
`pyproject.toml` (`gh api .../contents/pyproject.toml`), which is where the
per-repository product-path prefixes are declared. Both reads take the SAME
`--repo` selection, so the window and the classifier can never end up pointed
at two different repositories.

`fetch_repo_pyproject` is fail-soft by design: a repository with no
`pyproject.toml` is a legitimate audit target, and this is a report-only
surface, so a `gh` non-zero exit yields `None` and the caller falls back to the
declared fleet default rather than aborting the whole audit. It catches
`CalledProcessError` ONLY — a missing `gh`, an auth failure, or any other
`OSError` still propagates, because those mean the merged-PR window itself is
unreadable and a report built on them would be a clean, plausible, wrong answer.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Protocol

__all__: list[str] = [
    "DEFAULT_GH_SEAM",
    "GhSeam",
    "PullRequest",
    "fetch_merged_prs",
    "fetch_repo_pyproject",
    "parse_pr_list",
]

_GH_TIMEOUT_SECONDS = 60
# `gh api` substitutes `{owner}`/`{repo}` from the current directory's
# repository, which is exactly the no-`--repo` default `gh pr list` takes.
_CURRENT_REPO_PLACEHOLDER = "{owner}/{repo}"


@dataclass(frozen=True, slots=True, kw_only=True)
class PullRequest:
    """A merged PR reduced to the fields the audit reasons over."""

    number: int
    title: str
    author_login: str
    files: tuple[str, ...]
    labels: tuple[str, ...]
    commit_messages: tuple[str, ...]


class GhRunner(Protocol):
    """Seam: run a `gh` argv and return its stdout."""

    def __call__(self, *, args: list[str]) -> str: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class GhSeam:
    """The injectable `gh` transport (defaulted to the real subprocess)."""

    run: GhRunner


def _default_gh_run(*, args: list[str]) -> str:  # pragma: no cover
    """Production `gh` seam — integration-covered, never hit hermetically."""
    completed = subprocess.run(  # noqa: S603
        ["gh", *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        timeout=_GH_TIMEOUT_SECONDS,
    )
    return completed.stdout


DEFAULT_GH_SEAM = GhSeam(run=_default_gh_run)


def parse_pr_list(*, stdout: str) -> list[PullRequest]:
    """Parse `gh pr list --json number,title,author,labels,files,commits` stdout."""
    raw = json.loads(stdout)
    prs: list[PullRequest] = []
    for entry in raw:
        author = entry.get("author")
        login = "" if author is None else str(author.get("login", ""))
        prs.append(
            PullRequest(
                number=int(entry["number"]),
                title=str(entry.get("title", "")),
                author_login=login,
                files=tuple(str(item["path"]) for item in entry.get("files", ())),
                labels=tuple(str(label["name"]) for label in entry.get("labels", ())),
                commit_messages=tuple(
                    str(commit.get("messageHeadline", ""))
                    + "\n"
                    + str(commit.get("messageBody", ""))
                    for commit in entry.get("commits", ())
                ),
            )
        )
    return prs


def fetch_merged_prs(
    *,
    repo: str | None,
    limit: int,
    merged_since: str | None,
    seam: GhSeam = DEFAULT_GH_SEAM,
) -> list[PullRequest]:
    """Fetch the recently-merged PR window through the `gh` seam."""
    args = [
        "pr",
        "list",
        "--state",
        "merged",
        "--limit",
        str(limit),
        "--json",
        "number,title,author,labels,files,commits",
    ]
    if repo is not None:
        args += ["--repo", repo]
    if merged_since is not None:
        args += ["--search", f"merged:>={merged_since}"]
    return parse_pr_list(stdout=seam.run(args=args))


def fetch_repo_pyproject(*, repo: str | None, seam: GhSeam = DEFAULT_GH_SEAM) -> str | None:
    """Fetch the audited repository's `pyproject.toml`, or None when it has none."""
    slug = _CURRENT_REPO_PLACEHOLDER if repo is None else repo
    try:
        return seam.run(
            args=[
                "api",
                f"repos/{slug}/contents/pyproject.toml",
                "-H",
                "Accept: application/vnd.github.raw",
            ]
        )
    except subprocess.CalledProcessError:
        return None
