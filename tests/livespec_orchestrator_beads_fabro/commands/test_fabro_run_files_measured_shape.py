"""The run-files shape the DEPLOYED factory server actually serves.

MEASURED on hp :32276 through this repository's own server-API port on
2026-10-18, against run 01M57JEFQH7KJG4WVS0BFR82KA (HTTP 200, 601960 bytes,
four committed changes): every entry nests its path and its bytes under
`new_file` / `old_file`, names its change state `change_kind`, and carries NO
top-level `path`, `name` or `content` key at all. The response's `meta` carries
`scope` and `source`, which say which scope the server read and where it read
it from.

So the reader's tolerant top-level keys matched nothing on every real run, and
a checkpoint-failed ending would have written the "tree was NOT preserved"
comment and published no ref -- while reporting a parse failure rather than the
shape mismatch that caused it.

THE CONTENTS HERE ARE SYNTHETIC ON PURPOSE, and only the SHAPE is measured. The
run this was read from changed `workflow.fabro`, which carries MiniJinja
openers; an opener that reaches a ledger comment refuses every later dispatch of
the item carrying it, permanently.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._fabro_run_files import (
    RunFiles,
    run_files_from_payload,
)

_MODIFIED_PATH = "commands/_fabro_run_files.py"
_ADDED_PATH = "tests/commands/test_fabro_run_files.py"


def _measured_payload() -> dict[str, object]:
    """The measured response, with two of its entries and synthetic bytes."""
    return {
        "data": [
            {
                "change_kind": "modified",
                "new_file": {"name": _MODIFIED_PATH, "contents": "synthetic modified\n"},
                "old_file": {"name": _MODIFIED_PATH, "contents": "synthetic before\n"},
            },
            {
                "change_kind": "added",
                "new_file": {"name": _ADDED_PATH, "contents": "synthetic added\n"},
                "old_file": {"name": "", "contents": ""},
            },
        ],
        "meta": {
            "degraded": False,
            "scope": "committed",
            "source": "sandbox",
            "stats": {"additions": 559, "deletions": 3},
            "to_sha": "9b763c0a86f6536aa2d17836802815e9ec9e953d",
            "total_changed": 2,
            "truncated": False,
        },
    }


def test_the_deployed_servers_nested_entries_read_as_the_runs_changed_files() -> None:
    read = run_files_from_payload(payload=_measured_payload())
    assert isinstance(read, RunFiles), read
    assert tuple(changed.path for changed in read.files) == (_MODIFIED_PATH, _ADDED_PATH)
    assert tuple(changed.content for changed in read.files) == (
        b"synthetic modified\n",
        b"synthetic added\n",
    )
    # An added entry's `old_file.name` is the empty string, which must not be
    # read as the path of a file at the repository root.
    assert tuple(changed.mode for changed in read.files) == ("100644", "100644")


def test_the_responses_meta_names_the_scope_read_and_where_it_was_read_from() -> None:
    read = run_files_from_payload(payload=_measured_payload())
    assert isinstance(read, RunFiles), read
    assert (read.scope, read.source) == ("committed", "sandbox")


def test_a_response_carrying_no_readable_meta_reports_neither_scope_nor_source() -> None:
    entry = {"new_file": {"name": "a.py", "contents": "x\n"}}
    for payload in ({"data": [entry]}, {"data": [entry], "meta": "committed"}, [entry]):
        read = run_files_from_payload(payload=payload)
        assert isinstance(read, RunFiles), payload
        assert (read.scope, read.source) == (None, None), payload
