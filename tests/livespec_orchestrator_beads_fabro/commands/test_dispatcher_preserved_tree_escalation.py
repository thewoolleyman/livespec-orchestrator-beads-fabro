"""The leg that reads the factory, publishes, and writes the durable record.

WHAT IT MEANS FOR THIS LEG TO BE WRONG. The ratified clause makes the ledger
comment the ONLY durable pointer at the preservation ref: the dispatch result is
read once, the journal lives in the `tmp/` tree of whichever host ran the
dispatch, and the factory prunes the run. So a leg that publishes a ref and
fails to name it has produced a durable artifact nobody can find, which at every
surface is indistinguishable from never having published at all.

THE TWO FAIL-SOFT ARMS ARE WHY THIS TIER EXISTS. A failed publication and a
refused ledger write must each leave the dispatch's own outcome and exit code
UNCHANGED, because the item's rest state is `blocked` / `needs-human` either way
and a preservation that could not be taken must never convert an ended run into
a dispatch failure after the fact. Neither arm is observable from the pure
disposition, which is handed its inputs already read.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_preserved_tree_escalation as escalation,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_base import SOURCE_STAGE
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_escalation import (
    PRESERVED_TREE_UNREACHABLE_STAGE,
    PreservationInputs,
    preserve_checkpoint_failed_tree,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_MARKER,
    PRESERVED_TREE_RECORD_STAGE,
    PRESERVED_TREE_SKIPPED_STAGE,
    PRESERVED_TREE_STAGE,
    PRESERVED_TREE_UNPRESERVED_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM = "bd-ib-na2xvm"
_RUN = "01M4YJGC55V86C9V1X07QG3Y2H"
_FACTORY = "hp"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_BASE = "5d511335aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_COMMIT = "c" * 40
# The engine's own wording for the ending, measured on the incident run.
_CHECKPOINT_FAILED = "git checkpoint commit failed for node implement: git add failed (exit 127)"

# The object name the forge gives each Git Data write, keyed by its endpoint.
# The base-commit READ is keyed by its own path, which is what makes the tree
# the publication is built over distinguishable from the tree it creates.
_FORGE_NAMES = {
    f"/repos/{{owner}}/{{repo}}/git/commits/{_BASE}": "a" * 40,
    "/repos/{owner}/{repo}/git/blobs": "b" * 40,
    "/repos/{owner}/{repo}/git/trees": "7" * 40,
    "/repos/{owner}/{repo}/git/commits": _COMMIT,
}


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _write_config(project_root: Path) -> None:
    _ = (project_root / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "bd",
      "server_user": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "bd_path": "bd",
      "fake": true
    }
  }
}
""",
        encoding="utf-8",
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status="blocked",
        title="A checkpoint-failed run's tree is published to a preservation ref",
        description="The tree nothing else carries.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason="needs-human",
    )


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list[dict[str, object]])

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)

    def row(self, *, stage: str) -> dict[str, object] | None:
        return next((row for row in self.records if row.get("stage") == stage), None)


@dataclass(kw_only=True)
class _Runner:
    """One runner for both the engine and the forge, keyed on the CALL.

    Keyed on the subcommand and the endpoint rather than on call order, which is
    what lets a case assert that a read did not happen AT ALL: a fixed reply list
    would make that absence look like an unconsumed element, and so would a
    reordered pair -- and a list would also have to be re-counted every time the
    publication gained or lost a forge call.
    """

    events: tuple[dict[str, object], ...] | None = ()
    forge_fails_at: str | None = None
    argvs: list[list[str]] = field(default_factory=list[list[str]])

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        if "events" in argv:
            if self.events is None:
                return CommandResult(exit_code=1, stdout="", stderr="the factory refused")
            return CommandResult(exit_code=0, stdout=json.dumps(list(self.events)), stderr="")
        return self._forge(argv=argv)

    def _forge(self, *, argv: list[str]) -> CommandResult:
        endpoint = next((word for word in argv if word.startswith("/repos/")), "")
        if self.forge_fails_at is not None and self.forge_fails_at in endpoint:
            return CommandResult(exit_code=1, stdout="", stderr="the forge refused")
        if endpoint.endswith("/git/refs"):
            return CommandResult(exit_code=0, stdout="{}", stderr="")
        return CommandResult(exit_code=0, stdout=f"{_FORGE_NAMES[endpoint]}\n", stderr="")

    def endpoints(self) -> list[str]:
        return [word for argv in self.argvs for word in argv if word.startswith("/repos/")]


