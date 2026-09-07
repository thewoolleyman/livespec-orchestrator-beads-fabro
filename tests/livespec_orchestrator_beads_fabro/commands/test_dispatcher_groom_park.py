"""The park: a groom run's draft, recorded on the ledger when it needs a human.

`SPECIFICATION/contracts.md` section "Grooming and slice-size calibration" ->
"Consensus-gated automated groom cut" requires that when the Dispatcher
journals a groom-pinned run's needs-human termination it records the draft on
the item as a ledger comment, beside the preserve-by-reference pointer.

WHAT IS MEASURED, AND WHY IT IS THE ITEM'S COMMENTS. The draft's whole purpose
is to outlive the run that wrote it — the run is dead and reapable by the time
a human reads it — so the only assertion that means anything is a read-back
through the item's ledger comments. Every case here drives a real needs-human
termination through `record_groom_draft` and then reads the comments, never the
return value, which is `None` in every case by design.

THE THREE SKIPS ARE ASSERTED AS SEPARATE CAUSES, because they are the three
ways an operator can be left without a draft and each needs a different
response: no run to inspect, a run whose record carries no draft, and a draft
that would poison the item if written. The last is the one worth the most:
a ledger comment is append-only, so writing a draft carrying a MiniJinja
opening delimiter would kill every future dispatch of that item before a run
exists. The case asserts NOTHING was written and that the openers are named.

AND ONE CASE ASSERTS THE NON-GROOM PATH IS SILENT rather than skipped. Every
implement run that reaches a human gate passes through this seam, so a skip row
per human-gated run would bury the three skips that name something actionable.
"""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import record_dispatch_workflow
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_item_comments
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_groom_park"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_groom_park.py"
)

_ITEM_ID = "bd-ib-groom-park"
_RUN_ID = "01M1PARKRUN"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_GROOM_VARIANT = "groom-cut"
_GROOM_DIR = ".fabro/workflows/groom-cut"
_IMPLEMENT_VARIANT = "codex-first"
_IMPLEMENT_DIR = ".fabro/workflows/codex-first"
# ONE LINE, deliberately. The sentinel below is a stderr LINE, so the account
# a terminated run publishes is single-line by construction — a fact of the
# channel, not of this test. How a groom variant encodes a layered draft into
# one value belongs to the variant; what is asserted here is that whatever it
# published reaches the ledger verbatim.
_DRAFT = "Layer 1: slice A (acceptance: it lands). Layer 2: slice B depends on A."
# The workflow's own needs-human sentinel, which is the channel the propose
# phase publishes its draft on. Kept as a literal rather than imported so a
# rename of the marker fails this test loudly instead of silently agreeing.
_SENTINEL_LINE = f"LIVESPEC_NEEDS_HUMAN: {_DRAFT}"
# The tail of the groom terminal's own script, which is what reached the ledger
# in place of the draft on 2026-09-07 (run 01M1X6JBV2M1CCQCCEVNTJ2YXE).
_SCRIPT_FRAGMENT = '$(head -n 1 /tmp/livespec-groom-draft)" >&2; else echo'
_TERMINAL_SCRIPT = (
    f'if test -s /tmp/livespec-groom-draft; then echo "LIVESPEC_NEEDS_HUMAN: '
    f"{_SCRIPT_FRAGMENT} 'LIVESPEC_NEEDS_HUMAN: the groom run could not "
    "auto-resolve this work-item and produced no draft' >&2; fi; exit 1"
)


