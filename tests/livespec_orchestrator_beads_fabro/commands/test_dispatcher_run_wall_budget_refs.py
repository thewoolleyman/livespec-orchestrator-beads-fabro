"""Finding a verified preservation ref of a run on origin (bd-ib-l77jxo).

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": a held budget cancel looks for a *verified preservation
ref* of the run with "a remote ref listing (`git ls-remote`, never a local
clone)": `refs/heads/needs-human/<run-id>`, `refs/heads/preserve/run-<run-id>`,
a `refs/livespec/preserved-publish/<work-item-id>/<commit-sha>` ref, or the
run's latest `refs/livespec/wip/<work-item-id>/<run-id>/<n>` capture, "whose
commit's tree equals the tree of the run branch's committed tip as the run's own
record reports it. When the run's record cannot report that tip, the run's
latest preserved capture or its needs-human ref qualifies on its own." "A remote
ref listing that cannot be taken is a failed measurement of that poll, never
evidence that no ref exists."

The module is read inside each test body, through `importlib`, so the Red
commit fails on a genuine assertion about the module's absence rather than at
collection.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_refs"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_run_wall_budget_refs.py"
)
_ITEM = "bd-ib-uq2ocd"
_RUN = "01M6PAS50BAVMD32HFBV8P89YR"
_TIP = "a" * 40
_TIP_TREE = "cc9568cc88a0" + "0" * 28
_NEEDS_HUMAN = f"refs/heads/needs-human/{_RUN}"
_PRESERVE = f"refs/heads/preserve/run-{_RUN}"
_WIP = f"refs/livespec/wip/{_ITEM}/{_RUN}"
_PUBLISH = f"refs/livespec/preserved-publish/{_ITEM}"


def _sha(letter: str) -> str:
    return letter * 40


@dataclass(kw_only=True)
class _Origin:
    """A scripted `git` that answers the listing, the tree reads and the fetch.

    `remote` is what origin lists, `trees` maps a commit to its tree, `local`
    is the set of commits this clone can already read, and `fetchable` the
    commits origin will hand over when asked for them by id.
    """

    remote: dict[str, str] = field(default_factory=dict)
    trees: dict[str, str] = field(default_factory=dict)
    local: set[str] = field(default_factory=set)
    fetchable: set[str] = field(default_factory=set)
    listing_exit_code: int = 0
    fetch_drops_the_commit: bool = False
    calls: list[list[str]] = field(default_factory=list)

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
        verb = argv[1]
        if verb == "ls-remote":
            return self._listing()
        if verb == "fetch":
            reachable = argv[-1] in self.fetchable
            if reachable and not self.fetch_drops_the_commit:
                self.local.add(argv[-1])
            return CommandResult(exit_code=0 if reachable else 128, stdout="", stderr="")
        commit = argv[-1].removesuffix("^{tree}")
        if commit in self.local:
            return CommandResult(exit_code=0, stdout=f"{self.trees[commit]}\n", stderr="")
        return CommandResult(exit_code=1, stdout="", stderr="")

    def _listing(self) -> CommandResult:
        if self.listing_exit_code != 0:
            return CommandResult(exit_code=self.listing_exit_code, stdout="", stderr="no route")
        lines = "".join(f"{commit}\t{ref}\n" for ref, commit in self.remote.items())
        return CommandResult(exit_code=0, stdout=lines, stderr="")


def _lookup(*, origin: _Origin, tip: str | None = _TIP) -> Any:
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist"
    module = importlib.import_module(_MODULE)
    return module.verified_preservation_ref(
        runner=cast("Any", origin),
        repo=Path(),
        work_item_id=_ITEM,
        run_id=_RUN,
        tip_commit=tip,
    )


def _origin(*, remote: dict[str, str], tip_tree: str = _TIP_TREE) -> _Origin:
    """An origin whose refs sit at commits with the named trees; the tip is local."""
    trees = {_TIP: tip_tree}
    trees.update({commit: _TIP_TREE for commit in remote.values()})
    return _Origin(remote=remote, trees=trees, local=set(trees))


def test_the_listing_is_one_remote_listing_of_the_runs_four_ref_families() -> None:
    """The listing asks origin, never a local clone, for every family of ref."""
    origin = _origin(remote={_NEEDS_HUMAN: _sha("b")})
    _lookup(origin=origin)
    listing = origin.calls[0]
    assert listing[:3] == ["git", "ls-remote", "origin"]
    assert set(listing[3:]) == {
        _NEEDS_HUMAN,
        _PRESERVE,
        f"{_PUBLISH}/*",
        f"{_WIP}/*",
    }


def test_a_needs_human_ref_at_the_same_tree_is_a_verified_preservation_ref() -> None:
    """A different commit with an equal tree to the run's committed tip qualifies."""
    found = _lookup(origin=_origin(remote={_NEEDS_HUMAN: _sha("b")}))
    assert (found.ref, found.commit) == (_NEEDS_HUMAN, _sha("b"))


