"""The diff-apply reseed moves a stale preserved seed onto the default branch's tip.

Every git read and write runs against a REAL local bare origin, so the merge base,
the apply and the remote reads are git's own answers. Only the forge's Git Data API
(`gh api`) is emulated, by an object-writing double that builds the same objects the
forge would: it is the one interface the Dispatcher's primary checkout cannot push
through, and the reseed uses it for every write.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_diff_apply_reseed import (
    Reseeded,
    ReseedRefusal,
    diff_apply_reseed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_ITEM = "bd-ib-5xihdt"
_SEED_REF = "refs/heads/needs-human/abc"
_BRANCH = "master"
_LINES = "".join(f"line {n}\n" for n in range(1, 21))


def _git(*, cwd: Path, args: list[str], stdin: bytes | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        input=stdin,
        capture_output=True,
        check=True,
        env={
            **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.test",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.test",
        },
    )
    return completed.stdout.decode("utf-8").strip()


def _write(*, work: Path, name: str, text: str) -> None:
    (work / name).write_text(text, encoding="utf-8")


def _commit(*, work: Path, message: str) -> str:
    _git(cwd=work, args=["add", "-A"])
    _git(cwd=work, args=["commit", "-q", "--allow-empty", "-m", message])
    return _git(cwd=work, args=["rev-parse", "HEAD"])


@dataclass(kw_only=True)
class _Repo:
    work: Path
    origin: Path
    base: str
    tip: str
    seed: str


def _publish_refs(*, repo: _Repo, seed_branch: str) -> None:
    _git(cwd=repo.work, args=["push", "-q", "origin", f"{_BRANCH}:refs/heads/{_BRANCH}"])
    _git(cwd=repo.work, args=["push", "-q", "origin", f"{seed_branch}:{_SEED_REF}"])


def _fixture(
    *,
    tmp_path: Path,
    seed_edit: Callable[[Path], None],
    tip_edit: Callable[[Path], None],
) -> _Repo:
    """A repository whose default branch moved past the seed's merge base."""
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    _ = _git(cwd=tmp_path, args=["init", "-q", "--bare", str(origin)])
    _ = _git(cwd=origin, args=["config", "uploadpack.allowAnySHA1InWant", "true"])
    _ = _git(cwd=tmp_path, args=["init", "-q", "-b", _BRANCH, str(work)])
    _ = _git(cwd=work, args=["remote", "add", "origin", str(origin)])
    _write(work=work, name="a.txt", text=_LINES)
    _write(work=work, name="b.txt", text="b\n")
    _write(work=work, name="d.txt", text="d\n")
    base = _commit(work=work, message="base")
    _ = _git(cwd=work, args=["checkout", "-q", "-b", "seed"])
    seed_edit(work)
    seed = _commit(work=work, message="seed work")
    _ = _git(cwd=work, args=["checkout", "-q", _BRANCH])
    tip_edit(work)
    _ = _commit(work=work, message="tip one")
    tip = _commit(work=work, message="tip two")
    repo = _Repo(work=work, origin=origin, base=base, tip=tip, seed=seed)
    _publish_refs(repo=repo, seed_branch="seed")
    return repo


def _clean_seed(work: Path) -> None:
    lines = _LINES.replace("line 1\n", "seed line 1\n", 1)
    _write(work=work, name="a.txt", text=lines)
    _write(work=work, name="n.txt", text="new\n")
    (work / "d.txt").unlink()


def _clean_tip(work: Path) -> None:
    _write(work=work, name="a.txt", text=_LINES.replace("line 20\n", "tip line 20\n"))
    _write(work=work, name="b.txt", text="tip b\n")


def _conflicting_tip(work: Path) -> None:
    _write(work=work, name="a.txt", text=_LINES.replace("line 1\n", "tip line 1\n", 1))
    _write(work=work, name="b.txt", text="tip b\n")


def _conflicting_seed(work: Path) -> None:
    _write(work=work, name="a.txt", text=_LINES.replace("line 1\n", "seed line 1\n", 1))
    _write(work=work, name="b.txt", text="seed b\n")


def _expected_tree(*, tmp_path: Path, repo: _Repo) -> str:
    """The tip's tree with the seed's merge-base diff applied, by `git apply --3way`."""
    scratch = tmp_path / "scratch"
    _ = _git(cwd=tmp_path, args=["clone", "-q", str(repo.origin), str(scratch)])
    _ = _git(cwd=scratch, args=["checkout", "-q", "--detach", repo.tip])
    patch = _git(cwd=repo.work, args=["diff", "--binary", repo.base, repo.seed]) + "\n"
    _ = _git(cwd=scratch, args=["apply", "--3way", "--index"], stdin=patch.encode("utf-8"))
    return _git(cwd=scratch, args=["write-tree"])


