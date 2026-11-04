"""The pull requests an item's dispatch records name reach the run's environment.

`publish_draft` ends a run as a landed publication only for a merged pull request
the item's dispatch records name, so the journal reading and the overlay line it
renders are what that gate stands on. The journal keeps a pull request number at
the top level of some records and inside the `outcome` payload of others, which
is why both shapes are asserted.
"""

from __future__ import annotations

import json
from pathlib import Path

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_pull_requests import (
    DISPATCH_PULL_REQUESTS_ENV_VAR,
    dispatch_pull_requests_env_line,
    journaled_pull_request_numbers,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

_ENVIRONMENT_ID = "sandbox"
_WORKFLOW_TOML = (
    f'[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "{_ENVIRONMENT_ID}"\n'
)
_ITEM = "bd-ib-weje2m"

# Opaque non-secret placeholders: the overlay renders whatever it is handed, and
# a literal spelled like a credential at the call site reads as a hardcoded one.
_FAKE_TOKEN = "overlay-token-placeholder"
_FAKE_GITHUB_TOKEN = "overlay-github-placeholder"


def _journal(*, tmp_path: Path, records: list[dict[str, object]]) -> Path:
    path = tmp_path / "journal.jsonl"
    path.write_text("".join(json.dumps(one) + "\n" for one in records), encoding="utf-8")
    return path


def test_both_record_shapes_are_read_ascending_and_once_each(tmp_path: Path) -> None:
    journal = _journal(
        tmp_path=tmp_path,
        records=[
            {"work_item_id": _ITEM, "pr_number": 3731},
            {"outcome": {"work_item_id": _ITEM, "pr_number": 12}},
            {"outcome": {"work_item_id": _ITEM, "pr_number": 3731}},
        ],
    )

    assert journaled_pull_request_numbers(journal_path=journal, work_item_id=_ITEM) == (12, 3731)


def test_another_items_records_and_unusable_numbers_are_not_read(tmp_path: Path) -> None:
    journal = _journal(
        tmp_path=tmp_path,
        records=[
            {"work_item_id": "bd-ib-other", "pr_number": 99},
            {"work_item_id": _ITEM, "pr_number": None},
            {"work_item_id": _ITEM, "pr_number": True},
            {"work_item_id": _ITEM, "pr_number": "7"},
            {"work_item_id": _ITEM},
        ],
    )

    assert journaled_pull_request_numbers(journal_path=journal, work_item_id=_ITEM) == ()


def test_an_absent_journal_names_no_pull_request(tmp_path: Path) -> None:
    absent = tmp_path / "never-written.jsonl"

    assert dispatch_pull_requests_env_line(journal_path=absent, work_item_id=_ITEM) == (
        f'{DISPATCH_PULL_REQUESTS_ENV_VAR} = ""\n'
    )


def test_the_numbers_ride_the_runs_environment_table_as_one_value(tmp_path: Path) -> None:
    journal = _journal(
        tmp_path=tmp_path,
        records=[
            {"work_item_id": _ITEM, "pr_number": 3731},
            {"outcome": {"work_item_id": _ITEM, "pr_number": 12}},
        ],
    )
    rendered = render_run_config_overlay(
        committed_text=_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        dispatch_pull_requests_env=dispatch_pull_requests_env_line(
            journal_path=journal, work_item_id=_ITEM
        ),
    )

    assert rendered is not None
    env = tomli.loads(rendered)["environments"][_ENVIRONMENT_ID]["env"]
    assert env[DISPATCH_PULL_REQUESTS_ENV_VAR] == "12 3731"
