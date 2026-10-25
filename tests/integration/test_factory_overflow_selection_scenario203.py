"""Scenarios 53 and 203 — factory placement never turns host load into a refusal.

Binds `SPECIFICATION/scenarios.md` Scenarios 53 and 203 and the
factory-overflow-selection clause of `SPECIFICATION/contracts.md`. Every case
starts from a `.livespec.jsonc` ON DISK and drives the production configuration
read, the capacity read, the selection, the ledger stamp and the launch argv; the
only things stood in are the `fabro` CLI (a recording runner, so each factory's
run board and scheduler ceiling are scripted without a server and every argv is
observable) and the ledger, through this repository's own hermetic
`FakeBeadsClient`.

WHY SCENARIO 53 DRIVES THE WHOLE `loop` INVOCATION rather than the three layers
its claim passes through. "A dispatch proceeds when the host is busy" is a claim
about the ADMISSION-TO-LAUNCH PATH, and that path is a sequence: the preamble,
the pre-dispatch wall, recovery routing, the admission valve, the publish-branch
reclaim and then `dispatch_one`. Calling `admit_and_select`,
`args_with_dispatch_factory_target` and `FabroPort.run` in turn reproduces the
ANSWER each layer gives while skipping every layer that could refuse between
them — so a host-capacity gate anywhere in that sequence, or a wave that admitted
the row and never reached the launch, leaves such a case green. The cases below
therefore run the real `dispatcher.main(argv=["loop", "--item", ...])` CLI, which
is also the only entry point that ENFORCES the per-repo WIP cap the scenario's
free-slot premise is about: `dispatch --item` is an operator override and passes
`enforce_cap=False`. Only `run_dispatch` is stood in, at the launch seam, by a
recorder that assembles the production `fabro run` argv from the plan the real
path built — so the submission is observed rather than inferred, and the
Dispatcher's own exit code is observable too.

WHY THE ADMITTED STATUS IS READ AT THE LAUNCH and not afterwards. The claim is
that the row is `active` when its run is submitted, and the post-run
dispositions legitimately move an `ai-only` item on from there — so a status read
after the invocation returns reports the DISPOSITION rather than the admission,
and would pass for a dispatch that claimed the row only once the run had already
ended.

WHY THE CHOSEN FACTORY IS ASSERTED AT THE ARGV AND AT THE LEDGER, not at the
selection. A selection that answers `petri` proves the ranking; it does not prove
the dispatch LANDS there. The name crosses three hand-offs afterwards — the
resolved dispatch target, the item's own dispatch-factory record, and the
`fabro run --server` argv — and the clause requires the record specifically, "so
that a later resume, reconcile or acceptance pass of the same dispatch follows
it". A name dropped at any of those hand-offs does not fail: the dispatch
proceeds to the DEFAULT factory, which is a perfectly ordinary outcome with
nothing in the record to say the ranking was ignored.

WHY THE PINNED CASE COUNTS SERVER READS RATHER THAN CHECKING THE ANSWER. "without
reading either server's run count or `max_concurrent_runs`" is a claim about
reads that did NOT happen, and a pinned dispatch resolves to its own factory
whether or not the capacity reads were spent — so an implementation that read
both servers and then discarded the answer satisfies every other assertion while
putting two round trips on the critical path of every pinned dispatch and every
resume. The argv list is therefore asserted EMPTY, with the unpinned cases as the
positive control that the same runner does get reached.

WHY THE NO-FREE-SLOT CASE ASSERTS AN ARGV AS WELL AS A JOURNAL REASON. "the
dispatch is neither refused nor deferred" is also a negative, and the saturated
reading is exactly the input a capacity-aware implementation is tempted to hold
on. A refusal would leave no argv at all, so the launch argv is what separates
"placed on the default and queued there" from "declined".

WHY THE REFUSAL CASE SNAPSHOTS THE LEDGER. "refused before any item is claimed"
is two claims, and a refusal string proves only the first. The preamble is the
whole of what runs ahead of admission, so the item is snapshotted before it and
compared after: a refusal that fired AFTER stamping would satisfy a message-only
assertion while leaving the row claimed under a dispatch that never placed work.
"""

from __future__ import annotations

