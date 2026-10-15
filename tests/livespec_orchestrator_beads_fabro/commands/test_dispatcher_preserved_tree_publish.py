"""The transport the preserved-tree publication uses, and the one it must not."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    PreservedTree,
    publish_preserved_tree,
)
from livespec_orchestrator_beads_fabro.commands._fabro_run_files import RunFile

_BASE_COMMIT = "5d511335aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


@dataclass(kw_only=True)
class _ApiRunner:
    """Answer every `gh api` call with a plausible object name, recording argv."""

    argvs: list[list[str]] = field(default_factory=list)
    shas: list[str] = field(
        default_factory=lambda: [
            "7ee7ee7ee7ee7ee7ee7ee7ee7ee7ee7ee7ee7ee7",
            "b10bb10bb10bb10bb10bb10bb10bb10bb10bb10b",
            "7ree7ree7ree7ree7ree7ree7ree7ree7ree7ree7",
            "c0mm1tc0mm1tc0mm1tc0mm1tc0mm1tc0mm1tc0mm",
            "",
        ]
    )

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd
        _ = timeout_seconds
        _ = env
        _ = stdin
        self.argvs.append(list(argv))
        answer = self.shas[len(self.argvs) - 1] if len(self.argvs) <= len(self.shas) else ""
        return CommandResult(exit_code=0, stdout=f"{answer}\n", stderr="")


def _endpoints(*, argvs: list[list[str]]) -> list[str]:
    """The forge path each call addressed, in call order."""
    return [token for argv in argvs for token in argv if token.startswith("/repos/")]


def test_the_publication_creates_blobs_a_tree_a_commit_and_a_ref_through_the_git_data_api(
    tmp_path: Path,
) -> None:
    runner = _ApiRunner()
    published = publish_preserved_tree(
        runner=runner,
        repo=tmp_path,
        work_item_id="bd-ib-na2xvm",
        base_commit=_BASE_COMMIT,
        files=(RunFile(path="a.py", content=b"changed\n", mode="100644"),),
        message="preserved tree",
    )
    assert isinstance(published, PreservedTree), published
    assert _endpoints(argvs=runner.argvs) == [
        f"/repos/{{owner}}/{{repo}}/git/commits/{_BASE_COMMIT}",
        "/repos/{owner}/{repo}/git/blobs",
        "/repos/{owner}/{repo}/git/trees",
        "/repos/{owner}/{repo}/git/commits",
        "/repos/{owner}/{repo}/git/refs",
    ]
    assert all(argv[:2] == ["gh", "api"] for argv in runner.argvs), runner.argvs
    assert not any("push" in token for argv in runner.argvs for token in argv), runner.argvs
    assert not any(token == "git" for argv in runner.argvs for token in argv), runner.argvs
