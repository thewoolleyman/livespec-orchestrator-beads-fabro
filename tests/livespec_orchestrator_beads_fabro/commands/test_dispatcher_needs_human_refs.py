"""The unreadable-tip boundary for trailer-based needs-human attribution."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_refs import (
    NeedsHumanRef,
    NeedsHumanRefsUnobservable,
    NeedsHumanScope,
    newest_needs_human_ref,
)


class _Runner:
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        if argv[1] == "ls-remote":
            return CommandResult(
                exit_code=0,
                stdout=("e" * 40) + "\trefs/heads/needs-human/opaque\n",
                stderr="",
            )
        return CommandResult(exit_code=128, stdout="", stderr="missing commit")


def test_an_unreadable_trailer_only_tip_is_unobservable() -> None:
    found = newest_needs_human_ref(
        runner=_Runner(),
        repo=Path("/repo"),
        scope=NeedsHumanScope(run_ids=("run",)),
        ref_prefix="refs/heads/needs-human",
        remote="origin",
        timeout_seconds=1.0,
    )

    assert isinstance(found, NeedsHumanRefsUnobservable)
    assert "git show" in found.detail


class _FabroTrailerRunner:
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        if argv[1] == "ls-remote":
            return CommandResult(
                exit_code=0,
                stdout=("f" * 40) + "\trefs/heads/needs-human/opaque\n",
                stderr="",
            )
        return CommandResult(exit_code=0, stdout="Fabro-Run: run\n", stderr="")


def test_a_fabro_run_tip_trailer_attributes_an_opaque_ref() -> None:
    found = newest_needs_human_ref(
        runner=_FabroTrailerRunner(),
        repo=Path("/repo"),
        scope=NeedsHumanScope(run_ids=("run",)),
        ref_prefix="refs/heads/needs-human",
        remote="origin",
        timeout_seconds=1.0,
    )

    assert found is not None and not isinstance(found, NeedsHumanRefsUnobservable)
    assert found.run_id == "run"


class _UnattributedTipRunner(_FabroTrailerRunner):
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        result = super().run(
            argv=argv,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            env=env,
            stdin=stdin,
        )
        if argv[1] == "show":
            return CommandResult(exit_code=0, stdout="Other-Run: run\n", stderr="")
        return result


def test_an_opaque_tip_without_an_accepted_run_trailer_is_not_a_seed() -> None:
    found = newest_needs_human_ref(
        runner=_UnattributedTipRunner(),
        repo=Path("/repo"),
        scope=NeedsHumanScope(run_ids=("run",)),
        ref_prefix="refs/heads/needs-human",
        remote="origin",
        timeout_seconds=1.0,
    )

    assert found is None


_PREFIX = "refs/heads/needs-human"


class _History:
    """A fake origin plus local object store: refs, tip messages, times and ancestry."""

    def __init__(
        self,
        *,
        refs: dict[str, str],
        messages: dict[str, str],
        times: dict[str, int],
        ancestors: set[tuple[str, str]],
    ) -> None:
        self.refs = refs
        self.messages = messages
        self.times = times
        self.ancestors = ancestors
        self.calls: list[list[str]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        if argv[1] == "ls-remote":
            listing = "".join(f"{commit}\t{ref}\n" for ref, commit in self.refs.items())
            return CommandResult(exit_code=0, stdout=listing, stderr="")
        if argv[1] == "show" and argv[3] == "--format=%B":
            return CommandResult(exit_code=0, stdout=self.messages.get(argv[4], ""), stderr="")
        if argv[1] == "show":
            lines = "".join(f"{commit} {self.times[commit]}\n" for commit in argv[4:])
            return CommandResult(exit_code=0, stdout=lines, stderr="")
        older, newer = argv[3], argv[4]
        return CommandResult(
            exit_code=0 if (older, newer) in self.ancestors else 1, stdout="", stderr=""
        )


def _choose(*, history: _History, run_ids: tuple[str, ...]) -> object:
    return newest_needs_human_ref(
        runner=history,
        repo=Path("/repo"),
        scope=NeedsHumanScope(run_ids=run_ids),
        ref_prefix=_PREFIX,
        remote="origin",
        timeout_seconds=1.0,
    )


_OLD_S83 = "d7f0102e1" + "0" * 31
_NEW_S83 = "578a981c2" + "0" * 31
_RYW = "8458ea675" + "0" * 31


def test_a_descendant_tip_of_the_ofvsr3_runs_is_taken_whatever_order_the_identifiers_arrive_in() -> (
    None
):
    run_ids = (
        "01M6PCPTKGTV9M05N2BSSV2WCC",
        "01M6RYWRP28TFR8MJ8F20Q9V53",
        "01M6S83KZH54MR6N8NECJN86Z8",
        "402e63206eb74e309b6792a44ade4d65",
        "74987313a76048979c70ca2ea8b8c8f4",
        "4d5104454d7b406a80014d6d2acc139e",
    )
    by_s83 = f"{_PREFIX}/01M6S83KZH54MR6N8NECJN86Z8"
    by_ryw = f"{_PREFIX}/74987313a76048979c70ca2ea8b8c8f4"
    by_dispatch = f"{_PREFIX}/4d5104454d7b406a80014d6d2acc139e"
    history = _History(
        refs={by_s83: _OLD_S83, by_ryw: _RYW, by_dispatch: _NEW_S83},
        messages={
            _OLD_S83: "Fabro-Run: 01M6S83KZH54MR6N8NECJN86Z8\n",
            _RYW: "Fabro-Run: 01M6RYWRP28TFR8MJ8F20Q9V53\n",
            _NEW_S83: "Fabro-Run: 01M6S83KZH54MR6N8NECJN86Z8\n",
        },
        times={_OLD_S83: 100, _RYW: 150, _NEW_S83: 200},
        ancestors={(_OLD_S83, _NEW_S83)},
    )

    for ordered in (run_ids, tuple(reversed(run_ids))):
        found = _choose(history=history, run_ids=ordered)
        assert isinstance(found, NeedsHumanRef)
        assert found.ref == by_dispatch
        assert found.commit_sha == _NEW_S83
        assert sorted(found.passed_over) == sorted([(by_s83, _OLD_S83), (by_ryw, _RYW)])
    assert ["git", "ls-remote", "origin", f"{_PREFIX}/*"] in history.calls


def test_two_refs_carrying_one_run_are_not_overwritten_by_listing_order() -> None:
    older = f"{_PREFIX}/aaa-older"
    newer = f"{_PREFIX}/zzz-newer"
    for refs in ({older: _OLD_S83, newer: _NEW_S83}, {newer: _NEW_S83, older: _OLD_S83}):
        history = _History(
            refs=refs,
            messages={_OLD_S83: "Fabro-Run: run\n", _NEW_S83: "Factory-Run-Id: run\n"},
            times={_OLD_S83: 100, _NEW_S83: 200},
            ancestors={(_OLD_S83, _NEW_S83)},
        )
        found = _choose(history=history, run_ids=("run",))
        assert isinstance(found, NeedsHumanRef)
        assert found.ref == newer
        assert found.passed_over == ((older, _OLD_S83),)


def test_unrelated_tips_take_the_newest_committer_time_then_the_first_name() -> None:
    first = f"{_PREFIX}/run-a"
    second = f"{_PREFIX}/run-b"
    history = _History(
        refs={first: _OLD_S83, second: _RYW},
        messages={},
        times={_OLD_S83: 300, _RYW: 300},
        ancestors=set(),
    )
    found = _choose(history=history, run_ids=("run-a", "run-b"))
    assert isinstance(found, NeedsHumanRef)
    assert found.ref == first

    history.times[_RYW] = 301
    found = _choose(history=history, run_ids=("run-a", "run-b"))
    assert isinstance(found, NeedsHumanRef)
    assert found.ref == second


def test_a_name_only_breaks_a_tie_between_refs_at_the_same_commit() -> None:
    by_trailer = f"{_PREFIX}/aaa-opaque"
    by_name = f"{_PREFIX}/run-a"
    history = _History(
        refs={by_trailer: _OLD_S83, by_name: _OLD_S83},
        messages={_OLD_S83: "Fabro-Run: run-a\n"},
        times={},
        ancestors=set(),
    )
    found = _choose(history=history, run_ids=("run-a",))
    assert isinstance(found, NeedsHumanRef)
    assert found.ref == by_name
    assert found.passed_over == ((by_trailer, _OLD_S83),)


class _AncestryFails(_History):
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (env, stdin)
        if argv[1] == "merge-base":
            return CommandResult(exit_code=128, stdout="", stderr="bad object")
        return super().run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds)


class _TimesFail(_History):
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (env, stdin)
        if argv[1] == "show" and argv[3] != "--format=%B":
            return CommandResult(exit_code=0, stdout="", stderr="")
        return super().run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds)


def test_unreadable_ancestry_or_committer_times_are_unobservable_never_a_pick() -> None:
    refs = {f"{_PREFIX}/run-a": _OLD_S83, f"{_PREFIX}/run-b": _NEW_S83}
    for history in (
        _AncestryFails(refs=refs, messages={}, times={_OLD_S83: 1, _NEW_S83: 2}, ancestors=set()),
        _TimesFail(refs=refs, messages={}, times={_OLD_S83: 1, _NEW_S83: 2}, ancestors=set()),
    ):
        found = _choose(history=history, run_ids=("run-a", "run-b"))
        assert isinstance(found, NeedsHumanRefsUnobservable)


def test_a_ref_named_under_another_items_run_is_neither_read_nor_counted() -> None:
    foreign = f"{_PREFIX}/foreign-run"
    own = f"{_PREFIX}/run-a"
    history = _History(
        refs={foreign: _RYW, own: _OLD_S83},
        messages={},
        times={},
        ancestors=set(),
    )
    found = newest_needs_human_ref(
        runner=history,
        repo=Path("/repo"),
        scope=NeedsHumanScope(run_ids=("run-a",), foreign_run_ids=frozenset({"foreign-run"})),
        ref_prefix=_PREFIX,
        remote="origin",
        timeout_seconds=1.0,
    )
    assert isinstance(found, NeedsHumanRef)
    assert found.ref == own
    assert found.passed_over == ()
    assert not any(_RYW in call for call in history.calls)