import argparse
import importlib
import json
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import claim_row_for
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_stamp import (
    stamp_pending_claim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_ledger import (
    args_with_dispatch_factory_target,
    dispatch_factory_targets,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import (
    DispatchPlan,
    build_plan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import fabro_port_for_plan
from livespec_orchestrator_beads_fabro.commands.dispatcher import dispatch_preamble, main
from livespec_orchestrator_beads_fabro.store import record_dispatch_factory
from livespec_orchestrator_beads_fabro.types import StoreConfig

_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_CAPACITY_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_factory_capacity"
_SELECTION_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_overflow_selection"
_CAPACITY_FILE = "_dispatcher_factory_capacity.py"
_SELECTION_FILE = "_dispatcher_overflow_selection.py"

_DEFAULT_FACTORY = "hp"
_OVERFLOW_FACTORY = "petri"
_DEFAULT_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_OVERFLOW_SERVER = "https://gmktec.perch-rudd.ts.net:32276"
# A RESERVED-domain sentinel for the registry-backed case, so no provisioning
# inventory on any host can render this address and make the case non-hermetic.
_REGISTRY_SERVER = "https://registry-overflow.example:32276"
_REGISTRY_PATH_ENV_VAR = "LIVESPEC_FABRO_FACTORY_REGISTRY"
_FACTORY_SELECTION_ENV_VAR = "LIVESPEC_FABRO_FACTORY"

# The two ceilings measured on 2026-10-19 — hp reports 10 and petri reports 2 —
# which is the asymmetry the clause's least-utilized rule exists for: a
# first-free-slot rule would almost never select the smaller factory.
_DEFAULT_CEILING = 10
_OVERFLOW_CEILING = 2

_TENANT = "livespec-orch-beads-fabro"
_PREFIX = "bd-ib"
_WORK_ITEM_ID = "bd-ib-pzdwej"
_RUN_ID = "01M5AEWJ4VYZKYGQGQSTT9QGTD"
_DISPATCH_ID = "01M5AEWJ4VYZKYGQGQSTT9QGTE"
_EXIT_PRECONDITION_ERROR = 3

# A wave of UNPINNED items, five of them, which is what makes a ranking taken
# once per item distinguishable from one taken once per invocation: at four
# capacity reads per ranking the two differ by sixteen engine round trips.
_WAVE_ITEM_IDS = (
    "bd-ib-wave001",
    "bd-ib-wave002",
    "bd-ib-wave003",
    "bd-ib-wave004",
    "bd-ib-wave005",
)

_SELECTION_STAGE = "overflow-factory-selection"
_REASON_LEAST_UTILIZED = "least-utilized-free-slot"
_REASON_NO_CANDIDATE = "no-candidate-free-default"

# The committed workflow the Scenario 53 legs' dispatch target carries, so the
# preflight resolves THIS tree's graph rather than the plugin's bundled one.
_WORKFLOW_DIR = ".fabro/workflows/implement-work-item"
_WORKFLOW_TOML = '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "fabro-sandbox"\n'
_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)
_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
)

# The Fabro currency gate's hermetic answer — see `_CurrencyRunner`.
_CURRENCY_GATE_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency_gate"
_CURRENCY_SOURCES_MODULE = (
    "livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency_sources"
)
_CURRENCY_NOW = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
_CURRENCY_TAG = "v0.260.0"
_SERVING_COMMIT = "8869e88"


@pytest.fixture(autouse=True)
def _hermetic_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """A fresh in-memory tenant, and neither routing variable inherited.

    Both deletions are load-bearing rather than hygiene.
    `LIVESPEC_FABRO_FACTORY` PINS a dispatch, so a value leaking in from the
    dispatch that runs this suite would make every unpinned case here a pinned
    one — and the pinned case asserts that no capacity read happens, so the
    unpinned cases would fail for a reason that has nothing to do with
    selection. The registry path variable is the subject of one case and must
    not be inherited by the others.

    The remaining entries are what a whole `loop` invocation needs to be
    hermetic: a scratch temporary root, the worker credential the credential
    projection reads, the forge token supplier, the fleet manifest the sibling
    clone projection fetches, and no notification topic. They cost the layer
    cases nothing, which is why one fixture serves both halves of the module.
    """
    scratch = tmp_path_factory.mktemp("factory-overflow-scenario203")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:factory-overflow-scenario203")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    for topic in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(topic, raising=False)
    monkeypatch.delenv(_FACTORY_SELECTION_ENV_VAR, raising=False)
    monkeypatch.delenv(_REGISTRY_PATH_ENV_VAR, raising=False)
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Board:
    """One factory's scripted run board and scheduler ceiling.

    `runs` is a COUNT rather than a row list because the clause's input is the
    non-terminal run count; the rows are synthesized from it. `ceiling` of
    `None` scripts a `settings` read that answers nothing, and `unreadable`
    scripts a non-zero exit on BOTH reads — the clause treats a failed read and
    an unparseable one identically, and the two are the only ways a candidate
    goes unmeasured.
    """

    runs: int
    ceiling: int | None
    unreadable: bool = False


@dataclass(kw_only=True)
class _Runner:
    """The `fabro` CLI, scripted per factory server and recording every argv."""

    boards: dict[str, _Board]
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
        del cwd, timeout_seconds, env, stdin
        self.argvs.append(argv)
        board = self.boards.get(_server_of(argv=argv))
        if board is None or board.unreadable:
            return CommandResult(exit_code=1, stdout="", stderr="unreadable")
        if "ps" in argv:
            return CommandResult(exit_code=0, stdout=_ps_json(board=board), stderr="")
        if "settings" in argv:
            return CommandResult(exit_code=0, stdout=_settings_json(board=board), stderr="")
        return CommandResult(exit_code=0, stdout=f"Run: {_RUN_ID}\n", stderr="")

    def capacity_argvs(self) -> list[list[str]]:
        """Only the reads the clause names: the run board and the ceiling."""
        return [argv for argv in self.argvs if "ps" in argv or "settings" in argv]


def _server_of(*, argv: list[str]) -> str:
    return argv[argv.index("--server") + 1] if "--server" in argv else ""


def _ps_json(*, board: _Board) -> str:
    """A listing of `board.runs` non-terminal rows, plus one terminal row.

    The terminal row is the discriminator the clause needs and a count alone
    cannot carry: `max_concurrent_runs` bounds NON-TERMINAL runs, so an
    implementation counting every row the factory holds would report a
    long-lived factory as permanently saturated. hp listed 1626 rows on
    2026-10-12, nearly all of them terminal.
    """
    rows: list[dict[str, Any]] = [
        {"run_id": f"01MOVERFLOWLIVE{index:010d}", "status": {"kind": "running"}}
        for index in range(board.runs)
    ]
    rows.append({"run_id": "01MOVERFLOWDONE0000000000", "status": {"kind": "succeeded"}})
    return json.dumps(rows)


def _settings_json(*, board: _Board) -> str:
    if board.ceiling is None:
        return json.dumps({"server": {"listen": "127.0.0.1:32276"}})
    return json.dumps({"server": {"scheduler": {"max_concurrent_runs": board.ceiling}}})


def _capacity_module() -> Any:
    """The capacity-reading module, imported inside the test body.

    The file is asserted FIRST so the Red is a genuine assertion failure rather
    than a collection error: at Red neither module exists, and a top-level
    import of either would die before any assertion ran.
    """
    assert (_COMMANDS_DIR / _CAPACITY_FILE).is_file()
    return importlib.import_module(_CAPACITY_MODULE)


def _selection_module() -> Any:
    """The selection module, imported inside the test body."""
    assert (_COMMANDS_DIR / _SELECTION_FILE).is_file()
    return importlib.import_module(_SELECTION_MODULE)


def _install_runner(*, monkeypatch: pytest.MonkeyPatch, runner: _Runner) -> None:
    """Stand the `fabro` CLI in, and nothing else.

    The real `FactoryRunReader` and the real `FabroPort` stay in the path — the
    reader is rebuilt carrying this runner — so the configuration read, the
    registry resolution, the argv assembly and both payload parses are
    production code.
    """
    capacity = _capacity_module()
    real_reader = capacity.FactoryRunReader

    def _reader(*, repo: Path) -> Any:
        return real_reader(repo=repo, runner=runner)

    monkeypatch.setattr(capacity, "FactoryRunReader", _reader)
    # Every module that constructs its OWN reader, so no leg of a whole `loop`
    # invocation reaches a server: the admission valve's availability evidence,
    # and the wave's admission-time ACP preflight.
    for name in (
        "livespec_orchestrator_beads_fabro.commands._dispatcher_admission",
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop_wave",
    ):
        monkeypatch.setattr(importlib.import_module(name), "FactoryRunReader", _reader)


def _store() -> StoreConfig:
    return StoreConfig(
        tenant=_TENANT,
        prefix=_PREFIX,
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_store())
    assert isinstance(client, FakeBeadsClient)
    return client


def _seed_item(*, work_item_id: str = _WORK_ITEM_ID) -> None:
    """One item, filed through the store seam, carrying ONE gradeable assertion.

    The criterion is a `- ` bullet ending in a period because the pre-dispatch
    criteria wall refuses an AI-dispositive item that parses to zero gradeable
    assertions, and `criteria_lines` segments by CONTENT — a flush-left line
    with no list marker continues the previous block rather than starting an
    assertion of its own.
    """
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id=work_item_id,
            issue_type="feature",
            title="Overflow an unpinned dispatch to the least-utilized factory",
            description=(
                "## Definition of Done\n"
                "\n"
                "- The dispatch lands on the free slot.\n"
                "\n"
                "References: ## Effective acceptance criteria\n"
            ),
            assignee=None,
            created_at="2026-10-19T00:00:00Z",
            acceptance_criteria="- The Dispatcher submits this item to Fabro.\n",
        )
    )