@dataclass(kw_only=True)
class _Forge:
    """Runs git for real and plays the forge's Git Data API against the same objects."""

    repo: _Repo
    tree: str | None = None
    override: Callable[[list[str]], CommandResult | None] | None = None
    calls: list[list[str]] = field(default_factory=list)
    bodies: dict[str, list[dict[str, object]]] = field(default_factory=dict)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: object = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        self.calls.append(list(argv))
        if self.override is not None:
            answered = self.override(argv)
            if answered is not None:
                return answered
        if argv[0] == "git":
            return self._git(argv=argv)
        return self._forge(argv=argv, stdin=stdin)

    def _git(self, *, argv: list[str]) -> CommandResult:
        done = subprocess.run(
            argv,
            cwd=self.repo.work,
            capture_output=True,
            check=False,
            env={
                **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@example.test",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@example.test",
            },
        )
        return CommandResult(
            exit_code=done.returncode,
            stdout=done.stdout.decode("utf-8", errors="replace"),
            stderr=done.stderr.decode("utf-8", errors="replace"),
        )

    def _forge(self, *, argv: list[str], stdin: int | None) -> CommandResult:
        work = self.repo.work
        endpoint = next(one for one in argv if one.startswith("/repos/"))
        if endpoint.endswith("/git/refs"):
            fields = [one for one in argv if one.startswith(("ref=", "sha="))]
            ref = next(one for one in fields if one.startswith("ref=")).removeprefix("ref=")
            sha = next(one for one in fields if one.startswith("sha=")).removeprefix("sha=")
            _ = _git(cwd=work, args=["push", "-q", "origin", f"{sha}:{ref}"])
            return CommandResult(exit_code=0, stdout="", stderr="")
        assert stdin is not None
        with os.fdopen(os.dup(stdin), "rb") as handle:
            body = json.loads(handle.read())
        self.bodies.setdefault(endpoint, []).append(body)
        if endpoint.endswith("/git/blobs"):
            content = base64.b64decode(body["content"])
            sha = _git(cwd=work, args=["hash-object", "-w", "--stdin"], stdin=content)
        elif endpoint.endswith("/git/trees"):
            sha = self.tree or ""
        else:
            sha = _git(
                cwd=work,
                args=["commit-tree", body["tree"], "-p", body["parents"][0], "-m", body["message"]],
            )
        return CommandResult(exit_code=0, stdout=f"{sha}\n", stderr="")


def _reseed(
    *, tmp_path: Path, repo: _Repo, forge: _Forge | None = None
) -> Reseeded | ReseedRefusal:
    return diff_apply_reseed(
        runner=forge or _Forge(repo=repo, tree=_expected_tree(tmp_path=tmp_path, repo=repo)),
        repo=repo.work,
        work_item_id=_ITEM,
        seed_ref=_SEED_REF,
        default_branch=_BRANCH,
    )


def _origin_refs(*, repo: _Repo) -> dict[str, str]:
    listing = _git(cwd=repo.origin, args=["for-each-ref", "--format=%(objectname) %(refname)"])
    return {line.split(" ")[1]: line.split(" ")[0] for line in listing.splitlines()}


def _writes(*, forge: _Forge) -> list[list[str]]:
    return [one for one in forge.calls if one[0] == "gh"]


def test_a_stale_seed_is_reapplied_as_one_authored_commit_on_the_tip(tmp_path: Path) -> None:
    repo = _fixture(tmp_path=tmp_path, seed_edit=_clean_seed, tip_edit=_clean_tip)
    expected_tree = _expected_tree(tmp_path=tmp_path, repo=repo)
    forge = _Forge(repo=repo, tree=expected_tree)

    result = _reseed(tmp_path=tmp_path, repo=repo, forge=forge)

    assert isinstance(result, Reseeded)
    assert len(result.commit) == 40
    assert result.ref == f"refs/livespec/reseed/{_ITEM}/{result.commit}"
    assert (result.source_ref, result.source_commit) == (_SEED_REF, repo.seed)
    assert (result.tip_commit, result.default_branch) == (repo.tip, _BRANCH)
    parents = _git(cwd=repo.work, args=["rev-list", "--parents", "-n", "1", result.commit])
    assert parents.split(" ") == [result.commit, repo.tip]
    assert _git(cwd=repo.work, args=["rev-parse", f"{result.commit}^{{tree}}"]) == expected_tree
    message = _git(cwd=repo.work, args=["log", "-1", "--format=%B", result.commit])
    assert message.splitlines()[0] == f"reseed {_ITEM} from {_SEED_REF} onto {_BRANCH}"
    assert f"Livespec-Reseed-Source: {_SEED_REF} {repo.seed}" in message
    assert f"Livespec-Reseed-Onto: {repo.tip}" in message
    refs = _origin_refs(repo=repo)
    assert refs[result.ref] == result.commit
    assert refs[_SEED_REF] == repo.seed
    assert refs[f"refs/heads/{_BRANCH}"] == repo.tip


