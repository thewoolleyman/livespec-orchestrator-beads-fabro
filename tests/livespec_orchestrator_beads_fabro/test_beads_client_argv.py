"""Tests for pure beads argv and record builders."""

from __future__ import annotations

import json

import pytest
from livespec_orchestrator_beads_fabro._beads_client import IssueDraft
from livespec_orchestrator_beads_fabro._beads_client_argv import (
    build_create_argv,
    build_no_history_create_argv,
    build_update_argv,
    coerce_created_id,
    coerce_record_list,
)
from livespec_orchestrator_beads_fabro.errors import BeadsMappingError


def _draft(**overrides: object) -> IssueDraft:
    base: dict[str, object] = {
        "issue_id": "li-a",
        "issue_type": "task",
        "title": "title",
        "description": "desc",
        "priority": 2,
        "assignee": None,
        "created_at": "2026-05-19T00:00:00Z",
    }
    base.update(overrides)
    return IssueDraft(**base)  # type: ignore[arg-type]


def test_build_create_argv_full_field_set() -> None:
    draft = _draft(
        issue_id="li-a",
        assignee="alice",
        spec_id="topic-x",
        parent_id="li-epic",
        labels=["origin:freeform", "gap-id:G1"],
        metadata={"audit": {"merge_sha": "sha"}},
        acceptance_criteria="Run just check.",
        notes="Keep scope narrow.",
    )
    argv = build_create_argv(draft=draft)
    assert argv[0] == "create"
    assert "--id" in argv
    assert "li-a" in argv
    assert "--type" in argv
    assert "--title" in argv
    assert "--description" in argv
    assert "--priority" in argv
    assert "2" in argv
    assert "--created-at" not in argv
    assert "--assignee" in argv
    assert "alice" in argv
    assert "--spec-id" in argv
    assert "topic-x" in argv
    assert "--parent" in argv
    assert "li-epic" in argv
    assert "--acceptance" in argv
    assert "Run just check." in argv
    assert "--notes" in argv
    assert "Keep scope narrow." in argv
    assert argv.count("--label") == 2
    assert "origin:freeform" in argv
    assert "gap-id:G1" in argv
    meta_index = argv.index("--metadata")
    assert json.loads(argv[meta_index + 1]) == {"audit": {"merge_sha": "sha"}}


def test_build_create_argv_omits_optional_flags_when_absent() -> None:
    argv = build_create_argv(draft=_draft(assignee=None, spec_id=None, parent_id=None))
    assert "--assignee" not in argv
    assert "--spec-id" not in argv
    assert "--parent" not in argv
    assert "--acceptance" not in argv
    assert "--notes" not in argv
    assert argv.count("--label") == 0


def test_build_update_argv_full() -> None:
    argv = build_update_argv(
        issue_id="li-a",
        status="closed",
        parent_id="li-epic",
        add_labels=["resolution:completed"],
        metadata={"audit": {"merge_sha": "sha"}},
        acceptance_criteria="Updated acceptance.",
        notes="Updated notes.",
    )
    assert argv[:2] == ["update", "li-a"]
    assert "--status" in argv
    assert "closed" in argv
    assert "--parent" in argv
    assert "li-epic" in argv
    assert "--label" not in argv
    assert argv.count("--add-label") == 1
    add_index = argv.index("--add-label")
    assert argv[add_index + 1] == "resolution:completed"
    acceptance_index = argv.index("--acceptance")
    assert argv[acceptance_index + 1] == "Updated acceptance."
    notes_index = argv.index("--notes")
    assert argv[notes_index + 1] == "Updated notes."
    assert "--metadata" in argv


def test_build_update_argv_includes_assignee() -> None:
    argv = build_update_argv(
        issue_id="li-a",
        status="active",
        parent_id=None,
        add_labels=None,
        metadata=None,
        assignee="fabro",
    )
    assert argv[:2] == ["update", "li-a"]
    assert "--status" in argv
    assert "active" in argv
    assignee_index = argv.index("--assignee")
    assert argv[assignee_index + 1] == "fabro"


def test_build_update_argv_can_clear_assignee() -> None:
    argv = build_update_argv(
        issue_id="li-a",
        status="ready",
        parent_id=None,
        add_labels=None,
        metadata=None,
        clear_assignee=True,
    )
    assignee_index = argv.index("--assignee")
    assert argv[assignee_index + 1] == ""


def test_build_update_argv_repeats_add_label_per_label() -> None:
    argv = build_update_argv(
        issue_id="li-a",
        status=None,
        parent_id=None,
        add_labels=["origin:freeform", "gap-id:G1"],
        metadata=None,
    )
    assert "--label" not in argv
    assert argv.count("--add-label") == 2
    assert "origin:freeform" in argv
    assert "gap-id:G1" in argv


def test_build_update_argv_bare_is_noop_length() -> None:
    argv = build_update_argv(
        issue_id="li-a",
        status=None,
        parent_id=None,
        add_labels=None,
        metadata=None,
    )
    assert argv == ["update", "li-a"]


def test_coerce_record_list_bare_array_filters_non_dicts() -> None:
    out = coerce_record_list(parsed=[{"id": "li-a"}, "junk", 7])
    assert out == [{"id": "li-a"}]


def test_coerce_record_list_envelope() -> None:
    out = coerce_record_list(parsed={"issues": [{"id": "li-a"}, "junk"]})
    assert out == [{"id": "li-a"}]


def test_coerce_record_list_unknown_shape_raises() -> None:
    with pytest.raises(BeadsMappingError):
        _ = coerce_record_list(parsed={"not_issues": []})


def test_coerce_record_list_scalar_raises() -> None:
    with pytest.raises(BeadsMappingError):
        _ = coerce_record_list(parsed=42)


def test_build_no_history_create_argv_carries_no_id_flag() -> None:
    """The token create NEVER names an id — that is what makes it an exclusion.

    An explicit-id create is an upsert that reopens a closed record and erases
    its close reason (relay research note 007), so the absence of `--id` here
    is load-bearing rather than incidental.
    """
    argv = build_no_history_create_argv(title="token", description="single-use")
    assert argv == [
        "create",
        "--type",
        "task",
        "--title",
        "token",
        "--description",
        "single-use",
        "--no-history",
        "--json",
    ]
    assert "--id" not in argv


def test_coerce_created_id_reads_the_bare_object_and_the_one_element_array() -> None:
    assert coerce_created_id(parsed={"id": "bd-ib-wisp-01"}) == "bd-ib-wisp-01"
    assert coerce_created_id(parsed=[{"id": "bd-ib-wisp-02"}]) == "bd-ib-wisp-02"


def test_coerce_created_id_refuses_every_body_carrying_no_id() -> None:
    for parsed in ([], 42, {"no_id": "x"}, {"id": 7}, {"id": ""}):
        with pytest.raises(BeadsMappingError):
            _ = coerce_created_id(parsed=parsed)