def _item_state() -> dict[str, Any]:
    """The item's status, assignee, metadata and comments, as one snapshot."""
    record = _fake().show_issue(issue_id=_WORK_ITEM_ID)
    return {
        "status": record.get("status"),
        "assignee": record.get("assignee"),
        "metadata": json.dumps(record.get("metadata"), sort_keys=True, default=repr),
        "comments": [comment.text for comment in _fake().list_comments(issue_id=_WORK_ITEM_ID)],
    }


def _recorded_factory() -> object:
    metadata = _fake().show_issue(issue_id=_WORK_ITEM_ID).get("metadata")
    assert isinstance(metadata, dict)
    return metadata.get("dispatch_factory")


def _write_config(
    *,
    cwd: Path,
    overflow: object = (_OVERFLOW_FACTORY,),
    overflow_entry: dict[str, Any] | None = None,
    wip_cap: int | None = None,
) -> None:
    dispatcher: dict[str, Any] = {
        "default_factory": _DEFAULT_FACTORY,
        "factories": {
            _DEFAULT_FACTORY: {"server": _DEFAULT_SERVER},
            _OVERFLOW_FACTORY: (
                {"server": _OVERFLOW_SERVER} if overflow_entry is None else overflow_entry
            ),
        },
        "overflow_factories": list(overflow) if isinstance(overflow, tuple) else overflow,
    }
    if wip_cap is not None:
        dispatcher["wip_cap"] = wip_cap
        dispatcher["acceptance_mode"] = "ai-only"
    _ = (cwd / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Chad Woolley",
                    "operator_email": "thewoolleyman@gmail.com",
                },
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"tenant": _TENANT, "prefix": _PREFIX, "fake": True},
                    "dispatcher": dispatcher,
                },
            }
        ),
        encoding="utf-8",
    )


def _write_target_workflow(*, cwd: Path) -> None:
    """The dispatch target's own committed reserved workflow."""
    workflow = cwd / _WORKFLOW_DIR
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")


def _dispatch_args(*, cwd: Path, factory: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        factory=factory,
        journal=str(cwd / "journal.jsonl"),
        fabro_bin="/opt/fabro",
    )


def _journal_records(*, cwd: Path) -> list[dict[str, Any]]:
    path = cwd / "journal.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _selection_records(*, cwd: Path) -> list[dict[str, Any]]:
    return [
        record
        for record in _journal_records(cwd=cwd)
        if record.get("stage") == _SELECTION_STAGE
        or record.get("record", {}).get("stage") == _SELECTION_STAGE
    ]


def _non_green_outcomes(*, cwd: Path) -> list[dict[str, Any]]:
    """Every terminal outcome this invocation journaled that is not green.

    ONE reading for both halves of "neither refused nor deferred": a
    host-capacity refusal and a capacity deferral are both non-green outcome
    records, and reading only one of them would leave the other invisible.
    """
    outcomes = [
        record.get("outcome")
        for record in _journal_records(cwd=cwd)
        if record.get("stage") == "outcome"
    ]
    return [one for one in outcomes if isinstance(one, dict) and one.get("status") != "green"]