def test_a_ref_at_the_tips_own_commit_qualifies_without_reading_any_tree() -> None:
    """Equal commits have equal trees, so no tree read or fetch is needed."""
    origin = _Origin(remote={_PRESERVE: _TIP})
    found = _lookup(origin=origin)
    assert (found.ref, found.commit) == (_PRESERVE, _TIP)
    assert [call[1] for call in origin.calls] == ["ls-remote"]


def test_a_ref_at_a_different_tree_is_not_a_verified_preservation_ref() -> None:
    """Origin holding a ref of the run is not enough; its tree must be the tip's."""
    origin = _origin(remote={_NEEDS_HUMAN: _sha("b")})
    origin.trees[_sha("b")] = "f" * 40
    assert _lookup(origin=origin) is None


def test_only_the_latest_wip_capture_of_the_run_counts() -> None:
    """The run's LATEST capture is the one the clause names, not an older one."""
    remote = {f"{_WIP}/1": _sha("c"), f"{_WIP}/2": _sha("d"), f"{_WIP}/10": _sha("e")}
    origin = _origin(remote=remote)
    origin.trees[_sha("e")] = "f" * 40
    assert _lookup(origin=origin) is None
    origin.trees[_sha("e")] = _TIP_TREE
    found = _lookup(origin=origin)
    assert (found.ref, found.commit) == (f"{_WIP}/10", _sha("e"))


def test_a_preserved_publish_ref_qualifies_by_tree() -> None:
    """The reclaim's preserved-publish ref names the commit, and the tree decides."""
    found = _lookup(origin=_origin(remote={f"{_PUBLISH}/{_sha('b')}": _sha("b")}))
    assert (found.ref, found.commit) == (f"{_PUBLISH}/{_sha('b')}", _sha("b"))


def test_a_ref_listed_with_no_run_in_its_name_is_ignored() -> None:
    """Another run's needs-human ref is not this run's, whatever its tree is."""
    other = "refs/heads/needs-human/01OTHERRUN"
    assert _lookup(origin=_origin(remote={other: _sha("b")})) is None


def test_the_needs_human_ref_is_preferred_to_the_other_matching_refs() -> None:
    """Several refs may match; the choice is stable rather than listing-ordered."""
    remote = {
        f"{_PUBLISH}/{_sha('d')}": _sha("d"),
        f"{_WIP}/3": _sha("c"),
        _PRESERVE: _sha("b"),
        _NEEDS_HUMAN: _sha("e"),
    }
    assert _lookup(origin=_origin(remote=remote)).ref == _NEEDS_HUMAN
    del remote[_NEEDS_HUMAN]
    assert _lookup(origin=_origin(remote=remote)).ref == _PRESERVE
    del remote[_PRESERVE]
    assert _lookup(origin=_origin(remote=remote)).ref == f"{_WIP}/3"


def test_with_no_reported_tip_the_needs_human_ref_qualifies_on_its_own() -> None:
    """The run created it from the run branch's tip, so no comparison is possible."""
    origin = _origin(remote={_NEEDS_HUMAN: _sha("b"), _PRESERVE: _sha("c")})
    found = _lookup(origin=origin, tip=None)
    assert (found.ref, found.commit) == (_NEEDS_HUMAN, _sha("b"))
    assert [call[1] for call in origin.calls] == ["ls-remote"]