@dataclass(kw_only=True)
class _Transport:
    """The run-files HTTP exchange, as the server answers it (or refuses).

    The changed files ride in the response BODY and not in `payload`:
    `fabro_http_request` re-parses the body and replaces whatever payload a
    transport returned, so a double that filled only `payload` would hand the
    reader an empty response while looking correct at this seam.
    """

    succeeded: bool = True
    urls: list[str] = field(default_factory=list[str])

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        _ = (method, headers, body, timeout_seconds)
        self.urls.append(url)
        if not self.succeeded:
            return FabroHttpResult(
                status=401,
                body="Authentication required",
                error=None,
                payload=None,
                succeeded=False,
            )
        return FabroHttpResult(
            status=200,
            body=json.dumps({"files": [{"path": "a.py", "content": "print(1)\n"}]}),
            error=None,
            payload=None,
            succeeded=True,
        )


def _args(*, server: str | None = _SERVER, factory: str = _FACTORY) -> argparse.Namespace:
    return argparse.Namespace(
        fabro_bin="/home/ubuntu/.fabro/bin/fabro",
        fabro_factory_target=FactoryTarget(name=factory, server=server, dev_token=None),
    )


def _outcome(*, status: str = "blocked", run_id: str | None = _RUN) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM,
        status=status,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=f"the run ended: {_CHECKPOINT_FAILED}",
        fabro_run_id=run_id,
        fabro_failure_cause=_CHECKPOINT_FAILED,
    )


def _preserved(
    *,
    tmp_path: Path,
    runner: _Runner | None = None,
    transport: _Transport | None = None,
    outcome: DispatchOutcome | None = None,
    args: argparse.Namespace | None = None,
    journal_records: tuple[dict[str, object], ...] = (
        {"stage": SOURCE_STAGE, "work_item_id": _ITEM, "staged_at": _BASE},
    ),
) -> tuple[_Journal, _Runner, _Transport, list[str]]:
    _write_config(tmp_path)
    append_work_item(path=_config(), item=_item())
    journal = _Journal()
    used_runner = runner if runner is not None else _Runner()
    used_transport = transport if transport is not None else _Transport()
    preserve_checkpoint_failed_tree(
        args=args if args is not None else _args(),
        repo=tmp_path,
        item=_item(),
        outcome=outcome if outcome is not None else _outcome(),
        journal=journal,
        inputs=PreservationInputs(
            journal_records=journal_records,
            runner=used_runner,
            transport=used_transport,
        ),
    )
    bodies = [
        comment.text
        for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM)
        if comment.text.startswith(PRESERVED_TREE_MARKER)
    ]
    return journal, used_runner, used_transport, bodies


def test_a_checkpoint_failed_run_s_tree_is_published_and_named_on_the_item(
    tmp_path: Path,
) -> None:
    journal, runner, transport, bodies = _preserved(tmp_path=tmp_path)
    # The files came off the SERVER-API route of the dispatch's own factory, not
    # a default host: a port built elsewhere would publish another run's tree
    # under this item's preservation ref.
    assert transport.urls == [f"{_SERVER}/api/v1/runs/{_RUN}/files"]
    # Every forge write is a `gh api` Git Data call, so no `git push` ran and no
    # repository hook fired for this publication.
    forge = [argv for argv in runner.argvs if argv[0] != "/home/ubuntu/.fabro/bin/fabro"]
    assert forge, "the publication made no forge call"
    assert all(argv[0] == "gh" for argv in forge), forge
    assert not any("push" in argv for argv in runner.argvs)
    row = journal.row(stage=PRESERVED_TREE_STAGE)
    assert row is not None
    assert row["base_commit"] == _BASE
    assert row["preservation_ref"] == f"refs/livespec/preserved-publish/{_ITEM}/{_COMMIT}"
    assert len(bodies) == 1
    for named in (_RUN, _FACTORY, _COMMIT, _BASE):
        assert named in bodies[0], named


def test_a_run_whose_events_cannot_be_read_is_still_published(tmp_path: Path) -> None:
    journal, _, transport, bodies = _preserved(tmp_path=tmp_path, runner=_Runner(events=None))
    assert transport.urls, "the publication was not attempted"
    assert journal.row(stage=PRESERVED_TREE_STAGE) is not None
    assert len(bodies) == 1


def test_a_run_whose_terminal_event_carries_a_patch_is_not_published(tmp_path: Path) -> None:
    journal, runner, transport, bodies = _preserved(
        tmp_path=tmp_path,
        runner=_Runner(events=({"type": "run.failed", "terminal_patch": "diff --git a/x b/x\n"},)),
    )
    assert transport.urls == []
    assert runner.endpoints() == []
    row = journal.row(stage=PRESERVED_TREE_SKIPPED_STAGE)
    assert row is not None
    assert row["terminal_patch_bytes"] == len("diff --git a/x b/x\n")
    assert bodies == []