def _make_ready() -> None:
    """Move the fixture to `ready` so the admission valve has a candidate."""
    _fake().update_issue(issue_id=_WORK_ITEM_ID, status="ready", metadata={"rank": "a0"})


@dataclass(kw_only=True)
class _CurrencyRunner:
    """The Fabro currency gate's own two reads, answered without leaving the process.

    The gate is FIRST in the pre-dispatch wall and refuses an unidentifiable or
    out-of-window engine, so a `loop` over a target that DECLARES factory servers
    cannot reach admission at all until it is answered. It is not Scenario 53's
    subject, so it is answered rather than removed: both declared factories serve
    a build whose base IS the newest published release, which is the one reading
    that admits on the ordinary rule with no transition and no cached
    observation. Keeping the real gate, the real cache read and the real verdict
    in the path is the point — a wall arm that could refuse between admission and
    the launch is exactly what these cases exist to rule out.
    """

    now: Any

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        sources = importlib.import_module(_CURRENCY_SOURCES_MODULE)
        if "version" in argv:
            return CommandResult(exit_code=0, stdout=_version_json(), stderr="")
        if argv == sources.releases_argv():
            return CommandResult(exit_code=0, stdout=_releases_payload(now=self.now), stderr="")
        # The ancestry comparison is the LAST read the gate takes, asserted
        # rather than matched with a non-zero fall-through beside it. An argv
        # this runner does not recognise must fail the case LOUDLY: answered
        # non-zero it would degrade the gate into an honest refusal, and a
        # refusal is indistinguishable at every assertion below from the
        # host-capacity refusal these cases exist to rule out.
        assert argv == sources.compare_argv(base=_CURRENCY_TAG, head=_SERVING_COMMIT)
        return CommandResult(exit_code=0, stdout="identical\n", stderr="")


def _version_json() -> str:
    """`fabro version --json`'s server section, as the engine prints it.

    The SERVER section is what the gate reads; the client section sits beside it
    and carries the same commit here, so neither reading can be mistaken for the
    other by accident.
    """
    return json.dumps(
        {
            "client": {"version": "0.260.0", "git_sha": _SERVING_COMMIT},
            "server": {"version": "0.260.0", "git_sha": _SERVING_COMMIT},
        }
    )


def _releases_payload(*, now: Any) -> str:
    """One published release, one compact object on its own line.

    One release rather than several because the base this build serves IS that
    release, so the in-window gap is zero and nothing about this fixture depends
    on the publication-order rule the currency scenario's own module grades.
    `--paginate --jq` emits a line per release rather than one array, which is
    why this is not a JSON document.
    """
    published = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return json.dumps({"tag": _CURRENCY_TAG, "published_at": published}) + "\n"


def _install_currency_runner(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in the gate's ONLY two things that leave the process: shell and clock."""
    gate = importlib.import_module(_CURRENCY_GATE_MODULE)
    monkeypatch.setattr(gate, "currency_instant", lambda: _CURRENCY_NOW)
    monkeypatch.setattr(gate, "ShellCommandRunner", lambda: _CurrencyRunner(now=_CURRENCY_NOW))


@dataclass(frozen=True, kw_only=True)
class _Launch:
    """One submission the real admission-to-launch path reached.

    `status` is the ledger row's status AT THE MOMENT the run is submitted,
    which is the instant the admission claim is about — see the module docstring
    for why it cannot be read after the invocation returns.
    """

    plan: DispatchPlan
    status: object


def _launching_run_dispatch(
    *, runner: _Runner, launched: list[_Launch]
) -> Callable[..., DispatchOutcome]:
    """The launch seam, replaced by a recorder that still assembles the argv.

    The plan it is handed is the one the real path built, so the `fabro run`
    argv the production port renders from it is this dispatch's own submission
    — observable without a server because the recording runner stands exactly
    where the `fabro` CLI would. Nothing upstream of this seam is stood in.
    """

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        launched.append(
            _Launch(plan=plan, status=_fake().show_issue(issue_id=plan.work_item_id)["status"])
        )
        _ = fabro_port_for_plan(plan=plan, runner=runner).run(
            workflow_toml=plan.workflow_toml,
            goal_file=plan.goal_file,
            inputs=(),
            timeout_seconds=42.0,
        )
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="dispatched",
        )

    return _run_dispatch


def _loop_dispatch(
    *,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    boards: dict[str, _Board],
) -> tuple[int, list[_Launch], _Runner]:
    """Drive one real `loop --item` invocation over this target.

    `loop` rather than `dispatch --item` because the per-repo WIP cap is
    enforced only on the drain; a targeted dispatch is an operator override and
    passes `enforce_cap=False`, so it could not exercise the scenario's
    free-slot premise at all.
    """
    _make_ready()
    runner = _Runner(boards=boards)
    _install_runner(monkeypatch=monkeypatch, runner=runner)
    _install_currency_runner(monkeypatch=monkeypatch)
    launched: list[_Launch] = []
    monkeypatch.setattr(
        _dispatcher_loop,
        "run_dispatch",
        _launching_run_dispatch(runner=runner, launched=launched),
    )
    argv = [
        "loop",
        "--repo",
        str(cwd),
        "--item",
        _WORK_ITEM_ID,
        "--budget",
        "1",
        "--journal",
        str(cwd / "journal.jsonl"),
        "--no-close-on-merge",
    ]
    return main(argv=argv), launched, runner