def test_with_no_reported_tip_the_latest_wip_capture_qualifies_on_its_own() -> None:
    """A capture is also cut from the tip, so it releases a hold with no tip to compare."""
    remote = {f"{_WIP}/1": _sha("c"), f"{_WIP}/2": _sha("d")}
    found = _lookup(origin=_origin(remote=remote), tip=None)
    assert (found.ref, found.commit) == (f"{_WIP}/2", _sha("d"))


def test_with_no_reported_tip_the_other_refs_do_not_qualify_on_their_own() -> None:
    """A preserve ref or a preserved-publish ref says nothing about THIS tip."""
    remote = {_PRESERVE: _sha("b"), f"{_PUBLISH}/{_sha('c')}": _sha("c")}
    assert _lookup(origin=_origin(remote=remote), tip=None) is None


def test_origin_holding_no_ref_of_the_run_is_an_absence() -> None:
    """An answered, empty listing is the one reading that means no ref exists."""
    assert _lookup(origin=_origin(remote={})) is None


def test_a_listing_that_cannot_be_taken_is_a_failed_measurement_not_an_absence() -> None:
    """A failed `git ls-remote` must never read as 'origin holds no ref'."""
    origin = _origin(remote={_NEEDS_HUMAN: _sha("b")})
    origin.listing_exit_code = 128
    unobservable = _lookup(origin=origin)
    detail = unobservable.detail
    assert "git ls-remote origin" in detail
    assert "128" in detail
    assert not hasattr(unobservable, "ref")


def test_a_commit_this_clone_lacks_is_fetched_by_id_before_its_tree_is_read() -> None:
    """The listing hands back ids only, so an unknown commit is fetched from origin."""
    origin = _origin(remote={_NEEDS_HUMAN: _sha("b")})
    origin.local.discard(_sha("b"))
    origin.fetchable.add(_sha("b"))
    found = _lookup(origin=origin)
    assert (found.ref, found.commit) == (_NEEDS_HUMAN, _sha("b"))
    assert ["git", "fetch", "--quiet", "origin", _sha("b")] in origin.calls


def test_a_candidate_whose_tree_cannot_be_read_is_unobservable_not_unverified() -> None:
    """A tree nobody could read proves nothing either way, and says so."""
    origin = _origin(remote={_NEEDS_HUMAN: _sha("b")})
    origin.local.discard(_sha("b"))
    unobservable = _lookup(origin=origin)
    assert _NEEDS_HUMAN in unobservable.detail
    assert not hasattr(unobservable, "ref")


def test_a_readable_matching_candidate_wins_over_an_unreadable_one() -> None:
    """One unreadable ref does not hide another ref that verifies."""
    remote = {_NEEDS_HUMAN: _sha("b"), _PRESERVE: _sha("c")}
    origin = _origin(remote=remote)
    origin.local.discard(_sha("b"))
    assert _lookup(origin=origin).ref == _PRESERVE


def test_a_tip_whose_tree_cannot_be_read_is_unobservable() -> None:
    """With the tip unreadable no ref can be compared, so no ref is declared absent."""
    origin = _origin(remote={_NEEDS_HUMAN: _sha("b")})
    origin.local.discard(_TIP)
    unobservable = _lookup(origin=origin)
    assert _TIP in unobservable.detail
    assert not hasattr(unobservable, "ref")


def test_a_fetch_that_succeeds_but_leaves_the_commit_unreadable_is_a_failed_read() -> None:
    """The retry's own read failing is a failed measurement like the first."""
    origin = _origin(remote={_NEEDS_HUMAN: _sha("b")})
    origin.local.discard(_sha("b"))
    origin.fetchable.add(_sha("b"))
    origin.fetch_drops_the_commit = True
    assert _NEEDS_HUMAN in _lookup(origin=origin).detail
