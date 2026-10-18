"""The three preserved-work sources, their order, and the two ways each can fail.

`test_dispatcher_recovery_routing_seeded.py` drives the FIRST source end to end
through a real wave, which is the tier Scenario 185's second scenario belongs to.
This module covers what one wave cannot reach: the other two sources, the order
between all three, and — the arm that decides whether work is lost — an
unreadable reference, which "is not confirmed absence".

WHY THE ORDER IS ASSERTED BY WHAT WAS *NOT* ASKED. A reading that asked all three
sources and then preferred the right answer looks identical, at the returned
seed, to one that asked the cheapest question first and stopped. The difference
shows only in the calls: each case therefore reads the ARGV log, and the
higher-preference cases assert that the lower-preference sources were never asked
at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    NEEDS_HUMAN_REF_PREFIX,
    PRESERVED_SOURCE_EARLIER_PRESERVED_PUBLISH_REF,
    PRESERVED_SOURCE_PUBLISHED_HEAD,
    PRESERVED_SOURCE_TERMINAL_TREE,
    SEED_REMOTE,
    PreservedWorkAbsent,
    PreservedWorkUnobservable,
    verified_preserved_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed

_ITEM_ID = "bd-ib-qgcpoc"
_BRANCH_REF = f"refs/heads/feat/{_ITEM_ID}"
_RUN = "01M509HNX5KGKSRV04VQEYVWH6"
_OLDER_RUN = "01M4WYNGFMKM0000000000000Z"

_TERMINAL_COMMIT = "216c811200000000000000000000000000000002"
_PUBLISHED_HEAD = "f3f139b28469c7efaae32dcb897d73518edbaadd"
_EARLIER_HEAD = "1e9b31ba00000000000000000000000000000003"

_PRESERVED_PUBLISH_PREFIX = f"refs/livespec/preserved-publish/{_ITEM_ID}"


@dataclass(kw_only=True)
class _Runner:
    """A scripted subprocess seam keyed by argv substring, recording every call."""

    answers: dict[str, CommandResult] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        joined = " ".join(argv)
        self.calls.append(joined)
        for needle, result in self.answers.items():
            if needle in joined:
                return result
        return CommandResult(exit_code=0, stdout="", stderr="")


def _seed(
    *,
    runner: _Runner,
    earlier_run_ids: tuple[str, ...] = (_RUN, _OLDER_RUN),
    journal_records: tuple[dict[str, object], ...] = (),
):
    return verified_preserved_seed(
        runner=runner,
        repo=Path("/repo"),
        work_item_id=_ITEM_ID,
        earlier_run_ids=earlier_run_ids,
        journal_records=journal_records,
    )


def _asked(*, runner: _Runner, needle: str) -> bool:
    return any(needle in call for call in runner.calls)


def test_the_terminal_tree_wins_and_the_other_two_sources_are_never_asked() -> None:
    """The needs-human ref carries the run's whole tree, so nothing below it is read.

    The newest identifier's ref is taken even though an OLDER run also has one, and
    the publish branch is carrying a different head at the same moment — so a
    reading that preferred either would land on a well-formed wrong commit.
    """
    runner = _Runner(
        answers={
            f"ls-remote {SEED_REMOTE} {NEEDS_HUMAN_REF_PREFIX}/": CommandResult(
                exit_code=0,
                stdout=(
                    f"{_TERMINAL_COMMIT}\t{NEEDS_HUMAN_REF_PREFIX}/{_RUN}\n"
                    f"{_EARLIER_HEAD}\t{NEEDS_HUMAN_REF_PREFIX}/{_OLDER_RUN}\n"
                ),
                stderr="",
            )
        }
    )

    assert _seed(runner=runner) == RecoverySeed(
        source_run_id=_RUN,
        remote=SEED_REMOTE,
        commit_sha=_TERMINAL_COMMIT,
        preservation_ref=f"{NEEDS_HUMAN_REF_PREFIX}/{_RUN}",
    )
    assert not _asked(runner=runner, needle=_BRANCH_REF)
    assert not _asked(runner=runner, needle=_PRESERVED_PUBLISH_PREFIX)


def test_an_unreadable_terminal_reference_is_unobservable_and_stops_the_search() -> None:
    """ "An unreadable reference is not confirmed absence."

    Nothing below it is asked, because an answer from a lower-preference source
    would be acted on as though the higher one had been established absent — and
    that is exactly how a preserved tree nobody could read becomes one nobody will
    ever use.
    """
    runner = _Runner(
        answers={
            f"ls-remote {SEED_REMOTE} {NEEDS_HUMAN_REF_PREFIX}/": CommandResult(
                exit_code=128, stdout="", stderr="fatal: unable to access"
            )
        }
    )

    found = _seed(runner=runner)

    assert isinstance(found, PreservedWorkUnobservable)
    assert "could not be established" in found.detail
    assert not _asked(runner=runner, needle=_BRANCH_REF)


def test_an_item_with_no_earlier_identifier_skips_the_terminal_source_entirely() -> None:
    """With no run to name, that ref cannot exist, so no round trip is spent on it."""
    runner = _Runner(
        answers={
            f"ls-remote {SEED_REMOTE} {_BRANCH_REF}": CommandResult(
                exit_code=0, stdout=f"{_PUBLISHED_HEAD}\t{_BRANCH_REF}\n", stderr=""
            )
        }
    )

    found = _seed(runner=runner, earlier_run_ids=())

    assert isinstance(found, RecoverySeed)
    # The seed names no source run, because the ref it was read off names none.
    assert found.source_run_id == ""
    assert not _asked(runner=runner, needle=NEEDS_HUMAN_REF_PREFIX)


def test_the_published_head_is_seeded_under_the_ref_the_reclaim_will_preserve_it_at() -> None:
    """The seed names the preservation ref, never the branch it was read off.

    The reclaim deletes that branch before the run starts, so a seed naming it
    would fetch a ref that no longer exists by the time the sandbox asks. The
    preserved-publish source below it is not asked, which is what makes this the
    SECOND source rather than a fallback of the third.
    """
    runner = _Runner(
        answers={
            f"ls-remote {SEED_REMOTE} {_BRANCH_REF}": CommandResult(
                exit_code=0, stdout=f"{_PUBLISHED_HEAD}\t{_BRANCH_REF}\n", stderr=""
            )
        }
    )

    assert _seed(runner=runner) == RecoverySeed(
        source_run_id=_RUN,
        remote=SEED_REMOTE,
        commit_sha=_PUBLISHED_HEAD,
        preservation_ref=f"{_PRESERVED_PUBLISH_PREFIX}/{_PUBLISHED_HEAD}",
    )
    assert not _asked(runner=runner, needle=f"{_PRESERVED_PUBLISH_PREFIX}/*")


def test_an_unaskable_publish_branch_is_unobservable_rather_than_absent() -> None:
    """The reclaim's own distinction, carried through: "we could not look" is not "none"."""
    runner = _Runner(
        answers={
            f"ls-remote {SEED_REMOTE} {_BRANCH_REF}": CommandResult(
                exit_code=128, stdout="", stderr="fatal: unable to access"
            )
        }
    )

    found = _seed(runner=runner)

    assert isinstance(found, PreservedWorkUnobservable)
    assert _BRANCH_REF in found.detail