def _submitted_argv(*, runner: _Runner) -> list[str]:
    """The ONE `fabro run` argv this dispatch submitted."""
    submitted = [argv for argv in runner.argvs if argv[1] == "run"]
    assert len(submitted) == 1
    return submitted[0]


def _launch_argv(*, cwd: Path, runner: _Runner, args: argparse.Namespace) -> list[str]:
    """The `fabro run` argv this dispatch's resolved target actually produces."""
    target = args.fabro_factory_target
    plan = build_plan(
        repo=cwd,
        work_item_id=_WORK_ITEM_ID,
        workflow_toml=cwd / "workflow.toml",
        goal_file=cwd / "goal.md",
        fabro_bin=args.fabro_bin,
        fabro_factory_name=target.name,
        fabro_factory_server=target.server,
        janitor=None,
        janitor_checkout=cwd / "janitor",
    )
    _ = fabro_port_for_plan(plan=plan, runner=runner).run(
        workflow_toml=plan.workflow_toml,
        goal_file=plan.goal_file,
        inputs=(),
        timeout_seconds=42.0,
    )
    return _submitted_argv(runner=runner)


def _resolve(
    *,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    boards: dict[str, _Board],
    factory: str | None = None,
    resume: bool = False,
) -> tuple[argparse.Namespace, _Runner]:
    """Drive the production unpinned-dispatch resolution once.

    `resume` is the ROUTE recovery routing assigns, and the recorded pin is the
    one layer that depends on it: the clause makes the item's recorded factory a
    resume-only pin, so the recorded case below must drive a resume to be a
    pinned dispatch at all. Every other case is a fresh dispatch, which is what
    this clause makes every dispatch that is not a resume.
    """
    runner = _Runner(boards=boards)
    _install_runner(monkeypatch=monkeypatch, runner=runner)
    args = _dispatch_args(cwd=cwd, factory=factory)
    return (
        args_with_dispatch_factory_target(
            args=args, repo=cwd, work_item_id=_WORK_ITEM_ID, resume=resume
        ),
        runner,
    )


# ---------------------------------------------------------------------------
# Scenario 53 — host load belongs to Fabro's scheduler, not Dispatcher refusal.
# ---------------------------------------------------------------------------


def _dispatch_target(*, cwd: Path) -> None:
    """The one-slot dispatch target both Scenario 53 legs drive."""
    _write_config(cwd=cwd, wip_cap=1)
    _write_target_workflow(cwd=cwd)
    _seed_item()


def test_scenario53_admits_a_free_wip_item_and_submits_while_other_runs_are_in_flight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A free WIP slot admits and submits despite work already running on a factory.

    Five runs are in flight on the default factory, which is exactly the host
    load the scenario says must not become a refusal. Every assertion is a
    reading of the ONE real invocation: the Dispatcher's own exit code, the row
    the launch found `active`, the capacity read that observed the busy host,
    and the `fabro run` argv the production port rendered from the plan that
    invocation built. Any one of them alone is satisfiable by a build the
    scenario forbids — a host-capacity gate refuses before the row becomes
    `active`, a wave that claimed the row and never reached the launch leaves
    the argv list empty, and a build that never read a server at all would
    still place the dispatch somewhere.
    """
    _dispatch_target(cwd=tmp_path)

    exit_code, launched, runner = _loop_dispatch(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        boards={
            _DEFAULT_SERVER: _Board(runs=5, ceiling=_DEFAULT_CEILING),
            _OVERFLOW_SERVER: _Board(runs=0, ceiling=_OVERFLOW_CEILING),
        },
    )

    assert exit_code == 0
    assert [launch.status for launch in launched] == ["active"]
    assert any(_server_of(argv=argv) == _DEFAULT_SERVER for argv in runner.capacity_argvs())
    assert _submitted_argv(runner=runner)[-2:] == ["--server", _OVERFLOW_SERVER]
    assert _non_green_outcomes(cwd=tmp_path) == []


def test_scenario53_submits_an_admitted_item_when_the_scheduler_is_at_its_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A saturated board selects the default and still submits a scheduler-queued run.

    Both declared factories report their own scheduler ceiling reached, which is
    the reading a capacity-aware Dispatcher is most tempted to hold or refuse
    on. The journal reason is what says the saturated reading was MADE, and the
    exit code plus the argv are what say the dispatch nonetheless proceeded —
    onto the default, where Fabro's scheduler queues it. The refused-outcome
    list is asserted EMPTY because "neither refused nor deferred" is a negative
    the other three readings cannot carry: a wave that admitted the row, placed
    it, and then reported a capacity refusal alongside would satisfy every one
    of them.
    """
    _dispatch_target(cwd=tmp_path)

    exit_code, launched, runner = _loop_dispatch(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        boards={
            _DEFAULT_SERVER: _Board(runs=_DEFAULT_CEILING, ceiling=_DEFAULT_CEILING),
            _OVERFLOW_SERVER: _Board(runs=_OVERFLOW_CEILING, ceiling=_OVERFLOW_CEILING),
        },
    )

    assert exit_code == 0
    assert [launch.status for launch in launched] == ["active"]
    assert _selection_records(cwd=tmp_path)[-1]["reason"] == _REASON_NO_CANDIDATE
    assert _submitted_argv(runner=runner)[-2:] == ["--server", _DEFAULT_SERVER]
    assert _non_green_outcomes(cwd=tmp_path) == []