def test_only_the_changes_the_seed_made_are_posted_and_a_removal_is_a_null_entry(
    tmp_path: Path,
) -> None:
    repo = _fixture(tmp_path=tmp_path, seed_edit=_clean_seed, tip_edit=_clean_tip)
    forge = _Forge(repo=repo, tree=_expected_tree(tmp_path=tmp_path, repo=repo))

    result = _reseed(tmp_path=tmp_path, repo=repo, forge=forge)

    assert isinstance(result, Reseeded)
    (tree_body,) = forge.bodies["/repos/{owner}/{repo}/git/trees"]
    assert tree_body["base_tree"] == _git(cwd=repo.work, args=["rev-parse", f"{repo.tip}^{{tree}}"])
    entries = {one["path"]: one for one in tree_body["tree"]}  # type: ignore[attr-defined]
    assert sorted(entries) == ["a.txt", "d.txt", "n.txt"]
    assert entries["d.txt"]["sha"] is None
    assert entries["n.txt"]["sha"] == _git(cwd=repo.work, args=["rev-parse", f"{repo.seed}:n.txt"])
    posted_blobs = forge.bodies["/repos/{owner}/{repo}/git/blobs"]
    assert len(posted_blobs) == 1
    merged_a = base64.b64decode(posted_blobs[0]["content"]).decode("utf-8")  # type: ignore[arg-type]
    assert "seed line 1" in merged_a
    assert "tip line 20" in merged_a


def test_a_seed_whose_tree_equals_its_merge_base_tree_is_refused_as_carrying_no_work(
    tmp_path: Path,
) -> None:
    repo = _fixture(tmp_path=tmp_path, seed_edit=lambda _work: None, tip_edit=_clean_tip)
    forge = _Forge(repo=repo)

    result = _reseed(tmp_path=tmp_path, repo=repo, forge=forge)

    assert isinstance(result, ReseedRefusal)
    assert _SEED_REF in result.detail
    assert "carries no work" in result.detail
    assert _writes(forge=forge) == []
    assert not [ref for ref in _origin_refs(repo=repo) if ref.startswith("refs/livespec/reseed/")]


def test_a_seed_that_conflicts_with_the_tip_names_every_conflicting_path_and_publishes_nothing(
    tmp_path: Path,
) -> None:
    repo = _fixture(tmp_path=tmp_path, seed_edit=_conflicting_seed, tip_edit=_conflicting_tip)
    forge = _Forge(repo=repo)

    result = _reseed(tmp_path=tmp_path, repo=repo, forge=forge)

    assert isinstance(result, ReseedRefusal)
    assert "a.txt" in result.detail
    assert "b.txt" in result.detail
    assert _SEED_REF in result.detail
    assert _writes(forge=forge) == []
    assert not [ref for ref in _origin_refs(repo=repo) if ref.startswith("refs/livespec/reseed/")]


def _failing(
    *, prefix: list[str], exit_code: int = 1
) -> Callable[[list[str]], CommandResult | None]:
    def answer(argv: list[str]) -> CommandResult | None:
        if argv[: len(prefix)] == prefix:
            return CommandResult(exit_code=exit_code, stdout="", stderr="boom")
        return None

    return answer


def _empty_listing_after(*, count: int) -> Callable[[list[str]], CommandResult | None]:
    """Answer every `git ls-remote` after the first `count` with an empty listing."""
    seen = {"ls-remote": 0}

    def answer(argv: list[str]) -> CommandResult | None:
        if argv[:2] != ["git", "ls-remote"]:
            return None
        seen["ls-remote"] += 1
        if seen["ls-remote"] > count:
            return CommandResult(exit_code=0, stdout="", stderr="")
        return None

    return answer


def _refuse_gitlink(work: Path) -> None:
    """Add a nested repository, which `git add` records as a submodule (gitlink) entry."""
    nested = work / "sub"
    nested.mkdir()
    _ = _git(cwd=nested, args=["init", "-q"])
    _ = _git(cwd=nested, args=["commit", "-q", "--allow-empty", "-m", "nested"])


