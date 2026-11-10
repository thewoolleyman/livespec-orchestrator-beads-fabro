"""Tests for deleting a closed item's preservation refs from origin.

The deletion goes through the forge reference interface (`gh api`), never
`git push`, for the reason `_dispatcher_publish_branch_preserve` records: the
Dispatcher runs from the primary checkout, whose pre-push hook refuses every
push.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_preservation_ref_deletion import (
    delete_closed_item_refs,
    delete_ended_run_refs,
)

_MATCHING = "/repos/{owner}/{repo}/git/matching-refs/"
_REFS = "/repos/{owner}/{repo}/git/refs/"


@dataclass(kw_only=True)
class _Forge:
    """A forge that lists refs by prefix and records every deletion it is asked for."""

    refs: tuple[str, ...] = ()
    refuse_delete: frozenset[str] = frozenset()
    refuse_list: bool = False
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        if "DELETE" in argv:
            ref = "refs/" + argv[-1].removeprefix(_REFS)
            if ref in self.refuse_delete:
                return CommandResult(exit_code=1, stdout="", stderr="HTTP 422 protected")
            return CommandResult(exit_code=0, stdout="", stderr="")
        if self.refuse_list:
            return CommandResult(exit_code=1, stdout="", stderr="HTTP 502")
        prefix = "refs/" + argv[3].removeprefix(_MATCHING)
        listed = [ref for ref in self.refs if ref.startswith(prefix)]
        return CommandResult(exit_code=0, stdout="\n".join(listed) + "\n", stderr="")

    @property
    def deleted(self) -> list[str]:
        return ["refs/" + call[-1].removeprefix(_REFS) for call in self.calls if "DELETE" in call]


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_closing_an_item_deletes_every_wip_and_preserved_publish_ref_of_that_item(
    tmp_path: Path,
) -> None:
    forge = _Forge(
        refs=(
            "refs/livespec/wip/bd-ib-a/RUN1/1",
            "refs/livespec/wip/bd-ib-a/RUN1/2",
            "refs/livespec/wip/bd-ib-a/RUN2/1",
            "refs/livespec/preserved-publish/bd-ib-a/abc123",
            "refs/livespec/wip/bd-ib-ab/RUN9/1",
            "refs/livespec/preserved-publish/bd-ib-ab/def456",
            "refs/heads/needs-human/RUN1",
        )
    )
    journal = _Journal()

    complete = delete_closed_item_refs(
        runner=forge, repo=tmp_path, journal=journal, work_item_id="bd-ib-a"
    )

    assert complete is True
    assert forge.deleted == [
        "refs/livespec/wip/bd-ib-a/RUN1/1",
        "refs/livespec/wip/bd-ib-a/RUN1/2",
        "refs/livespec/wip/bd-ib-a/RUN2/1",
        "refs/livespec/preserved-publish/bd-ib-a/abc123",
    ]
    assert journal.records == []


def test_collecting_a_run_deletes_its_wip_refs_its_needs_human_ref_and_the_items_preserved_publish_refs(
    tmp_path: Path,
) -> None:
    forge = _Forge(
        refs=(
            "refs/livespec/wip/bd-ib-a/RUN1/1",
            "refs/livespec/wip/bd-ib-a/RUN1/2",
            "refs/livespec/wip/bd-ib-a/RUN2/1",
            "refs/livespec/preserved-publish/bd-ib-a/abc123",
            "refs/heads/needs-human/RUN1",
            "refs/heads/needs-human/RUN10",
        )
    )

    complete = delete_ended_run_refs(
        runner=forge,
        repo=tmp_path,
        journal=_Journal(),
        work_item_id="bd-ib-a",
        run_id="RUN1",
    )

    assert complete is True
    assert forge.deleted == [
        "refs/livespec/wip/bd-ib-a/RUN1/1",
        "refs/livespec/wip/bd-ib-a/RUN1/2",
        "refs/livespec/preserved-publish/bd-ib-a/abc123",
        "refs/heads/needs-human/RUN1",
    ]


def test_an_item_with_no_preservation_refs_deletes_nothing(tmp_path: Path) -> None:
    forge = _Forge(refs=("refs/livespec/wip/bd-ib-other/RUN1/1",))
    journal = _Journal()

    complete = delete_closed_item_refs(
        runner=forge, repo=tmp_path, journal=journal, work_item_id="bd-ib-a"
    )

    assert (complete, forge.deleted, journal.records) == (True, [], [])


def test_a_refused_deletion_is_journaled_with_its_ref_and_the_rest_are_still_attempted(
    tmp_path: Path,
) -> None:
    refused = "refs/livespec/wip/bd-ib-a/RUN1/1"
    forge = _Forge(
        refs=(refused, "refs/livespec/wip/bd-ib-a/RUN1/2"),
        refuse_delete=frozenset({refused}),
    )
    journal = _Journal()

    complete = delete_closed_item_refs(
        runner=forge, repo=tmp_path, journal=journal, work_item_id="bd-ib-a"
    )

    assert complete is False
    assert forge.deleted == [refused, "refs/livespec/wip/bd-ib-a/RUN1/2"]
    assert journal.records == [
        {
            "stage": "preservation-ref-deletion-failed",
            "work_item_id": "bd-ib-a",
            "operation": "delete",
            "ref": refused,
            "exit_code": 1,
            "detail": "HTTP 422 protected",
        }
    ]


def test_a_listing_the_forge_refuses_is_journaled_and_nothing_is_deleted(tmp_path: Path) -> None:
    forge = _Forge(refs=("refs/livespec/wip/bd-ib-a/RUN1/1",), refuse_list=True)
    journal = _Journal()

    complete = delete_closed_item_refs(
        runner=forge, repo=tmp_path, journal=journal, work_item_id="bd-ib-a"
    )

    assert complete is False
    assert forge.deleted == []
    assert [record["ref"] for record in journal.records] == [
        "refs/livespec/wip/bd-ib-a/",
        "refs/livespec/preserved-publish/bd-ib-a/",
    ]
    assert {record["operation"] for record in journal.records} == {"list"}