def _park_module() -> Any:
    """Import the groom-park module, proving the file exists first."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(frozen=True, kw_only=True)
class _Command:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(kw_only=True)
class _Runner:
    """A fake `fabro` CLI returning one canned `inspect` payload."""

    payload: str
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> _Command:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return _Command(exit_code=0, stdout=self.payload, stderr="")


@dataclass(frozen=True, kw_only=True)
class _Factory:
    server: str | None


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _manifest(*, kind: str) -> str:
    return f'[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "{kind}"\n'


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for directory, kind in ((_GROOM_DIR, "groom"), (_IMPLEMENT_DIR, "implement")):
        target = repo / directory
        target.mkdir(parents=True)
        _ = (target / "workflow.toml").write_text(_manifest(kind=kind), encoding="utf-8")
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "livespec-impl-beads",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "workflows": {
                            _GROOM_VARIANT: _GROOM_DIR,
                            _IMPLEMENT_VARIANT: _IMPLEMENT_DIR,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _filed(*, pin: str | None) -> WorkItem:
    reset_fake_singleton()
    item = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="An epic under a groom dispatch",
        description="It carries more than one coherent done.",
        origin="freeform",
        gap_id=None,
        rank="m",
        assignee="dispatcher",
        depends_on=(),
        captured_at="2026-09-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    append_work_item(path=_config(), item=item)
    if pin is not None:
        record_dispatch_workflow(path=_config(), work_item_id=_ITEM_ID, workflow=pin)
    return item


def _args(*, server: str | None = _SERVER) -> argparse.Namespace:
    return argparse.Namespace(fabro_bin="fabro", fabro_factory_target=_Factory(server=server))


def _outcome(*, status: str = "blocked", run_id: str | None = _RUN_ID) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status=status,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="the run routed the decision to a human",
        fabro_run_id=run_id,
    )


def _inspect_payload(*, line: str) -> str:
    return json.dumps({"run": {"id": _RUN_ID, "stderr": line}})


def _inspect_payload_with_script(*, line: str) -> str:
    """A record carrying the terminal's SCRIPT SOURCE ahead of its output.

    `notes` is the measured carrier: a fabro stage status note reads `Script
    completed: <the whole script>`, and that script necessarily contains the
    sentinel because it is what echoes it.
    """
    return json.dumps(
        {
            "run": {
                "id": _RUN_ID,
                "notes": f"Script completed: {_TERMINAL_SCRIPT}",
                "stderr": line,
            }
        }
    )


def _comments() -> tuple[str, ...]:
    return tuple(
        comment.text for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
    )


def test_a_groom_pinned_needs_human_termination_records_the_draft_as_a_comment(
    tmp_path: Path,
) -> None:
    """The draft is read back off the ITEM, which is where it has to outlive the run."""
    module = _park_module()
    repo = _repo(tmp_path=tmp_path)
    _ = _filed(pin=_GROOM_VARIANT)
    journal = _RecordingJournal()

    module.record_groom_draft(
        args=_args(),
        repo=repo,
        item=_filed(pin=_GROOM_VARIANT),
        outcome=_outcome(),
        journal=journal,
        runner=_Runner(payload=_inspect_payload(line=_SENTINEL_LINE)),
    )

    bodies = _comments()
    assert len(bodies) == 1
    assert _DRAFT in bodies[0]
    assert _GROOM_VARIANT in bodies[0].split("\n", 1)[0]
    assert [row["stage"] for row in journal.records] == [module.GROOM_DRAFT_RECORDED_STAGE]
    assert journal.records[0]["workflow_name"] == _GROOM_VARIANT


def test_the_recorded_comment_carries_the_draft_not_the_script_that_echoed_it(
    tmp_path: Path,
) -> None:
    """The end-to-end shape of the substitution measured on 2026-09-07.

    The terminal node's script CONTAINS the sentinel — it is the script that
    echoes it — and a stage record carries that script beside the run's output.
    What has to reach the item is the decomposition, so both halves are
    asserted: the draft is present, and the shell that published it is not.
    """
    module = _park_module()
    repo = _repo(tmp_path=tmp_path)
    journal = _RecordingJournal()

    module.record_groom_draft(
        args=_args(),
        repo=repo,
        item=_filed(pin=_GROOM_VARIANT),
        outcome=_outcome(),
        journal=journal,
        runner=_Runner(payload=_inspect_payload_with_script(line=_SENTINEL_LINE)),
    )

    bodies = _comments()
    assert len(bodies) == 1
    assert _DRAFT in bodies[0]
    assert _SCRIPT_FRAGMENT not in bodies[0]
    assert [row["stage"] for row in journal.records] == [module.GROOM_DRAFT_RECORDED_STAGE]


def test_an_implement_pinned_termination_records_nothing_and_journals_nothing(
    tmp_path: Path,
) -> None:
    """Every human-gated implement run passes here; none of them is a groom park."""
    module = _park_module()
    repo = _repo(tmp_path=tmp_path)
    journal = _RecordingJournal()

    module.record_groom_draft(
        args=_args(),
        repo=repo,
        item=_filed(pin=_IMPLEMENT_VARIANT),
        outcome=_outcome(),
        journal=journal,
        runner=_Runner(payload=_inspect_payload(line=_SENTINEL_LINE)),
    )

    assert _comments() == ()
    assert journal.records == []


def test_an_unpinned_termination_records_nothing_and_journals_nothing(
    tmp_path: Path,
) -> None:
    module = _park_module()
    repo = _repo(tmp_path=tmp_path)
    journal = _RecordingJournal()

    module.record_groom_draft(
        args=_args(),
        repo=repo,
        item=_filed(pin=None),
        outcome=_outcome(),
        journal=journal,
        runner=_Runner(payload=_inspect_payload(line=_SENTINEL_LINE)),
    )

    assert _comments() == ()
    assert journal.records == []


def test_a_green_outcome_is_not_a_park(tmp_path: Path) -> None:
    """The park is keyed on the needs-human terminal, not on the pin alone."""
    module = _park_module()
    repo = _repo(tmp_path=tmp_path)
    journal = _RecordingJournal()

    module.record_groom_draft(
        args=_args(),
        repo=repo,
        item=_filed(pin=_GROOM_VARIANT),
        outcome=_outcome(status="green"),
        journal=journal,
        runner=_Runner(payload=_inspect_payload(line=_SENTINEL_LINE)),
    )

    assert _comments() == ()
    assert journal.records == []


def test_a_termination_with_no_run_to_inspect_is_skipped_under_its_own_cause(
    tmp_path: Path,
) -> None:
    module = _park_module()
    repo = _repo(tmp_path=tmp_path)
    journal = _RecordingJournal()

    module.record_groom_draft(
        args=_args(),
        repo=repo,
        item=_filed(pin=_GROOM_VARIANT),
        outcome=_outcome(run_id=None),
        journal=journal,
        runner=_Runner(payload="{}"),
    )

    assert _comments() == ()
    assert journal.records[0]["stage"] == module.GROOM_DRAFT_SKIPPED_STAGE
    assert journal.records[0]["reason"] == "missing-run-or-server"


def test_a_termination_with_no_factory_server_is_skipped_under_the_same_cause(
    tmp_path: Path,
) -> None:
    module = _park_module()
    repo = _repo(tmp_path=tmp_path)
    journal = _RecordingJournal()

    module.record_groom_draft(
        args=_args(server=None),
        repo=repo,
        item=_filed(pin=_GROOM_VARIANT),
        outcome=_outcome(),
        journal=journal,
        runner=_Runner(payload="{}"),
    )

    assert _comments() == ()
    assert journal.records[0]["reason"] == "missing-run-or-server"


def test_a_run_record_carrying_no_draft_is_skipped_under_its_own_cause(
    tmp_path: Path,
) -> None:
    """A record with no needs-human account is a different fault from no run."""
    module = _park_module()
    repo = _repo(tmp_path=tmp_path)
    journal = _RecordingJournal()

    module.record_groom_draft(
        args=_args(),
        repo=repo,
        item=_filed(pin=_GROOM_VARIANT),
        outcome=_outcome(),
        journal=journal,
        runner=_Runner(payload=_inspect_payload(line="nothing to see here")),
    )

    assert _comments() == ()
    assert journal.records[0]["reason"] == "no-draft-in-run-record"


def test_a_draft_carrying_a_template_opener_is_refused_with_nothing_written(
    tmp_path: Path,
) -> None:
    """Writing it would kill every future dispatch of this item, permanently.

    A ledger comment cannot be edited or deleted, so the openers are named in
    the skip and the draft is left in the preserved run rather than escaped
    into something the propose phase did not write.
    """
    module = _park_module()
    repo = _repo(tmp_path=tmp_path)
    journal = _RecordingJournal()
    poisoned = "LIVESPEC_NEEDS_HUMAN: Layer 1: slice " + chr(123) + chr(123) + " item.id }}"

    module.record_groom_draft(
        args=_args(),
        repo=repo,
        item=_filed(pin=_GROOM_VARIANT),
        outcome=_outcome(),
        journal=journal,
        runner=_Runner(payload=_inspect_payload(line=poisoned)),
    )

    assert _comments() == ()
    assert journal.records[0]["reason"] == "draft-would-poison-goal"
    assert chr(123) + chr(123) in str(journal.records[0]["detail"])


def test_an_inspect_that_cannot_run_is_skipped_rather_than_raised(
    tmp_path: Path,
) -> None:
    """The default shell runner is exercised here, against a binary that is absent.

    The park runs after the outcome is journaled and before the escalation that
    rests the item at `blocked / needs-human`, so a factory it cannot reach must
    not become an exception on the dispatch path.
    """
    module = _park_module()
    repo = _repo(tmp_path=tmp_path)
    journal = _RecordingJournal()
    args = argparse.Namespace(
        fabro_bin=str(tmp_path / "no-such-fabro"),
        fabro_factory_target=_Factory(server=_SERVER),
    )

    module.record_groom_draft(
        args=args,
        repo=repo,
        item=_filed(pin=_GROOM_VARIANT),
        outcome=_outcome(),
        journal=journal,
    )

    assert _comments() == ()
    assert journal.records[0]["reason"] == "no-draft-in-run-record"


def test_a_ledger_that_cannot_be_reached_is_journaled_rather_than_raised(
    tmp_path: Path,
) -> None:
    """The escalation after this seam still has to run, so nothing escapes it."""
    from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError

    module = _park_module()
    repo = _repo(tmp_path=tmp_path)
    journal = _RecordingJournal()
    item = _filed(pin=_GROOM_VARIANT)

    def _raise(*, path: StoreConfig, work_item_id: str) -> str | None:
        _ = (path, work_item_id)
        raise BeadsConnectionError(detail="tenant unreachable")

    module.dispatch_workflow_for = _raise
    try:
        module.record_groom_draft(
            args=_args(),
            repo=repo,
            item=item,
            outcome=_outcome(),
            journal=journal,
            runner=_Runner(payload="{}"),
        )
    finally:
        importlib.reload(module)

    assert journal.records[0]["stage"] == "groom-draft-skipped"
    assert journal.records[0]["reason"] == "BeadsConnectionError"