def _tip_without_the_nested_repository(work: Path) -> None:
    shutil.rmtree(work / "sub")
    _clean_tip(work)


def _already_on_tip(work: Path) -> None:
    _write(work=work, name="b.txt", text="same\n")


@pytest.mark.parametrize(
    ("label", "override", "needle"),
    [
        (
            "tip read fails",
            _failing(prefix=["git", "ls-remote", "origin", "refs/heads/master"]),
            "tip",
        ),
        ("tip absent", _empty_listing_after(count=0), "refs/heads/master"),
        ("seed read fails", _failing(prefix=["git", "ls-remote", "origin", _SEED_REF]), _SEED_REF),
        ("fetch fails", _failing(prefix=["git", "fetch"]), "fetch"),
        ("merge base fails", _failing(prefix=["git", "merge-base"]), "merge base"),
        ("trees unreadable", _failing(prefix=["git", "rev-parse", "--verify"]), "tree"),
        ("merge errors", _failing(prefix=["git", "merge-tree"], exit_code=128), "apply"),
        ("diff unreadable", _failing(prefix=["git", "diff-tree"]), "diff"),
        ("blob unreadable", _failing(prefix=["git", "cat-file"]), "blob"),
        (
            "blob refused",
            lambda argv: (
                CommandResult(exit_code=1, stdout="", stderr="no")
                if any(one.endswith("/git/blobs") for one in argv)
                else None
            ),
            "blob",
        ),
        (
            "tree refused",
            lambda argv: (
                CommandResult(exit_code=0, stdout="\n", stderr="")
                if any(one.endswith("/git/trees") for one in argv)
                else None
            ),
            "tree",
        ),
        (
            "commit refused",
            lambda argv: (
                CommandResult(exit_code=1, stdout="", stderr="no")
                if any(one.endswith("/git/commits") for one in argv)
                else None
            ),
            "commit",
        ),
        (
            "ref refused",
            lambda argv: (
                CommandResult(exit_code=1, stdout="", stderr="no")
                if any(one.endswith("/git/refs") for one in argv)
                else None
            ),
            "ref",
        ),
        ("ref unconfirmed", _empty_listing_after(count=2), "remote read"),
    ],
)
def test_every_step_that_cannot_complete_refuses_naming_what_failed(
    tmp_path: Path,
    label: str,
    override: Callable[[list[str]], CommandResult | None],
    needle: str,
) -> None:
    repo = _fixture(tmp_path=tmp_path, seed_edit=_clean_seed, tip_edit=_clean_tip)
    forge = _Forge(repo=repo, tree=_expected_tree(tmp_path=tmp_path, repo=repo), override=override)

    result = _reseed(tmp_path=tmp_path, repo=repo, forge=forge)

    assert isinstance(result, ReseedRefusal), label
    assert needle in result.detail, label


def test_a_forge_tree_that_is_not_the_applied_tree_is_refused_before_any_commit(
    tmp_path: Path,
) -> None:
    repo = _fixture(tmp_path=tmp_path, seed_edit=_clean_seed, tip_edit=_clean_tip)
    forge = _Forge(repo=repo, tree="e" * 40)

    result = _reseed(tmp_path=tmp_path, repo=repo, forge=forge)

    assert isinstance(result, ReseedRefusal)
    assert "differs" in result.detail
    assert "/repos/{owner}/{repo}/git/commits" not in forge.bodies


def test_a_seed_whose_work_is_already_on_the_tip_is_refused_as_applying_to_nothing(
    tmp_path: Path,
) -> None:
    repo = _fixture(tmp_path=tmp_path, seed_edit=_already_on_tip, tip_edit=_already_on_tip)
    forge = _Forge(repo=repo)

    result = _reseed(tmp_path=tmp_path, repo=repo, forge=forge)

    assert isinstance(result, ReseedRefusal)
    assert "already" in result.detail
    assert _writes(forge=forge) == []


def test_a_seed_that_changes_a_submodule_entry_is_refused(tmp_path: Path) -> None:
    repo = _fixture(
        tmp_path=tmp_path,
        seed_edit=_refuse_gitlink,
        tip_edit=_tip_without_the_nested_repository,
    )
    forge = _Forge(repo=repo)

    result = _reseed(tmp_path=tmp_path, repo=repo, forge=forge)

    assert isinstance(result, ReseedRefusal)
    assert "sub" in result.detail
    assert "submodule" in result.detail
    assert _writes(forge=forge) == []
