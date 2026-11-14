"""Edge arms of the completed-cycle series derivation.

Beside `test_dispatcher_completed_cycles`, which pins what a pair IS, this file
exercises the arms a malformed provenance reaches: a pair whose preserved Red
instant does not parse, and a pair carrying no Red test-file checksum to be
identified by.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    ProvenanceCommit,
    verified_pairs,
)


def _message(*, red_at: str, green_at: str, checksum: str | None = None) -> str:
    lines = ["feat(dispatcher): one assertion", "", "Body prose.", ""]
    if checksum is not None:
        lines.append(f"TDD-Red-Test-File-Checksum: {checksum}")
    lines.append(f"TDD-Red-Captured-At: {red_at}")
    lines.append(f"TDD-Green-Verified-At: {green_at}")
    return "\n".join(lines) + "\n"


def test_a_pair_whose_red_instant_does_not_parse_still_counts_and_sorts_last() -> None:
    pairs = verified_pairs(
        commits=(
            ProvenanceCommit(
                sha="unparseable",
                message=_message(red_at="whenever", green_at="also-whenever", checksum="sha256:x"),
            ),
            ProvenanceCommit(
                sha="dated",
                message=_message(
                    red_at="2026-10-01T10:00:00Z",
                    green_at="2026-10-01T10:04:10Z",
                    checksum="sha256:y",
                ),
            ),
        )
    )

    assert [source.commit for source in pairs] == ["dated", "unparseable"]


def test_a_pair_with_no_red_checksum_is_identified_by_its_commit() -> None:
    pairs = verified_pairs(
        commits=(
            ProvenanceCommit(
                sha="abc1234",
                message=_message(red_at="2026-10-01T10:00:00Z", green_at="2026-10-01T10:04:10Z"),
            ),
        )
    )

    assert [source.pair_id for source in pairs] == ["commit:abc1234"]
