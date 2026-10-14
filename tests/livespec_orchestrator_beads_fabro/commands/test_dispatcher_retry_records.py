"""Tests for the retry-discipline record format.

THE RENDER IS ASSERTED AS EXACT BYTES, not as a set of substrings. The parse on
the other side of this module reads a line-oriented header, so the thing that
has to hold is that each field occupies its own `key: value` line — a substring
assertion passes for a body that ran two fields together and the parse would
then lose one of them.

EVERY FIELD IS EMITTED ON EVERY KIND, empty values included, and that is
asserted rather than assumed: an omitted key is what a record from a build
predating that key looks like, so a reader could not tell "this kind carries no
reason" from "the reason was lost".
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest

_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_retry_records"


def _module() -> ModuleType:
    assert (_COMMANDS_DIR / "_dispatcher_retry_records.py").is_file()
    return importlib.import_module(_MODULE_NAME)


def test_a_rendered_signature_puts_every_field_on_its_own_line() -> None:
    module = _module()

    body = module.render_retry_record(
        record=module.RetryRecord(
            kind=module.REFUSAL_SIGNATURE_KIND,
            stage="fabro-run",
            error_class="deterministic",
            build=module.ExecutingBuild(version="0.196.1", plugin_root="/cache/0196"),
            recorded_at="2026-10-14T01:02:03Z",
        )
    )

    assert body == (
        "livespec-dispatch-retry-discipline\n"
        "kind: refusal-signature\n"
        "stage: fabro-run\n"
        "error-class: deterministic\n"
        "build-version: 0.196.1\n"
        "plugin-root: /cache/0196\n"
        "recorded-at: 2026-10-14T01:02:03Z\n"
        "reason: \n"
        "overrode-stage: \n"
        "overrode-error-class: \n"
    )
    assert module.RETRY_DISCIPLINE_PREFIX == "livespec-dispatch-retry-discipline"


def test_a_named_change_record_carries_its_reason_and_what_it_overrode() -> None:
    module = _module()

    body = module.render_retry_record(
        record=module.RetryRecord(
            kind=module.NAMED_CHANGE_KIND,
            stage="fabro-run",
            error_class="deterministic",
            build=module.ExecutingBuild(version="0.196.1", plugin_root="/cache/0196"),
            recorded_at="2026-10-14T01:02:03Z",
            reason="rebound to a build carrying the checkpoint-commit fix",
            overrode_stage="fabro-run",
            overrode_error_class="deterministic",
        )
    )

    assert "kind: named-change\n" in body
    assert "reason: rebound to a build carrying the checkpoint-commit fix\n" in body
    assert "overrode-stage: fabro-run\n" in body
    assert "overrode-error-class: deterministic\n" in body


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("one line", "one line"),
        ("two\nlines", "two lines"),
        ("  padded \t and   spaced \n", "padded and spaced"),
        ("", ""),
    ],
)
def test_a_reason_is_collapsed_to_one_line(given: str, expected: str) -> None:
    assert _module().one_line(text=given) == expected


def test_a_multi_line_reason_cannot_split_the_record_header() -> None:
    module = _module()

    body = module.render_retry_record(
        record=module.RetryRecord(
            kind=module.NAMED_CHANGE_KIND,
            stage="fabro-run",
            error_class="deterministic",
            build=module.ExecutingBuild(version="0.1.0", plugin_root="/cache"),
            recorded_at="2026-10-14T01:02:03Z",
            reason="first\nkind: refusal-signature",
        )
    )

    assert len(body.splitlines()) == 10
    assert "reason: first kind: refusal-signature\n" in body


def test_the_unclassified_and_unknown_names_are_stated_rather_than_empty() -> None:
    module = _module()

    assert module.UNCLASSIFIED_ERROR_CLASS == "unclassified"
    assert module.UNKNOWN_BUILD_VERSION == "unknown"
