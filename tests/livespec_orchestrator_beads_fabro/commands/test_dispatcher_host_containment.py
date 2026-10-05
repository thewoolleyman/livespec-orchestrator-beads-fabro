"""Tests for the gathering half of the host leg: the forge read and the selection.

`test_dispatcher_host_leg.py` covers the evidence RULE. This module covers what that
rule is handed: the containment comparison the pass must verify itself, the memoized
reader that resolves it, and the selection of which records on a pull request are host
replays at all.

THE MEMOIZATION IS ASSERTED BY COUNTING FORGE CALLS, not by inspecting a cache. A
capture and the replay of it are taken against ONE installed build, so the same release
is named more than once on a normal pull request; an un-memoized reader is correct and
merely wasteful, which no verdict-shaped assertion can see. The call count is the only
instrument that can.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    RELEASE_TAG_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_containment import (
    compare_argv,
    containment_reader,
    host_leg_for_records,
    merge_contained_in,
    unchecked_containment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import proof_records

_REPO = Path("/repo")
_MERGE_SHA = "ac7ebb0f36026f9789997f93aaaabbbbccccdddd"
_RELEASE_TAG = "v0.166.0"
_ASSERTION = "The released build resolves the host mode on an operator host."


@dataclass(kw_only=True)
class _Runner:
    results: list[CommandResult]
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        return self.results.pop(0)


def _result(*, exit_code: int = 0, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr="")


def _comment(*, verdict: str, identity: str, reproduced: str | None = "yes") -> dict[str, str]:
    verdict_line = "" if reproduced is None else f"\nReproduced: {reproduced}.\n"
    return {
        "url": f"https://example.test/c/{identity}",
        "body": (
            f"Proof of Done — {verdict} — session {identity} — t\n\n"
            f"- {RELEASE_TAG_LABEL}: {_RELEASE_TAG}\n\n"
            f"## Assertion 1 — {_ASSERTION}\n{verdict_line}"
        ),
    }


def test_the_reader_asks_the_forge_once_per_distinct_build() -> None:
    """Two replays naming one release cost ONE comparison, not two.

    The memoization is what keeps an acceptance pass's forge cost proportional to the
    number of BUILDS a pull request names rather than to the number of records on it,
    and a pass re-runs on every `reconcile-merged`.
    """
    runner = _Runner(results=[_result(stdout="ahead\n")])
    reader = containment_reader(repo=_REPO, merge_sha=_MERGE_SHA, runner=runner)

    assert reader(ref=_RELEASE_TAG) is True
    assert reader(ref=_RELEASE_TAG) is True
    assert runner.argvs == [compare_argv(base=_MERGE_SHA, head=_RELEASE_TAG)]


def test_the_reader_answers_unobservable_without_asking_when_no_merge_is_known() -> None:
    """With no merge commit there is nothing to check containment OF, so none is run."""
    runner = _Runner(results=[])
    reader = containment_reader(repo=_REPO, merge_sha=None, runner=runner)

    assert reader(ref=_RELEASE_TAG) is None
    assert runner.argvs == []


def test_the_unchecked_reader_refuses_every_build() -> None:
    """The fail-closed default: not checked, for every build, so the item parks."""
    assert unchecked_containment(ref=_RELEASE_TAG) is None


def test_the_selection_grades_only_replay_records_and_reads_the_capture_identity() -> None:
    """A `host_recorded` record supplies the capturing identity and decides nothing.

    One pull request carrying a capture and an INDEPENDENT replay is the ordinary
    shape, and this is the join that turns those two comments into the rule's three
    inputs. The pass is the assertion that the capture was used as the identity rather
    than as evidence: a selection that admitted it as a replay would find it listed
    the assertion and pass it, with no independent party involved at all.
    """
    records = proof_records(
        comments=[
            _comment(verdict="host_recorded", identity="capturing", reproduced=None),
            _comment(verdict="host_verified", identity="replaying"),
        ]
    )

    leg = host_leg_for_records(
        assertions=(_ASSERTION,),
        records=records,
        contains_merge=lambda ref: ref == _RELEASE_TAG,
    )

    assert [one.passed for one in leg.grades] == [True]
    assert leg.pending == ()


def test_a_replay_from_the_capturing_identity_is_refused_by_the_selection_join() -> None:
    """The capturing identity the join read is what the rule compares against."""
    records = proof_records(
        comments=[
            _comment(verdict="host_recorded", identity="one", reproduced=None),
            _comment(verdict="host_verified", identity="one"),
        ]
    )

    leg = host_leg_for_records(
        assertions=(_ASSERTION,),
        records=records,
        contains_merge=lambda ref: ref == _RELEASE_TAG,
    )

    assert leg.pending == (_ASSERTION,)
    assert leg.refused != ()


def test_a_record_naming_no_build_costs_no_comparison() -> None:
    """A replay with no ref to aim at is refused without a forge call.

    Asserted by RECORDING the refs the join asked about, because a wasted call returns
    a harmless `None` and is invisible in the verdict: the refusal looks identical
    whether the reader was consulted or not. The recorded list is the only instrument
    that separates them.
    """
    asked: list[str] = []

    def recording(*, ref: str) -> bool | None:
        asked.append(ref)
        return None

    records = proof_records(
        comments=[
            {
                "url": "https://example.test/c/9",
                "body": (
                    "Proof of Done — host_verified — session replaying — t\n\n"
                    f"## Assertion 1 — {_ASSERTION}\n\nReproduced: yes.\n"
                ),
            }
        ]
    )

    leg = host_leg_for_records(assertions=(_ASSERTION,), records=records, contains_merge=recording)

    assert asked == []
    assert leg.pending == (_ASSERTION,)
    # The POSITIVE CONTROL for the empty list above: a recorder that recorded nothing
    # because it was broken would satisfy `asked == []` vacuously, so prove it can.
    assert recording(ref=_RELEASE_TAG) is None
    assert asked == [_RELEASE_TAG]


def test_containment_is_read_through_the_forges_comparison_of_merge_against_build() -> None:
    """`identical` and `ahead` mean the named build carries the merge."""
    for status in ("ahead", "identical"):
        runner = _Runner(results=[_result(stdout=f"{status}\n")])
        assert (
            merge_contained_in(repo=_REPO, merge_sha=_MERGE_SHA, ref=_RELEASE_TAG, runner=runner)
            is True
        )
        assert runner.argvs == [compare_argv(base=_MERGE_SHA, head=_RELEASE_TAG)]


def test_a_build_behind_or_diverged_from_the_merge_does_not_contain_it() -> None:
    """The two statuses that say the merge is not in the named build's history."""
    for status in ("behind", "diverged"):
        runner = _Runner(results=[_result(stdout=f"{status}\n")])
        assert (
            merge_contained_in(repo=_REPO, merge_sha=_MERGE_SHA, ref=_RELEASE_TAG, runner=runner)
            is False
        )


def test_an_unreadable_or_unrecognised_comparison_is_unobservable_rather_than_either() -> None:
    """A failed read and an unknown status both answer `None`, which refuses.

    `None` is the third state the evidence rule needs: the comparison was not made,
    which is a different fact from "the build does not contain the merge" and must
    not be reported as one.
    """
    for result in (_result(exit_code=1), _result(stdout="something-new\n")):
        assert (
            merge_contained_in(
                repo=_REPO,
                merge_sha=_MERGE_SHA,
                ref=_RELEASE_TAG,
                runner=_Runner(results=[result]),
            )
            is None
        )
