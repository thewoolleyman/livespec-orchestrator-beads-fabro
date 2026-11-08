"""Tests for rebuilding dump-compatible diff artifacts from a run projection."""

from __future__ import annotations

import hashlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._fabro_stage_diffs import (
    stage_diffs_from_run_state,
    write_stage_diffs,
)


def test_projection_diffs_have_the_same_paths_bytes_sizes_and_digests_as_a_dump(
    tmp_path: Path,
) -> None:
    implement = "diff --git a/app.py b/app.py\n+print('implemented')\n"
    repair = "diff --git a/app.py b/app.py\n+print('repaired')\n"
    stage_diffs = stage_diffs_from_run_state(
        run_state={
            "stages": {
                "fix@1": {"first_event_seq": 6, "diff": repair},
                "implement@1": {"first_event_seq": 2, "diff": implement},
                "review@1": {"first_event_seq": 4, "diff": None},
            }
        }
    )

    artifacts = write_stage_diffs(stage_diffs=stage_diffs, output_dir=tmp_path)

    expected = {
        "stages/001-fix@1/diff.patch": repair.encode(),
        "stages/002-implement@1/diff.patch": implement.encode(),
    }
    actual = {
        artifact.relative_to(tmp_path).as_posix(): artifact.read_bytes() for artifact in artifacts
    }
    assert actual == expected
    assert [(len(payload), hashlib.sha256(payload).hexdigest()) for payload in actual.values()] == [
        (len(payload), hashlib.sha256(payload).hexdigest()) for payload in expected.values()
    ]


def test_projection_uses_the_dump_stage_ordinal_not_its_event_sequence(tmp_path: Path) -> None:
    """A captured state projection's event sequence is not its dump directory ordinal."""
    dump_patch = b"diff --git a/app.py b/app.py\n+print('implemented')\n"
    stage_diffs = stage_diffs_from_run_state(
        run_state={
            "stages": {
                "implement@1": {
                    "first_event_seq": 239551,
                    "dump_ordinal": 55,
                    "diff": dump_patch.decode(),
                }
            }
        }
    )

    artifacts = write_stage_diffs(stage_diffs=stage_diffs, output_dir=tmp_path)

    actual = {
        artifact.relative_to(tmp_path).as_posix(): artifact.read_bytes() for artifact in artifacts
    }
    assert actual == {"stages/055-implement@1/diff.patch": dump_patch}


def test_projection_derives_the_dump_ordinal_from_the_ordered_stage_projection(
    tmp_path: Path,
) -> None:
    """The captured `/state` mapping has no dump_ordinal but preserves stage order.

    The dump for the captured run writes ``055-implement@1``.  Its event
    sequence is 239551, so using that sequence as a directory rank produces
    the wrong pointer path.  The 54 earlier (diff-less) stage entries still
    occupy dump ordinals and must be counted.
    """
    dump_patch = b"diff --git a/app.py b/app.py\n+print('implemented')\n"
    stages = {
        **{
            f"prior-{index:03d}@1": {"first_event_seq": index, "diff": None}
            for index in range(1, 55)
        },
        "implement@1": {"first_event_seq": 239551, "diff": dump_patch.decode()},
    }

    stage_diffs = stage_diffs_from_run_state(run_state={"stages": stages})

    artifacts = write_stage_diffs(stage_diffs=stage_diffs, output_dir=tmp_path)

    assert {
        artifact.relative_to(tmp_path).as_posix(): artifact.read_bytes() for artifact in artifacts
    } == {"stages/055-implement@1/diff.patch": dump_patch}


def test_unreadable_or_diff_less_projection_yields_no_artifacts(tmp_path: Path) -> None:
    assert stage_diffs_from_run_state(run_state=None) == ()
    assert stage_diffs_from_run_state(run_state={"stages": []}) == ()
    assert (
        stage_diffs_from_run_state(
            run_state={"stages": {"review@1": {"first_event_seq": 1}, "malformed": []}}
        )
        == ()
    )
    assert write_stage_diffs(stage_diffs=(), output_dir=tmp_path) == ()