def test_the_less_utilized_overflow_factory_receives_the_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A: 6 of 10, B: 0 of 2 — the dispatch lands on B and the record names B.

    All three hand-offs are asserted in ONE case because they are three points
    on one chain and a failure has to say which point dropped the name: the
    resolved target, the item's dispatch-factory record, or the launch argv.
    Splitting them would re-run the chain three times to learn the same thing.

    `--server` is asserted as the LAST two argv tokens because the pinned engine
    requires the flag to stay last on the subcommand, and as adjacent TOKENS
    rather than by substring because an address spliced onto the flag would
    satisfy a substring probe and be rejected by the engine.
    """
    _write_config(cwd=tmp_path)
    _seed_item()
    _ = _selection_module()

    resolved, runner = _resolve(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        boards={
            _DEFAULT_SERVER: _Board(runs=6, ceiling=_DEFAULT_CEILING),
            _OVERFLOW_SERVER: _Board(runs=0, ceiling=_OVERFLOW_CEILING),
        },
    )

    assert resolved.fabro_factory_target.name == _OVERFLOW_FACTORY
    assert _recorded_factory() == _OVERFLOW_FACTORY
    assert _launch_argv(cwd=tmp_path, runner=runner, args=resolved)[-2:] == [
        "--server",
        _OVERFLOW_SERVER,
    ]


@pytest.mark.parametrize(
    ("case", "default_runs", "overflow_runs"),
    [("less-utilized-default", 4, 1), ("equal-utilization", 5, 1)],
    ids=["less-utilized-default", "equal-utilization"],
)
def test_the_default_factory_keeps_the_dispatch_when_it_is_not_more_utilized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    default_runs: int,
    overflow_runs: int,
) -> None:
    """4 of 10 beats 1 of 2 on utilization; 5 of 10 TIES 1 of 2 and still wins.

    The tie case is what makes the comparison a RATIO rather than a count: at 5
    and 1 the default holds more runs than the overflow factory by every absolute
    measure, and only utilization makes them equal — at which point the clause's
    "ties go to the earlier candidate" puts the dispatch on the default. An
    implementation comparing free slots, or remaining capacity, sends this case
    to the overflow factory while passing the case above.
    """
    del case
    _write_config(cwd=tmp_path)
    _seed_item()
    _ = _selection_module()

    resolved, _ = _resolve(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        boards={
            _DEFAULT_SERVER: _Board(runs=default_runs, ceiling=_DEFAULT_CEILING),
            _OVERFLOW_SERVER: _Board(runs=overflow_runs, ceiling=_OVERFLOW_CEILING),
        },
    )

    assert resolved.fabro_factory_target.name == _DEFAULT_FACTORY
    assert _recorded_factory() == _DEFAULT_FACTORY
    records = _selection_records(cwd=tmp_path)
    assert [record["chosen"] for record in records] == [_DEFAULT_FACTORY]
    assert [record["reason"] for record in records] == [_REASON_LEAST_UTILIZED]


@pytest.mark.parametrize(
    ("case", "overflow_board"),
    [
        ("saturated", _Board(runs=2, ceiling=_OVERFLOW_CEILING)),
        ("read-failed", _Board(runs=0, ceiling=None, unreadable=True)),
        ("ceiling-unreadable", _Board(runs=0, ceiling=None)),
    ],
    ids=["saturated", "read-failed", "ceiling-unreadable"],
)
def test_with_no_candidate_free_the_dispatch_goes_to_the_default_and_is_not_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    overflow_board: _Board,
) -> None:
    """A saturated default plus an unusable overflow still SUBMITS, on the default.

    The launch argv is asserted alongside the journal reason because "neither
    refused nor deferred" is a negative: a refusal leaves no argv at all, so the
    argv is what separates "placed on the default, where its scheduler queues it"
    from "declined on capacity grounds".

    The three overflow boards are parametrized together because the clause
    treats them identically — saturated, read failed, ceiling unreadable — and an
    implementation that reported an unmeasured candidate as having room would
    send the dispatch to a factory it never observed.
    """
    del case
    _write_config(cwd=tmp_path)
    _seed_item()
    _ = _selection_module()

    resolved, runner = _resolve(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        boards={
            _DEFAULT_SERVER: _Board(runs=_DEFAULT_CEILING, ceiling=_DEFAULT_CEILING),
            _OVERFLOW_SERVER: overflow_board,
        },
    )

    assert resolved.fabro_factory_target.name == _DEFAULT_FACTORY
    assert _recorded_factory() == _DEFAULT_FACTORY
    assert _launch_argv(cwd=tmp_path, runner=runner, args=resolved)[-2:] == [
        "--server",
        _DEFAULT_SERVER,
    ]
    records = _selection_records(cwd=tmp_path)
    assert [record["reason"] for record in records] == [_REASON_NO_CANDIDATE]


def test_one_journal_record_lists_every_candidate_in_order_with_what_it_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EXACTLY one record, candidates in candidate order, counts or a failure reason.

    The record is asserted FIELD BY FIELD rather than by containment: a record
    that merely mentioned the chosen factory would satisfy an `in` check while
    naming neither what each candidate reported nor why the choice was made, and
    those are the two things the clause requires of it. The unreadable candidate
    carries a REASON in place of its counts, and its count and ceiling are
    asserted `None` — a zero there would read as a factory the Dispatcher
    observed to be idle, which is the one reading that would send work to a
    server nobody could reach.

    The default is deliberately left with a FREE SLOT, so the record under test
    is one a SUCCESSFUL ranking wrote: the clause requires a record per
    selection rather than per fallback, and the saturated shape is already
    graded by the no-free-slot case above. It is also the arm where a candidate
    the ranking never considered would be easiest to drop — the unreadable one
    could not win, so only the record says it was looked at.
    """
    _write_config(cwd=tmp_path)
    _seed_item()
    _ = _selection_module()

    _, _ = _resolve(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        boards={
            _DEFAULT_SERVER: _Board(runs=6, ceiling=_DEFAULT_CEILING),
            _OVERFLOW_SERVER: _Board(runs=0, ceiling=None, unreadable=True),
        },
    )

    records = _selection_records(cwd=tmp_path)

    assert len(records) == 1
    record = records[0]
    assert record["stage"] == _SELECTION_STAGE
    assert record["work_item_id"] == _WORK_ITEM_ID
    assert record["chosen"] == _DEFAULT_FACTORY
    assert record["reason"] == _REASON_LEAST_UTILIZED
    assert [candidate["factory"] for candidate in record["candidates"]] == [
        _DEFAULT_FACTORY,
        _OVERFLOW_FACTORY,
    ]
    assert record["candidates"][0]["run_count"] == 6
    assert record["candidates"][0]["max_concurrent_runs"] == _DEFAULT_CEILING
    assert record["candidates"][0]["unreadable"] is None
    assert record["candidates"][1]["run_count"] is None
    assert record["candidates"][1]["max_concurrent_runs"] is None
    assert isinstance(record["candidates"][1]["unreadable"], str)


