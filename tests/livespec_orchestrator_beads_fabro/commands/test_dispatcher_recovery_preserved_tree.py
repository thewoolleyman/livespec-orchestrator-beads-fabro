"""The preservation ref as a recovery source, and where it ranks.

WHAT IT MEANS FOR THIS SOURCE TO BE WRONG, AND WHY IT IS QUIET. A
checkpoint-failed run's tree exists in exactly one durable place, and the
reclaim's preserved-publish refs share its namespace -- both end in a
forty-character object id, so nothing in a ref NAME tells them apart. A seed
that took the wrong one, or took the right ref and named the wrong commit,
still produces a well-formed seed record and a run that starts cleanly. The
damage shows up only in what the run is working from.

THE BASE-COMMIT ASSERTION IS THE LOAD-BEARING ONE. The published commit ran no
hook, passed no check suite and carries no Red/Green trailers; the clause says
the seed MUST record the run's base commit and MUST NOT carry the hookless
commit itself. Seeding the published commit would put unchecked work into a
run's history and then into its pull request -- and every other assertion here
would still pass, because the ref, the remote and the run id would all be right.
That is why each case asserts the SHA is the base and is NOT the published
commit, rather than asserting the seed is merely non-None.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_STAGE,
    PRESERVED_TREE_UNPRESERVED_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    SEED_REMOTE,
    PreservedWorkUnobservable,
    verified_preserved_seed,
)

_ITEM_ID = "bd-ib-na2xvm"
_RUN = "01M4YJGC55V86C9V1X07QG3Y2H"
_OLDER_RUN = "01M4WYNGFMKM0000000000000Z"

_BASE = "5d511335aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_OLDER_BASE = "5d511335bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_PRESERVED_COMMIT = "c" * 40
_OLDER_PRESERVED_COMMIT = "d" * 40
_PUBLISHED_HEAD = "f3f139b28469c7efaae32dcb897d73518edbaadd"

_PREFIX = f"refs/livespec/preserved-publish/{_ITEM_ID}"
_REF = f"{_PREFIX}/{_PRESERVED_COMMIT}"
_OLDER_REF = f"{_PREFIX}/{_OLDER_PRESERVED_COMMIT}"
_BRANCH_REF = f"refs/heads/feat/{_ITEM_ID}"


@dataclass(kw_only=True)
class _Runner:
    """A scripted subprocess seam keyed by argv substring, recording every call."""

    answers: dict[str, CommandResult] = field(default_factory=dict[str, CommandResult])
    calls: list[str] = field(default_factory=list[str])

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
        joined = " ".join(argv)
        self.calls.append(joined)
        for needle, result in self.answers.items():
            if needle in joined:
                return result
        return CommandResult(exit_code=0, stdout="", stderr="")


def _row(
    *,
    stage: str = PRESERVED_TREE_STAGE,
    ref: str | None = _REF,
    base: str | None = _BASE,
    run_id: str | None = _RUN,
    work_item_id: str = _ITEM_ID,
) -> dict[str, object]:
    """One `preserved-tree` journal row, with every key written as the writer does."""
    return {
        "stage": stage,
        "work_item_id": work_item_id,
        "run_id": run_id,
        "factory": "hp",
        "base_commit": base,
        "preservation_ref": ref,
        "preservation_commit": _PRESERVED_COMMIT,
    }


def _ls_remote(*, ref: str, commit: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=f"{commit}\t{ref}\n", stderr="")


def _seed(*, runner: _Runner, journal_records: tuple[dict[str, object], ...]):
    return verified_preserved_seed(
        runner=runner,
        repo=Path("/repo"),
        work_item_id=_ITEM_ID,
        earlier_run_ids=(_RUN, _OLDER_RUN),
        journal_records=journal_records,
    )


def _asked(*, runner: _Runner, needle: str) -> bool:
    return any(needle in call for call in runner.calls)


def test_the_preservation_ref_outranks_the_published_head_and_names_the_base() -> None:
    # The publish branch is deliberately PRESENT and would otherwise win: without
    # it the ranking claim is vacuous, because there would be nothing to outrank.
    runner = _Runner(
        answers={
            _REF: _ls_remote(ref=_REF, commit=_PRESERVED_COMMIT),
            _BRANCH_REF: _ls_remote(ref=_BRANCH_REF, commit=_PUBLISHED_HEAD),
        }
    )
    seed = _seed(runner=runner, journal_records=(_row(),))
    assert not isinstance(seed, PreservedWorkUnobservable)
    assert seed is not None
    assert seed.preservation_ref == _REF
    assert seed.remote == SEED_REMOTE
    assert seed.source_run_id == _RUN
    # The base, NOT the hookless published commit: the clause forbids carrying it.
    assert seed.commit_sha == _BASE
    assert seed.commit_sha != _PRESERVED_COMMIT
    assert seed.commit_sha != _PUBLISHED_HEAD
    # The published head was never even asked for, which is what "preferred over"
    # means operationally -- a round trip spent there is a question already settled.
    assert not _asked(runner=runner, needle=_BRANCH_REF)


def test_the_newest_published_tree_wins_over_an_earlier_one() -> None:
    # One journal accumulates every dispatch this checkout made, so a re-dispatch
    # appends a second row; seeding the first would work from a tree the item has
    # already moved past.
    runner = _Runner(answers={_REF: _ls_remote(ref=_REF, commit=_PRESERVED_COMMIT)})
    seed = _seed(
        runner=runner,
        journal_records=(
            _row(ref=_OLDER_REF, base=_OLDER_BASE, run_id=_OLDER_RUN),
            _row(),
        ),
    )
    assert seed is not None and not isinstance(seed, PreservedWorkUnobservable)
    assert seed.preservation_ref == _REF
    assert seed.commit_sha == _BASE


def test_a_ref_origin_no_longer_carries_falls_through_to_the_next_source() -> None:
    # Origin is ASKED rather than the journal believed, so a pruned ref is absence
    # at this source and not a seed naming a ref the sandbox could never fetch.
    runner = _Runner(
        answers={
            _REF: CommandResult(exit_code=0, stdout="", stderr=""),
            _BRANCH_REF: _ls_remote(ref=_BRANCH_REF, commit=_PUBLISHED_HEAD),
        }
    )
    seed = _seed(runner=runner, journal_records=(_row(),))
    assert seed is not None and not isinstance(seed, PreservedWorkUnobservable)
    assert seed.commit_sha == _PUBLISHED_HEAD
    assert _asked(runner=runner, needle=_BRANCH_REF)


def test_an_unaskable_origin_is_unobservable_and_not_confirmed_absence() -> None:
    runner = _Runner(answers={_REF: CommandResult(exit_code=128, stdout="", stderr="no")})
    seed = _seed(runner=runner, journal_records=(_row(),))
    assert isinstance(seed, PreservedWorkUnobservable)
    assert _REF in seed.detail
    # The question was NOT silently handed to the next source: an unreadable
    # reference is not confirmed absence, and the two support opposite decisions.
    assert not _asked(runner=runner, needle=_BRANCH_REF)


def test_rows_that_name_no_published_tree_are_passed_over() -> None:
    # A FAILED publication writes every key with nulls, so its row is a record
    # that no ref exists -- not a sparse row to part-use. Another item's row and
    # a row of a different stage must likewise never be read as this item's tree.
    runner = _Runner(answers={_BRANCH_REF: _ls_remote(ref=_BRANCH_REF, commit=_PUBLISHED_HEAD)})
    seed = _seed(
        runner=runner,
        journal_records=(
            _row(stage=PRESERVED_TREE_UNPRESERVED_STAGE),
            _row(work_item_id="bd-ib-someone-else"),
            _row(ref=None),
            _row(base=None),
            _row(run_id=None),
            # Present but EMPTY is its own arm, and not the same as absent: a
            # degraded row carrying the empty string passes every type test and
            # would reach `git ls-remote` as a bare remote name, which lists
            # EVERY ref and would seed from whichever came back first.
            _row(ref=""),
            _row(base="   "),
            _row(run_id=""),
        ),
    )
    assert seed is not None and not isinstance(seed, PreservedWorkUnobservable)
    assert seed.commit_sha == _PUBLISHED_HEAD
    assert not _asked(runner=runner, needle=_PREFIX + "/")
