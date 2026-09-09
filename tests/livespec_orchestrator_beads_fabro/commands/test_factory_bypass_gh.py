"""Hermetic tests for the factory-bypass audit's `gh` transport.

No network: the transport is an injected `GhSeam` fake returning canned stdout,
mirroring how sibling command modules fake their side-effecting seams. The
argv assertions are the load-bearing ones — a merged-PR window and a
product-path declaration read from two DIFFERENT repositories would produce a
clean, plausible, wrong audit, so both reads are asserted to carry the same
`--repo` selection.
"""

from __future__ import annotations

import json
import subprocess

from livespec_orchestrator_beads_fabro.commands._factory_bypass_gh import (
    GhSeam,
    PullRequest,
    fetch_merged_prs,
    fetch_repo_pyproject,
    parse_pr_list,
)

_PRODUCT = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/foo.py"


def _seam(*, stdout: str, recorder: list[list[str]]) -> GhSeam:
    def _run(*, args: list[str]) -> str:
        recorder.append(args)
        return stdout

    return GhSeam(run=_run)


def _failing_seam(*, recorder: list[list[str]]) -> GhSeam:
    def _run(*, args: list[str]) -> str:
        recorder.append(args)
        raise subprocess.CalledProcessError(returncode=1, cmd=["gh", *args])

    return GhSeam(run=_run)


# --------------------------------------------------------------------------
# parse_pr_list — the gh JSON reduction
# --------------------------------------------------------------------------


def test_parse_pr_list_reduces_fields_including_commit_messages() -> None:
    stdout = json.dumps(
        [
            {
                "number": 100,
                "title": "feat: x",
                "author": {"login": "thewoolleyman"},
                "files": [{"path": _PRODUCT}, {"path": "README.md"}],
                "labels": [{"name": "enhancement"}],
                "commits": [
                    {"messageHeadline": "feat: x", "messageBody": "Factory-Override: reason"}
                ],
            },
            {"number": 101, "author": None, "files": [], "labels": []},
        ]
    )
    prs = parse_pr_list(stdout=stdout)
    assert prs[0] == PullRequest(
        number=100,
        title="feat: x",
        author_login="thewoolleyman",
        files=(_PRODUCT, "README.md"),
        labels=("enhancement",),
        commit_messages=("feat: x\nFactory-Override: reason",),
    )
    # Missing author / title / commits default to empty; a null author yields "".
    assert prs[1] == PullRequest(
        number=101,
        title="",
        author_login="",
        files=(),
        labels=(),
        commit_messages=(),
    )


def test_parse_pr_list_defaults_absent_commit_message_fields() -> None:
    stdout = json.dumps([{"number": 1, "author": None, "files": [], "labels": [], "commits": [{}]}])
    assert parse_pr_list(stdout=stdout)[0].commit_messages == ("\n",)


# --------------------------------------------------------------------------
# fetch_merged_prs — argv construction over the seam
# --------------------------------------------------------------------------


def test_fetch_merged_prs_default_window_requests_commits() -> None:
    recorder: list[list[str]] = []
    prs = fetch_merged_prs(
        repo=None,
        limit=100,
        merged_since=None,
        seam=_seam(stdout="[]", recorder=recorder),
    )
    assert prs == []
    args = recorder[0]
    assert args[:6] == ["pr", "list", "--state", "merged", "--limit", "100"]
    assert args[args.index("--json") + 1] == "number,title,author,labels,files,commits"
    assert "--repo" not in args
    assert "--search" not in args


def test_fetch_merged_prs_repo_and_since() -> None:
    recorder: list[list[str]] = []
    _ = fetch_merged_prs(
        repo="thewoolleyman/livespec-dev-tooling",
        limit=25,
        merged_since="2026-06-15",
        seam=_seam(stdout="[]", recorder=recorder),
    )
    args = recorder[0]
    assert args[args.index("--repo") + 1] == "thewoolleyman/livespec-dev-tooling"
    assert args[args.index("--search") + 1] == "merged:>=2026-06-15"
    assert args[args.index("--limit") + 1] == "25"


# --------------------------------------------------------------------------
# fetch_repo_pyproject — the per-repository declaration read
# --------------------------------------------------------------------------


def test_fetch_repo_pyproject_targets_the_selected_repository() -> None:
    recorder: list[list[str]] = []
    text = fetch_repo_pyproject(
        repo="thewoolleyman/livespec-dev-tooling",
        seam=_seam(stdout="[tool.livespec_dev_tooling]\n", recorder=recorder),
    )
    assert text == "[tool.livespec_dev_tooling]\n"
    assert recorder[0] == [
        "api",
        "repos/thewoolleyman/livespec-dev-tooling/contents/pyproject.toml",
        "-H",
        "Accept: application/vnd.github.raw",
    ]


def test_fetch_repo_pyproject_uses_the_current_repo_placeholder() -> None:
    recorder: list[list[str]] = []
    _ = fetch_repo_pyproject(repo=None, seam=_seam(stdout="", recorder=recorder))
    assert recorder[0][1] == "repos/{owner}/{repo}/contents/pyproject.toml"


def test_fetch_repo_pyproject_is_fail_soft_on_a_missing_file() -> None:
    """A repository with no pyproject.toml is a legitimate target, not an abort."""
    recorder: list[list[str]] = []
    assert fetch_repo_pyproject(repo="o/r", seam=_failing_seam(recorder=recorder)) is None
    assert recorder[0][0] == "api"