def test_a_preserved_publish_ref_of_an_earlier_head_is_the_last_source() -> None:
    """It is still preserved work, so it is asked before absence is confirmed.

    A `fresh` dispatch "with that loss recorded" taken while such a ref stands
    would be recording a loss that had not happened. The LAST line of the listing
    is taken, which is deterministic for one reading and the most this source can
    honestly offer — nothing in the ref says which of two earlier heads is newer.
    """
    runner = _Runner(
        answers={
            f"ls-remote {SEED_REMOTE} {_PRESERVED_PUBLISH_PREFIX}/*": CommandResult(
                exit_code=0,
                stdout=(
                    f"{_EARLIER_HEAD}\t{_PRESERVED_PUBLISH_PREFIX}/{_EARLIER_HEAD}\n"
                    "a-line-ls-remote-never-prints\n"
                ),
                stderr="",
            )
        }
    )

    assert _seed(runner=runner) == RecoverySeed(
        source_run_id=_RUN,
        remote=SEED_REMOTE,
        commit_sha=_EARLIER_HEAD,
        preservation_ref=f"{_PRESERVED_PUBLISH_PREFIX}/{_EARLIER_HEAD}",
    )


def test_an_unaskable_preserved_publish_listing_is_unobservable() -> None:
    """The last source fails the same way the first two do, and for the same reason."""
    runner = _Runner(
        answers={
            f"ls-remote {SEED_REMOTE} {_PRESERVED_PUBLISH_PREFIX}/*": CommandResult(
                exit_code=128, stdout="", stderr="fatal: unable to access"
            )
        }
    )

    found = _seed(runner=runner)

    assert isinstance(found, PreservedWorkUnobservable)
    assert "absence is not confirmed" in found.detail


def test_three_silent_sources_are_confirmed_absence() -> None:
    """Every source asked, every one naming nothing: the one answer that permits `fresh`.

    This is the control for all six cases above: a reading that answered absence
    whatever it saw would satisfy them only here, and a reading that never
    answered absence would leave a genuinely clean item permanently held.

    The absence NAMES what it measured — the run whose work is being written off
    and each source that was asked — because the clause requires the plain
    dispatch it permits to record that loss, and the record cannot be a
    measurement unless the reading reports one.
    """
    runner = _Runner()

    assert _seed(runner=runner) == PreservedWorkAbsent(
        source_run_id=_RUN,
        sources_asked=(
            PRESERVED_SOURCE_TERMINAL_TREE,
            PRESERVED_SOURCE_PUBLISHED_HEAD,
            PRESERVED_SOURCE_EARLIER_PRESERVED_PUBLISH_REF,
        ),
    )
    assert _asked(runner=runner, needle=NEEDS_HUMAN_REF_PREFIX)
    assert _asked(runner=runner, needle=_BRANCH_REF)
    assert _asked(runner=runner, needle=f"{_PRESERVED_PUBLISH_PREFIX}/*")
