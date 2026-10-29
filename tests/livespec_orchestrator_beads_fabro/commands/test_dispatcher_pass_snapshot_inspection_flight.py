"""A dispatch pass's inspect memo never serializes inspects and never loses a failed reading.

Binds the concurrency half of the third assertion of work-item bd-ib-6bbcda's
Definition of Done: within one dispatch pass the Dispatcher issues at most one
`fabro inspect` for each distinct pair of factory and run id, and it does so
without making the readers of DIFFERENT runs wait on one another.

The selection-replay lane fans its inspects out across worker threads, so a memo
that held its lock across the read would serialize them while still passing every
single-threaded case. Each case here is a thread interleaving that such a memo, or
one that lost a raised reading, gets wrong while returning a plausible result.
"""

from __future__ import annotations

import threading
import time

from livespec_orchestrator_beads_fabro.commands._dispatcher_pass_snapshot import (
    memoized_inspection,
    pass_snapshot,
)

_HP = "https://hp.example:32276"


_WAIT_SECONDS = 5.0


def test_inspections_of_different_runs_overlap_inside_one_pass() -> None:
    """A slow inspect of one run never holds back the inspect of another.

    The selection-replay lane fans its inspects out across worker threads, so a
    memo that serialized them behind one lock would hand back the pass's nine
    seconds per run one after another while still passing every single-threaded
    case. The first reader waits for the second to start INSIDE its own read, so
    the flag is true only when the two reads were in flight together.
    """
    first_in = threading.Event()
    second_in = threading.Event()
    overlapped: list[bool] = []

    def read_first() -> str:
        first_in.set()
        overlapped.append(second_in.wait(timeout=_WAIT_SECONDS))
        return "first"

    def read_second() -> str:
        second_in.set()
        return "second"

    with pass_snapshot():
        one = threading.Thread(
            target=lambda: memoized_inspection(factory=_HP, run_id="run-1", read=read_first)
        )
        two = threading.Thread(
            target=lambda: memoized_inspection(factory=_HP, run_id="run-2", read=read_second)
        )
        one.start()
        assert first_in.wait(timeout=_WAIT_SECONDS)
        two.start()
        one.join()
        two.join()
    assert overlapped == [True]


def test_two_readers_of_one_run_share_a_single_reading_in_flight() -> None:
    reads: list[str] = []
    results: list[str] = []
    entered = threading.Event()
    release = threading.Event()

    def slow() -> str:
        reads.append("read")
        entered.set()
        _ = release.wait(timeout=_WAIT_SECONDS)
        return "value"

    with pass_snapshot():
        leader = threading.Thread(
            target=lambda: results.append(
                memoized_inspection(factory=_HP, run_id="run-1", read=slow)
            )
        )
        follower = threading.Thread(
            target=lambda: results.append(
                memoized_inspection(factory=_HP, run_id="run-1", read=lambda: "other")
            )
        )
        leader.start()
        assert entered.wait(timeout=_WAIT_SECONDS)
        follower.start()
        release.set()
        leader.join()
        follower.join()
    assert reads == ["read"]
    assert results == ["value", "value"]


def test_a_reading_that_raised_is_taken_again_by_the_reader_waiting_on_it() -> None:
    errors: list[str] = []
    results: list[str] = []
    entered = threading.Event()
    fail = threading.Event()

    def failing() -> str:
        entered.set()
        _ = fail.wait(timeout=_WAIT_SECONDS)
        raise RuntimeError("boom")

    def catching() -> None:
        try:
            _ = memoized_inspection(factory=_HP, run_id="run-1", read=failing)
        except RuntimeError as error:
            errors.append(str(error))

    with pass_snapshot():
        leader = threading.Thread(target=catching)
        follower = threading.Thread(
            target=lambda: results.append(
                memoized_inspection(factory=_HP, run_id="run-1", read=lambda: "fresh")
            )
        )
        leader.start()
        assert entered.wait(timeout=_WAIT_SECONDS)
        follower.start()
        time.sleep(0.3)
        fail.set()
        leader.join()
        follower.join()
        again = memoized_inspection(factory=_HP, run_id="run-1", read=lambda: "unused")
    assert errors == ["boom"]
    assert results == ["fresh"]
    assert again == "fresh"
