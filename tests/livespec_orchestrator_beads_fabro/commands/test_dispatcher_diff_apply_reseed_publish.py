"""Publishing a diff-apply reseed's tree puts one commit over the tip on a confirmed ref.

The real-origin cases live beside this module (`test_dispatcher_diff_apply_reseed`).
These drive `publish_reseed` against a scripted runner, which is what lets each forge
call be refused on its own and lets the argv and the posted bodies be read directly.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_diff_apply_reseed_publish import (
    AppliedTree,
    PublishedReseed,
    ReseedRefusal,
    TreeChange,
    publish_reseed,
    reseed_ref,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_ITEM = "bd-ib-5xihdt"
_TIP = "1" * 40
_TIP_TREE = "2" * 40
_APPLIED_TREE = "3" * 40
_COMMIT = "4" * 40
_MERGED_BLOB = "5" * 40
_POSTED_BLOB = "6" * 40
_SEED_BLOB = "7" * 40
_REF = f"refs/livespec/reseed/{_ITEM}/{_COMMIT}"
_OK = CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Runner:
    """Answers each call the way the forge would, unless `refuse` names the call."""

    refuse: Callable[[list[str]], CommandResult | None] = lambda _argv: None
    tree: str = _APPLIED_TREE
    listing: str = f"{_COMMIT}\t{_REF}\n"
    calls: list[list[str]] = field(default_factory=list)
    bodies: dict[str, dict[str, object]] = field(default_factory=dict)

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
        refused = self.refuse(argv)
        if refused is not None:
            return refused
        if argv[:2] == ["git", "cat-file"]:
            return CommandResult(exit_code=0, stdout="merged\n", stderr="")
        if argv[:2] == ["git", "ls-remote"]:
            return CommandResult(exit_code=0, stdout=self.listing, stderr="")
        endpoint = next((one for one in argv if one.startswith("/repos/")), "")
        if endpoint.endswith("/git/refs") or stdin is None:
            return _OK
        with os.fdopen(os.dup(stdin), "rb") as handle:
            self.bodies[endpoint.rsplit("/", 1)[1]] = json.loads(handle.read())
        named = {"blobs": _POSTED_BLOB, "trees": self.tree, "commits": _COMMIT}
        return CommandResult(exit_code=0, stdout=named[endpoint.rsplit("/", 1)[1]], stderr="")


def _applied() -> AppliedTree:
    return AppliedTree(
        message="reseed message",
        tip=_TIP,
        tip_tree=_TIP_TREE,
        applied_tree=_APPLIED_TREE,
        changes=(
            TreeChange(path="seed-only.txt", mode="100644", blob=_SEED_BLOB, on_origin=True),
            TreeChange(path="both.txt", mode="100644", blob=_MERGED_BLOB, on_origin=False),
            TreeChange(path="gone.txt", mode="100644", blob=None, on_origin=True),
        ),
    )


def _publish(*, runner: _Runner) -> PublishedReseed | ReseedRefusal:
    return publish_reseed(runner=runner, repo=Path(), work_item_id=_ITEM, applied=_applied())


def _refusing(*, needle: str, exit_code: int = 1) -> Callable[[list[str]], CommandResult | None]:
    def refuse(argv: list[str]) -> CommandResult | None:
        if any(needle in one for one in argv):
            return CommandResult(exit_code=exit_code, stdout="", stderr="no")
        return None

    return refuse


def test_the_ref_is_named_after_the_item_and_the_commit() -> None:
    assert reseed_ref(work_item_id=_ITEM, commit=_COMMIT) == _REF


def test_the_applied_tree_is_published_as_one_commit_over_the_tip_and_confirmed() -> None:
    runner = _Runner()

    result = _publish(runner=runner)

    assert result == PublishedReseed(ref=_REF, commit=_COMMIT)
    entries = cast("list[dict[str, object]]", runner.bodies["trees"]["tree"])
    assert [(one["path"], one["sha"]) for one in entries] == [
        ("seed-only.txt", _SEED_BLOB),
        ("both.txt", _POSTED_BLOB),
        ("gone.txt", None),
    ]
    assert runner.bodies["trees"]["base_tree"] == _TIP_TREE
    assert runner.bodies["commits"] == {
        "message": "reseed message",
        "tree": _APPLIED_TREE,
        "parents": [_TIP],
    }
    assert base64.b64decode(str(runner.bodies["blobs"]["content"])) == b"merged\n"
    assert runner.calls[-1] == ["git", "ls-remote", "origin", _REF]


def test_a_blob_the_forge_already_holds_is_not_posted() -> None:
    runner = _Runner()

    _ = _publish(runner=runner)

    assert [one for one in runner.calls if one[:2] == ["git", "cat-file"]] == [
        ["git", "cat-file", "blob", _MERGED_BLOB]
    ]


def test_a_merged_blob_that_cannot_be_read_refuses_before_anything_is_posted() -> None:
    runner = _Runner(refuse=_refusing(needle="cat-file"))

    result = _publish(runner=runner)

    assert isinstance(result, ReseedRefusal)
    assert "both.txt" in result.detail
    assert runner.bodies == {}


def test_a_merged_blob_the_forge_does_not_name_refuses() -> None:
    runner = _Runner(refuse=_refusing(needle="/git/blobs"))

    result = _publish(runner=runner)

    assert isinstance(result, ReseedRefusal)
    assert "no blob" in result.detail
    assert "trees" not in runner.bodies


def test_a_forge_tree_that_is_not_the_applied_tree_refuses_before_any_commit() -> None:
    runner = _Runner(tree="e" * 40)

    result = _publish(runner=runner)

    assert isinstance(result, ReseedRefusal)
    assert "differs" in result.detail
    assert "commits" not in runner.bodies


def test_a_forge_that_names_no_tree_refuses_naming_none() -> None:
    runner = _Runner(refuse=_refusing(needle="/git/trees"))

    result = _publish(runner=runner)

    assert isinstance(result, ReseedRefusal)
    assert "none" in result.detail


def test_a_forge_that_names_no_commit_refuses_before_creating_a_ref() -> None:
    runner = _Runner(refuse=_refusing(needle="/git/commits"))

    result = _publish(runner=runner)

    assert isinstance(result, ReseedRefusal)
    assert "no commit" in result.detail
    assert not [one for one in runner.calls if any(x.endswith("/git/refs") for x in one)]


def test_a_ref_the_forge_refuses_to_create_refuses_naming_the_exit() -> None:
    runner = _Runner(refuse=_refusing(needle="/git/refs", exit_code=7))

    result = _publish(runner=runner)

    assert isinstance(result, ReseedRefusal)
    assert _REF in result.detail
    assert "exited 7" in result.detail


def test_a_ref_the_remote_read_does_not_confirm_is_not_reported_as_published() -> None:
    runner = _Runner(listing=f"{'9' * 40}\t{_REF}\n")

    result = _publish(runner=runner)

    assert isinstance(result, ReseedRefusal)
    assert "did not confirm" in result.detail
    assert "9" * 40 in result.detail


def test_a_remote_read_that_lists_nothing_names_nothing_observed() -> None:
    runner = _Runner(listing="")

    result = _publish(runner=runner)

    assert isinstance(result, ReseedRefusal)
    assert "observed nothing" in result.detail