def test_a_refused_run_files_read_is_recorded_as_the_files_read_step(tmp_path: Path) -> None:
    journal, _, _, bodies = _preserved(tmp_path=tmp_path, transport=_Transport(succeeded=False))
    row = journal.row(stage=PRESERVED_TREE_UNPRESERVED_STAGE)
    assert row is not None
    assert row["failed_step"] == "files-read"
    assert len(bodies) == 1
    assert "NOT preserved" in bodies[0]
    # The server's own words reach the journal and never the append-only comment.
    assert "Authentication required" in str(row["detail"])
    assert "Authentication required" not in bodies[0]


def test_a_refused_forge_write_is_recorded_as_the_publication_step_that_failed(
    tmp_path: Path,
) -> None:
    # The sibling of the case above, and the half that reaches the PUBLICATION:
    # the clause names five steps a preservation can fail at, and a read that
    # succeeded leaves the four forge ones. A blob refusal is the earliest of
    # them, so it also proves the failure is attributed to the step that
    # actually refused rather than to the last step attempted.
    journal, _, transport, bodies = _preserved(
        tmp_path=tmp_path, runner=_Runner(forge_fails_at="/git/blobs")
    )
    assert transport.urls, "the run's changed files were never read"
    row = journal.row(stage=PRESERVED_TREE_UNPRESERVED_STAGE)
    assert row is not None
    assert row["failed_step"] == "blob"
    assert row["preservation_ref"] is None
    assert len(bodies) == 1
    assert "NOT preserved" in bodies[0]
    # The step's own words reach the journal and never the append-only comment,
    # which carries names and figures only and cannot be repaired once appended.
    assert "blob" in str(row["detail"])
    assert str(row["detail"]) not in bodies[0]


def test_a_green_outcome_reads_no_factory_and_writes_nothing(tmp_path: Path) -> None:
    journal, runner, transport, bodies = _preserved(
        tmp_path=tmp_path, outcome=_outcome(status="green")
    )
    assert runner.argvs == []
    assert transport.urls == []
    assert journal.records == []
    assert bodies == []


def test_a_terminal_naming_no_run_or_no_server_is_journaled_as_unreachable(
    tmp_path: Path,
) -> None:
    for args, outcome in (
        (_args(server=None), _outcome()),
        (_args(), _outcome(run_id=None)),
    ):
        journal, runner, transport, bodies = _preserved(
            tmp_path=tmp_path, args=args, outcome=outcome
        )
        assert runner.argvs == []
        assert transport.urls == []
        row = journal.row(stage=PRESERVED_TREE_UNREACHABLE_STAGE)
        assert row is not None, (args, outcome)
        assert bodies == []


def test_a_refused_ledger_write_is_journaled_and_never_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The run has already ended and the item rests at blocked / needs-human
    # either way, so a tenant that declines the append must cost a journal row
    # and not convert an ended run into a dispatch failure after the fact.
    def _refuse(*, path: StoreConfig, work_item_id: str, body: str) -> None:
        _ = (path, work_item_id, body)
        message = "the tenant declined the append"
        raise BeadsConnectionError(detail=message)

    monkeypatch.setattr(escalation, "append_work_item_comment", _refuse)
    journal, _, _, bodies = _preserved(tmp_path=tmp_path)
    # The publication's own row still stands: it is the only record that the
    # ref exists, and it is written BEFORE the comment for that reason.
    assert journal.row(stage=PRESERVED_TREE_STAGE) is not None
    error = journal.row(stage=PRESERVED_TREE_RECORD_STAGE)
    assert error is not None
    assert error["reason"] == "BeadsConnectionError"
    assert bodies == []


def test_a_body_the_detector_refuses_is_withheld_and_journaled(tmp_path: Path) -> None:
    # A factory name is committed configuration and reaches the body verbatim,
    # so it is the one input that can carry an opener into a comment nobody can
    # repair. The publication still happened and its row still stands.
    opener = "{" + "{ item.id }" + "}"
    journal, _, transport, bodies = _preserved(tmp_path=tmp_path, args=_args(factory=f"hp{opener}"))
    assert transport.urls, "the publication was not attempted"
    assert journal.row(stage=PRESERVED_TREE_STAGE) is not None
    withheld = journal.row(stage=PRESERVED_TREE_RECORD_STAGE)
    assert withheld is not None
    assert "opener" in str(withheld["reason"])
    assert bodies == []
