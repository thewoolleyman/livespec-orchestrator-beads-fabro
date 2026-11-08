"""Tests for the verified reader behind blob-backed stage diffs."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._fabro_stage_diffs import (
    stage_diffs_from_run_state,
    write_stage_diffs,
)


def test_blob_references_write_the_addressed_bytes_only_after_their_digest_verifies(
    tmp_path: Path,
) -> None:
    payload = b"diff --git a/app.py b/app.py\n+binary \xff\n"
    digest = hashlib.sha256(payload).hexdigest()
    stage_diffs = stage_diffs_from_run_state(
        run_state={
            "stages": {
                "implement@1": {
                    "first_event_seq": 239551,
                    "dump_ordinal": 55,
                    "diff": f"blob://sha256/{digest}",
                }
            }
        },
        read_blob=lambda blob_sha256: payload
        if blob_sha256 == digest
        else pytest.fail(f"unexpected blob {blob_sha256}"),
    )

    artifacts = write_stage_diffs(stage_diffs=stage_diffs, output_dir=tmp_path)

    assert artifacts[0].read_bytes() == payload


@pytest.mark.parametrize(
    ("diff", "read_blob"),
    [
        ("blob://sha256/not-a-digest", None),
        (f"blob://sha256/{'a' * 64}", None),
    ],
)
def test_blob_references_without_a_readable_address_yield_no_artifact(
    diff: str,
    read_blob: Callable[[str], bytes] | None,
) -> None:
    assert (
        stage_diffs_from_run_state(
            run_state={
                "stages": {
                    "implement@1": {
                        "first_event_seq": 1,
                        "dump_ordinal": 1,
                        "diff": diff,
                    }
                }
            },
            read_blob=read_blob,
        )
        == ()
    )
