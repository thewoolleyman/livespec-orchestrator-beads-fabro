"""The ending receipt's terminal-ref parsing and origin diff measurements."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_ref_measurement import (
    PreservedRef,
    checkpoint_ref,
    named_terminal_refs,
    needs_human_ref,
    numstat,
    remote_tip,
    terminal_ref_lines,
    terminal_refs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_wip_capture_receipt import receipt_body

_RUN = "01RUN"
_NEEDS_HUMAN_REF = f"refs/heads/needs-human/{_RUN}"
_PRESERVATION_REF = "refs/livespec/preserved-publish/bd-ib-item/commit"
_COMMIT = "c" * 40
_BASE = "b" * 40


@dataclass(kw_only=True)
class _Runner:
    replies: dict[tuple[str, ...], CommandResult]
    calls: list[tuple[str, ...]] = field(default_factory=list[tuple[str, ...]])

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        key = tuple(argv)
        self.calls.append(key)
        return self.replies[key]


def _result(*, stdout: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr="refused")


def _comments() -> tuple[object, ...]:
    return (
        SimpleNamespace(
            text="\n".join(
                [
                    "livespec-needs-human-cause",
                    f"run id: {_RUN}",
                    f"preservation: the tree was preserved on {_NEEDS_HUMAN_REF} (see pointer)",
                ]
            )
        ),
        SimpleNamespace(
            text="\n".join(
                [
                    "livespec-preserved-tree",
                    f"run id: {_RUN}",
                    f"preservation ref: {_PRESERVATION_REF}",
                ]
            )
        ),
        SimpleNamespace(text="livespec-preserved-tree\nrun id: another\npreservation ref: ignored"),
    )


def test_the_receipt_names_both_terminal_refs_and_their_origin_merge_base_diffs() -> None:
    needs_commit = "n" * 40
    preservation_commit = "p" * 40
    runner = _Runner(
        replies={
            ("git", "ls-remote", "origin", _NEEDS_HUMAN_REF): _result(
                stdout=f"{needs_commit}\t{_NEEDS_HUMAN_REF}\n"
            ),
            ("git", "merge-base", "origin/HEAD", needs_commit): _result(stdout=f"{_BASE}\n"),
            (
                "git",
                "diff",
                "--numstat",
                _BASE,
                needs_commit,
                "--",
                ".",
                ":(exclude).fabro",
            ): _result(stdout="2\t1\tsrc/a.py\n3\t4\tsrc/b.py\n"),
            ("git", "ls-remote", "origin", _PRESERVATION_REF): _result(
                stdout=f"{preservation_commit}\t{_PRESERVATION_REF}\n"
            ),
            ("git", "merge-base", "origin/HEAD", preservation_commit): _result(stdout=f"{_BASE}\n"),
            (
                "git",
                "diff",
                "--numstat",
                _BASE,
                preservation_commit,
                "--",
                ".",
                ":(exclude).fabro",
            ): _result(stdout=""),
        }
    )

    refs = terminal_refs(runner=runner, repo=Path("/repo"), run_id=_RUN, comments=_comments())
    body = receipt_body(
        work_item_id="bd-ib-item",
        run_id=_RUN,
        factory="petri",
        observed=None,
        terminal_refs=refs,
    )

    assert refs == (
        PreservedRef(ref=_NEEDS_HUMAN_REF, commit=needs_commit, diff=(2, 5, 5)),
        PreservedRef(ref=_PRESERVATION_REF, commit=preservation_commit, diff=(0, 0, 0)),
    )
    assert "2 files changed, 5 insertions(+), 5 deletions(-)" in body
    assert "0 files changed, 0 insertions(+), 0 deletions(-)" in body
    assert all(":(exclude).fabro" in call for call in runner.calls if "diff" in call)


def test_unmeasurable_or_missing_terminal_refs_are_named_without_claiming_loss() -> None:
    runner = _Runner(
        replies={
            ("git", "ls-remote", "origin", _NEEDS_HUMAN_REF): _result(
                stdout=f"{_COMMIT}\t{_NEEDS_HUMAN_REF}\n"
            ),
            ("git", "merge-base", "origin/HEAD", _COMMIT): _result(exit_code=1),
            ("git", "ls-remote", "origin", _PRESERVATION_REF): _result(stdout=""),
        }
    )

    refs = terminal_refs(runner=runner, repo=Path("/repo"), run_id=_RUN, comments=_comments())
    lines = terminal_ref_lines(refs=refs)

    assert refs == (
        PreservedRef(ref=_NEEDS_HUMAN_REF, commit=_COMMIT, diff=None),
        PreservedRef(ref=_PRESERVATION_REF, commit=None, diff=None),
    )
    assert "merge-base diff could not be determined" in lines[2]
    assert "tip commit and merge-base diff could not be determined" in lines[4]


def test_terminal_ref_parsers_decline_unrelated_and_malformed_records() -> None:
    assert needs_human_ref(text="livespec-preserved-tree") is None
    assert needs_human_ref(text="livespec-needs-human-cause\npreservation: absent") is None
    assert checkpoint_ref(text="livespec-needs-human-cause") is None
    assert checkpoint_ref(text="livespec-preserved-tree\npreservation ref: none -- failed") is None
    assert (
        named_terminal_refs(
            run_id=_RUN,
            comments=(SimpleNamespace(text=object()), SimpleNamespace(text="unrelated")),
        )
        == ()
    )
    assert numstat(stdout="-\t-\timage.png\n") is None
    assert remote_tip(ref=_NEEDS_HUMAN_REF, result=_result(exit_code=1)) is None
    assert remote_tip(ref=_NEEDS_HUMAN_REF, result=_result(stdout="wrong\tother\n")) is None