@pytest.mark.parametrize(
    "case",
    ["explicit-flag", "environment", "recorded"],
)
def test_a_pinned_dispatch_reads_no_capacity_and_journals_no_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    """Each of the three pins lands on its factory having read NEITHER server.

    The capacity argv list is asserted EMPTY, which is the only assertion that
    can fail for the right reason: a pinned dispatch resolves to its own factory
    whether or not the reads were spent, so an implementation that measured both
    servers and discarded the answer passes every other assertion while putting
    two round trips on every pinned dispatch and every resume. The unpinned cases
    above are the positive control that this same runner IS reached.

    The three pins are parametrized together because the clause names them
    together and an implementation can honour one and miss another — the recorded
    pin especially, since it arrives from the ledger rather than from the command
    line.

    The RECORDED row drives a resume, which is what the clause makes that pin:
    "for a resume only, the item's recorded factory". Dispatched fresh the same
    row carries no pin at all and overflow selection applies to it, which is
    exactly what the unpinned cases above measure.
    """
    _write_config(cwd=tmp_path)
    _seed_item()
    _ = _selection_module()
    if case == "environment":
        monkeypatch.setenv(_FACTORY_SELECTION_ENV_VAR, _OVERFLOW_FACTORY)
    if case == "recorded":
        record_dispatch_factory(
            path=_store(), work_item_id=_WORK_ITEM_ID, factory=_OVERFLOW_FACTORY
        )

    resolved, runner = _resolve(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        boards={
            _DEFAULT_SERVER: _Board(runs=0, ceiling=_DEFAULT_CEILING),
            _OVERFLOW_SERVER: _Board(runs=2, ceiling=_OVERFLOW_CEILING),
        },
        factory=_OVERFLOW_FACTORY if case == "explicit-flag" else None,
        resume=case == "recorded",
    )

    assert resolved.fabro_factory_target.name == _OVERFLOW_FACTORY
    assert runner.capacity_argvs() == []
    assert _selection_records(cwd=tmp_path) == []


