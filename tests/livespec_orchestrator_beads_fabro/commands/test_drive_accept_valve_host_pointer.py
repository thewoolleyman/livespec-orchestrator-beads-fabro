"""`accept:<id>` resolves the pull request through a pointer that cites the host replay.

A mixed item whose pull request holds a factory `captured` record and an independent
`host_verified` replay for every host-captured assertion carries a pointer at that
replay, and the valve must read the pull request off it instead of refusing with
"the description carries no Proof of Done pointer".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._drive_accept_valve import accept_item
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_FACTORY = "The projection carries the parent field."
_HOST = "The released build prints its own version on an operator host."
_DESCRIPTION = (
    f"## Definition of Done\n\n- {_FACTORY}\n\n"
    f"### Host-captured\n\nReason: needs the released build.\n\n- {_HOST}\n\n"
    "References: ## Something\n"
    "\n## Proof of Done\n\n"
    "- Pull request: #11\n"
    "- Verified record: https://example.test/c/3\n"
    "- Run: session-b\n"
    "- Timestamp: 2026-10-29T10:07:30Z\n"
    "- Verdict: host_verified\n"
    "- Host-verified record: https://example.test/c/3\n"
)
_CAPTURED = (
    "Proof of Done — captured — run d547aa765bb3427cb43e70ebc9fd54a6 — 2026-10-27T00:46:00Z\n"
)
_REPLAY = (
    "Proof of Done — host_verified — session session-b — 2026-10-29T10:07:30Z\n\n"
    f"## Assertion 1 — {_HOST}\n\nReproduced: yes.\n"
)


@dataclass(kw_only=True)
class _Runner:
    stdout: str
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-aty",
        type="bug",
        status="acceptance",
        title="Task",
        description=_DESCRIPTION,
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-then-human",
        acceptance_criteria=None,
    )


def _comments(*, bodies: list[str]) -> str:
    entries = [{"url": "https://example.test/c/3", "body": body} for body in bodies]
    return json.dumps({"comments": entries})


def test_the_valve_reads_the_pull_request_off_a_pointer_at_the_host_replay(
    tmp_path: Path,
) -> None:
    item = _item()
    append_work_item(path=_config(), item=item)
    runner = _Runner(stdout=_comments(bodies=[_CAPTURED, _REPLAY]))

    result = accept_item(
        repo=tmp_path, config=_config(), item=item, action_id=f"accept:{item.id}", runner=runner
    )

    assert ["gh", "pr", "view", "11", "--json", "comments"] in runner.argvs
    assert result["status"] == "green"
    stored = materialize_work_items(records=read_work_items(path=_config()))[item.id]
    assert stored.status == "done"


def test_the_valve_still_refuses_while_no_replay_lists_the_assertion(tmp_path: Path) -> None:
    item = _item()
    append_work_item(path=_config(), item=item)
    runner = _Runner(stdout=_comments(bodies=[_CAPTURED]))

    result = accept_item(
        repo=tmp_path, config=_config(), item=item, action_id=f"accept:{item.id}", runner=runner
    )

    summary = str(result["summary"])
    assert result["status"] == "failed"
    assert "no host_verified record on pull request #11 lists them as reproduced" in summary
    assert "carries no Proof of Done pointer" not in summary
