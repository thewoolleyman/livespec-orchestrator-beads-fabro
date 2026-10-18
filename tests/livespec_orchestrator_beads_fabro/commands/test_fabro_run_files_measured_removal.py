"""A removal in the DEPLOYED server's nested entry shape.

THIS ARM IS UNMEASURED and the reader says so in its own code. The control read
on 2026-10-18 (hp :32276, run 01M57JEFQH7KJG4WVS0BFR82KA) carried `change_kind`
values `modified` and `added` and no removal at all, so neither the word the
server spells a deletion with nor what it puts in `new_file` for one was
observed. Both plausible spellings are therefore read as a removal:
`change_kind` holding `deleted` or `removed`, and a `new_file` of JSON null.

A REMOVAL MISREAD AS CONTENT IS THE ONE ERROR THAT CANNOT BE NOTICED. It
publishes the deleted file back into the preservation tree, and a file being
PRESENT looks like the normal case -- while the mirror error, a removal read for
a file the run merely changed, drops a file from the tree and shows up the first
time anyone opens it. So this reads BOTH spellings rather than picking one.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._fabro_run_files import (
    RunFiles,
    run_files_from_payload,
)

_GONE = "commands/_gone.py"


def test_a_change_kind_naming_a_deletion_reads_as_a_removal_and_not_as_bytes() -> None:
    for word in ("deleted", "removed", "Deleted"):
        read = run_files_from_payload(
            payload={
                "data": [
                    {
                        "change_kind": word,
                        "new_file": {"name": "", "contents": ""},
                        "old_file": {"name": _GONE, "contents": "synthetic before\n"},
                    }
                ]
            }
        )
        assert isinstance(read, RunFiles), (word, read)
        # The path comes from `old_file.name`: a removal's `new_file.name` is
        # the empty string, which is no path at all.
        assert tuple(changed.path for changed in read.files) == (_GONE,), word
        # `None` and not `b""`: a truncated file reports zero bytes and a
        # deleted one reports no content, and the tree entry each produces
        # differs -- a blob against a JSON null.
        assert read.files[0].content is None, word


def test_a_null_new_file_reads_as_a_removal_however_the_change_kind_is_spelled() -> None:
    read = run_files_from_payload(
        payload={
            "data": [
                {
                    "change_kind": "whatever-the-server-calls-it",
                    "new_file": None,
                    "old_file": {"name": _GONE, "contents": "synthetic before\n"},
                }
            ]
        }
    )
    assert isinstance(read, RunFiles), read
    assert tuple(changed.path for changed in read.files) == (_GONE,)
    assert read.files[0].content is None


def test_a_change_kind_naming_no_deletion_stays_on_the_content_path() -> None:
    read = run_files_from_payload(
        payload={
            "data": [
                {
                    "change_kind": "renamed",
                    "new_file": {"name": _GONE, "contents": "synthetic after\n"},
                    "old_file": {"name": "commands/_was.py", "contents": "synthetic before\n"},
                }
            ]
        }
    )
    assert isinstance(read, RunFiles), read
    assert read.files[0].content == b"synthetic after\n"