def test_an_environment_pinned_dispatch_is_stamped_without_any_capacity_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LIVESPEC_FABRO_FACTORY` pins the ADMISSION resolution, which holds no namespace.

    Taken at the pending CLAIM STAMP rather than at the dispatch resolution,
    because the stamp is where the loss lands. Admission resolves the factory
    through the namespace-less form of the precedence — it carries no `--factory`
    flag to read the variable out of — while the dispatch resolution does honour
    the variable, so a variable invisible to the first stamps the row with a
    factory the dispatch never reaches. Every assertion about the dispatch itself
    still passes in that state, which is why the case is written here: this
    variable is the ONLY routing mechanism `drive.py` has, and it is used
    precisely when the recorded factory identity is the point.

    The pinned factory is deliberately the one a ranking would REJECT: hp reports
    6 of 10 against petri's 0 of 2, so a ranking that ran at all answers petri.
    The stamped name and the empty capacity-argv list therefore fail
    independently — the first if the answer came from a reading, the second if a
    reading was spent at all.
    """
    _write_config(cwd=tmp_path)
    _seed_item()
    _ = _selection_module()
    monkeypatch.setenv(_FACTORY_SELECTION_ENV_VAR, _DEFAULT_FACTORY)
    runner = _Runner(
        boards={
            _DEFAULT_SERVER: _Board(runs=6, ceiling=_DEFAULT_CEILING),
            _OVERFLOW_SERVER: _Board(runs=0, ceiling=_OVERFLOW_CEILING),
        }
    )
    _install_runner(monkeypatch=monkeypatch, runner=runner)

    stamp_pending_claim(
        repo=tmp_path,
        work_item_id=_WORK_ITEM_ID,
        dispatch_id=_DISPATCH_ID,
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
    )

    stamp = claim_row_for(path=_store(), work_item_id=_WORK_ITEM_ID).stamp
    assert stamp is not None
    assert stamp.factory_name == _DEFAULT_FACTORY
    assert runner.capacity_argvs() == []
    assert _selection_records(cwd=tmp_path) == []


def test_a_wave_of_unpinned_items_is_ranked_once_for_the_whole_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Five unpinned items, ONE ranking: two reads per server, not two per item.

    The pre-claim gate grades the engine of every target the selection would
    dispatch to, and in a repository that declares overflow every unpinned item
    of one wave is placed by the same ranking — so the capacity reads are a
    property of the INVOCATION and not of the item count.

    Asserted as the exact argv sequence rather than as a bound, because a
    per-item ranking returns the same target tuple and writes the same gate
    records: the only thing that says it ranked five times is the round trips it
    spent, four per ranking, each bounded at the run reader's own 60-second
    timeout — inside the pre-dispatch wall, whose whole purpose is to settle
    admission before anything further is spent. A per-item ranking is also
    several independent live readings, which can disagree with each other, and
    the `dispatcher.minimum_release` floor is graded only against the targets
    this one call returns.

    The journal is asserted EMPTY for the same reason the clause requires one
    record per selection: the gate ranks and the dispatch resolution records, so
    a record written here would make the one record several, each describing a
    reading no dispatch acted on.
    """
    _write_config(cwd=tmp_path)
    for work_item_id in _WAVE_ITEM_IDS:
        _seed_item(work_item_id=work_item_id)
    _ = _selection_module()
    runner = _Runner(
        boards={
            _DEFAULT_SERVER: _Board(runs=6, ceiling=_DEFAULT_CEILING),
            _OVERFLOW_SERVER: _Board(runs=0, ceiling=_OVERFLOW_CEILING),
        }
    )
    _install_runner(monkeypatch=monkeypatch, runner=runner)

    targets = dispatch_factory_targets(
        args=_dispatch_args(cwd=tmp_path),
        repo=tmp_path,
        work_item_ids=_WAVE_ITEM_IDS,
    )

    assert [target.name for target in targets] == [_OVERFLOW_FACTORY]
    assert [_server_of(argv=argv) for argv in runner.capacity_argvs()] == [
        _DEFAULT_SERVER,
        _DEFAULT_SERVER,
        _OVERFLOW_SERVER,
        _OVERFLOW_SERVER,
    ]
    assert _selection_records(cwd=tmp_path) == []


def test_a_registry_backed_candidate_is_resolved_before_its_server_is_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The registry's address is what gets read, and the dispatch lands on it.

    Asserted at the capacity ARGV rather than only at the chosen factory: a
    candidate the registry resolves is selectable either way, and the argv is the
    only thing that says the reads went to the registry's address rather than to
    a committed one — a registry-backed entry commits none, so a resolution that
    skipped the registry would read a factory with no server and report the
    candidate unmeasured, which looks exactly like a saturated one.
    """
    registry = tmp_path / "fabro-factories.json"
    _ = registry.write_text(
        json.dumps({_OVERFLOW_FACTORY: {"server": _REGISTRY_SERVER}}), encoding="utf-8"
    )
    monkeypatch.setenv(_REGISTRY_PATH_ENV_VAR, str(registry))
    _write_config(cwd=tmp_path, overflow_entry={"registry": True})
    _seed_item()
    _ = _selection_module()

    resolved, runner = _resolve(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        boards={
            _DEFAULT_SERVER: _Board(runs=9, ceiling=_DEFAULT_CEILING),
            _REGISTRY_SERVER: _Board(runs=0, ceiling=_OVERFLOW_CEILING),
        },
    )

    assert resolved.fabro_factory_target.name == _OVERFLOW_FACTORY
    assert resolved.fabro_factory_target.server == _REGISTRY_SERVER
    assert [_server_of(argv=argv) for argv in runner.capacity_argvs()] == [
        _DEFAULT_SERVER,
        _DEFAULT_SERVER,
        _REGISTRY_SERVER,
        _REGISTRY_SERVER,
    ]


def test_a_registry_backed_candidate_the_registry_cannot_resolve_has_no_free_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unresolvable registry candidate is passed over, and the dispatch proceeds.

    The discriminating assertion is that the DEFAULT still receives the dispatch
    while reporting 9 of 10 — a free slot the overflow factory would have won on
    utilization had it been measurable. An implementation that read an
    unresolvable candidate as idle would send the dispatch to a factory with no
    address, which resolves to the ambient local Fabro: a run created on the
    dispatching host with the item's record naming a factory the work never
    reached.
    """
    registry = tmp_path / "fabro-factories.json"
    _ = registry.write_text(json.dumps({"someone-else": {}}), encoding="utf-8")
    monkeypatch.setenv(_REGISTRY_PATH_ENV_VAR, str(registry))
    _write_config(cwd=tmp_path, overflow_entry={"registry": True})
    _seed_item()
    _ = _selection_module()

    resolved, runner = _resolve(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        boards={_DEFAULT_SERVER: _Board(runs=9, ceiling=_DEFAULT_CEILING)},
    )

    assert resolved.fabro_factory_target.name == _DEFAULT_FACTORY
    assert [_server_of(argv=argv) for argv in runner.capacity_argvs()] == [
        _DEFAULT_SERVER,
        _DEFAULT_SERVER,
    ]
    record = _selection_records(cwd=tmp_path)[0]
    assert record["chosen"] == _DEFAULT_FACTORY
    assert record["reason"] == _REASON_LEAST_UTILIZED
    assert isinstance(record["candidates"][1]["unreadable"], str)


def test_a_violating_overflow_entry_is_refused_before_the_item_is_claimed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The dispatch preamble refuses, names the value, and leaves the row alone.

    Taken off `dispatch_preamble` because that is the whole of what runs ahead of
    admission, and the ledger is snapshotted around it: a refusal that fired
    after stamping would satisfy a message-only assertion while leaving the row
    claimed under a dispatch that never placed work.
    """
    _write_config(cwd=tmp_path, overflow=["ghost"])
    _seed_item()
    _ = _selection_module()
    before = _item_state()

    result = dispatch_preamble(
        args=argparse.Namespace(fabro_bin=None, janitor=None, journal=None),
        repo=tmp_path,
    )

    refusal = capsys.readouterr().err
    assert "dispatcher.overflow_factories[0]" in refusal
    assert repr("ghost") in refusal
    assert result == (None, _EXIT_PRECONDITION_ERROR)
    assert _item_state() == before
