"""What the factory SERVED, carried onto the durable preserved-tree record.

The server's run-files response says which scope it answered from (`committed`
on the 2026-10-18 control read) and where it read that from (`sandbox` on that
run, `final_patch` on another). Those two readings decide what the preservation
ref actually contains, and the ledger comment is the only record that outlives
the run -- so an operator who cannot read them off the comment cannot tell a ref
carrying the run's committed work from one carrying its uncommitted work too.

The first real checkpoint-failed ending is the only thing that can establish
which of those a dying run is served, and it can only establish it if the
record names it.
"""

from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree import publish_run_tree
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    PreservedTree,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    preserved_tree_body,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import (
    FabroHttpPort,
    FabroHttpResult,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroTarget

_BASE_COMMIT = "5d511335aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_RUN_ID = "01M4YJGC55V86C9V1X07QG3Y2H"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_COMMIT = "c0mm1tc0mm1tc0mm1tc0mm1tc0mm1tc0mm1tc0mm"
_REF = f"refs/livespec/preserved-publish/bd-ib-na2xvm/{_COMMIT}"

# The measured response shape, with synthetic bytes. Only the shape and the
# `meta` keys are measured; the contents are invented, because the run this was
# read from changed a file carrying MiniJinja openers.
_SERVED_PAYLOAD = {
    "data": [
        {
            "change_kind": "modified",
            "new_file": {"name": "a.py", "contents": "synthetic\n"},
            "old_file": {"name": "a.py", "contents": "before\n"},
        }
    ],
    "meta": {"scope": "committed", "source": "sandbox", "total_changed": 1},
}


def _carries_the_served_reading() -> bool:
    """Whether the publication result carries what the factory served at all."""
    return {"scope", "source"} <= {field.name for field in dataclasses.fields(PreservedTree)}


@dataclass(kw_only=True)
class _ServedTransport:
    """Answer the run-files route with the measured served payload."""

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        _ = method
        _ = url
        _ = headers
        _ = body
        _ = timeout_seconds
        return FabroHttpResult(
            status=200,
            body=json.dumps(_SERVED_PAYLOAD),
            error=None,
            payload=None,
            succeeded=True,
        )


@dataclass(kw_only=True)
class _ApiRunner:
    """Answer each `gh api` call with a canned object name."""

    answers: list[str] = field(
        default_factory=lambda: ["basetree", "blob1", "treesha", _COMMIT, ""]
    )
    calls: int = 0

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = argv
        _ = cwd
        _ = timeout_seconds
        _ = env
        if stdin is not None:
            _ = os.pread(stdin, 1_000_000, 0)
        index = self.calls
        self.calls += 1
        answer = self.answers[index] if index < len(self.answers) else ""
        return CommandResult(exit_code=0, stdout=f"{answer}\n", stderr="")


def test_the_comment_names_the_scope_the_factory_served_and_where_it_read_it() -> None:
    assert _carries_the_served_reading(), sorted(
        field.name for field in dataclasses.fields(PreservedTree)
    )
    body = preserved_tree_body(
        work_item_id="bd-ib-na2xvm",
        run_id=_RUN_ID,
        factory="hp",
        base_commit=_BASE_COMMIT,
        preserved=PreservedTree(
            ref=_REF,
            commit=_COMMIT,
            file_count=48,
            scope="committed",
            source="sandbox",
        ),
    )
    assert "committed" in body
    assert "sandbox" in body


def test_a_read_that_served_neither_says_so_rather_than_dropping_the_lines() -> None:
    assert _carries_the_served_reading(), sorted(
        field.name for field in dataclasses.fields(PreservedTree)
    )
    body = preserved_tree_body(
        work_item_id="bd-ib-na2xvm",
        run_id=_RUN_ID,
        factory="hp",
        base_commit=_BASE_COMMIT,
        preserved=PreservedTree(ref=_REF, commit=_COMMIT, file_count=48, scope=None, source=None),
    )
    # An OMITTED line is what a record from a build predating this reading looks
    # like, so an unreported scope is stated rather than left out.
    scoped = [line for line in body.splitlines() if line.startswith("served scope:")]
    sourced = [line for line in body.splitlines() if line.startswith("served source:")]
    assert len(scoped) == 1, body
    assert len(sourced) == 1, body
    assert "committed" not in scoped[0]
    assert "sandbox" not in sourced[0]


def test_the_publication_carries_what_the_read_was_served_rather_than_re_deriving_it() -> None:
    assert _carries_the_served_reading(), sorted(
        field.name for field in dataclasses.fields(PreservedTree)
    )
    published = publish_run_tree(
        port=FabroHttpPort(target=FabroTarget(server_url=_SERVER), transport=_ServedTransport()),
        runner=_ApiRunner(),
        repo=Path("/nonexistent"),
        work_item_id="bd-ib-na2xvm",
        run_id=_RUN_ID,
        base_commit=_BASE_COMMIT,
    )
    assert isinstance(published, PreservedTree), published
    assert (published.scope, published.source) == ("committed", "sandbox")
