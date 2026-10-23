"""Integration-tier acceptance for Scenario 125's valve run account.

Binds `SPECIFICATION/scenarios.md` "Scenario 125 — The needs-attention valve
item carries the terminated run's account and fails soft" and the v093 rule of
`SPECIFICATION/contracts.md` it realizes: a factory run that needs a decision
TERMINATES, so the account the `needs_human` terminal left behind is the only
thing a human coming to decide has to decide ON.

BOTH CASES COMPOSE THE WHOLE JSON ENVELOPE through the real
`needs_attention.main(argv=["--json", ...])`, over the real store/client seam
against the in-memory `FakeBeadsClient`, a real on-disk dispatch journal and the
repository's own committed factory block. Only the ONE seam that leaves the
process is stood in — the `fabro` CLI, at the runner the production port
constructs — so the run-id attribution, the factory resolution, the `inspect`
argv, the record parse, the summary composition and the conformance boundary are
all production code.

DRIVING THE ENVELOPE IS WHAT MAKES THE SECOND CASE MEAN ANYTHING. Its claim is
that the valve item is STILL SURFACED when the factory cannot be reached, and
that is a claim about the composed snapshot a console reads: an enrichment
asserted in isolation can show the summary degrading but not that the lane
survived — and a lane that vanished because a network read failed would read
downstream as a decision that had already been made.

THE UNREACHABLE LEG IS COMPARED AGAINST THE REACHABLE ONE rather than against a
transcribed title, because "the enrichment is omitted" is only observable
beside the enrichment it omits: the two legs run the IDENTICAL tenant, journal
and configuration and differ in exactly one input — whether the `fabro inspect`
the port issues answers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import (
    _needs_attention_needs_human_question,
    needs_attention,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.needs_attention import SpecNextOutput

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_ITEM = "bd-ib-s125-parked"
_TITLE = "Parked on a question the run could not answer"
_RUN_ID = "01M5S125TERMINATED"
_FACTORY = "hp"
_SERVER = "https://hp-xubuntu.example:32276"
_OTHER_SERVER = "https://vps.example:32276"
_PROMPT = "loop cannot auto-resolve this work-item; the acceptance criteria contradict each other"
_SIGNATURE = "implement|deterministic|acp turn failed"
_PRESERVED_REF = f"refs/heads/needs-human/{_RUN_ID}"
_VALVE_ID = f"valve:resolve-blocked:{_ITEM}"
_DEFAULT_SUMMARY = f"Resolve human-needed block for work-item {_ITEM}: {_TITLE}"
# What an unreachable server produces at this seam: `fabro inspect` exits
# non-zero and says so. A stand-in that returned an empty record would assert
# only that the parser tolerates one.
_REFUSED_EXIT = 1
_REFUSED_STDERR = f"error: failed to connect to {_SERVER}: connection refused"


@dataclass(kw_only=True)
class _Runner:
    """One fake `fabro` CLI, answering `inspect` for the run its argv names."""

    payload: str
    exit_code: int
    calls: list[list[str]] = field(default_factory=list)

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
        self.calls.append(argv)
        return CommandResult(
            exit_code=self.exit_code,
            stdout=self.payload,
            stderr="" if self.exit_code == 0 else _REFUSED_STDERR,
        )


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", "fabro")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _terminated_record() -> str:
    """One `fabro inspect` payload for a run that TERMINATED at `needs_human`.

    The sentinels sit under an OUTPUT key, which is the only place the reader
    honours them: the terminal's own script CONTAINS every sentinel literal by
    construction, so a record whose script source answered would substitute
    shell text for the operator's question.
    """
    return json.dumps(
        [
            {
                "run_id": _RUN_ID,
                "status": {"kind": "failed"},
                "checkpoints": [
                    {
                        "checkpoint": {
                            "next_node_id": "needs_human",
                            "loop_failure_signatures": {_SIGNATURE: 1},
                        }
                    }
                ],
                "nodes": [
                    {
                        "id": "needs_human",
                        "output": {
                            "stderr": (
                                f"LIVESPEC_NEEDS_HUMAN_PRESERVED: {_PRESERVED_REF}\n"
                                f"LIVESPEC_NEEDS_HUMAN: {_PROMPT}"
                            )
                        },
                    }
                ],
            }
        ]
    )


def _project(*, tmp_path: Path) -> Path:
    """A repository root carrying the factory block and the dispatch journal.

    The journal names a SIBLING item's run beside this item's, so the per-item
    filter is exercised rather than assumed, and the factory block declares a
    second factory the item was NOT sent to, so the server the argv names is
    evidence rather than the only value available.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                _PLUGIN_BLOCK: {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "bd-ib",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "default_factory": _FACTORY,
                        "factories": {
                            _FACTORY: {"server": _SERVER},
                            "vps": {"server": _OTHER_SERVER},
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    journal = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    _ = journal.write_text(
        "\n".join(
            json.dumps(record)
            for record in (
                {"work_item_id": "bd-ib-s125-sibling", "run_id": "01M5S125SIBLING"},
                {"work_item_id": _ITEM, "run_id": _RUN_ID},
            )
        )
        + "\n",
        encoding="utf-8",
    )
    append_work_item(
        path=_config(),
        item=replace(
            WorkItem(
                id=_ITEM,
                type="task",
                status="blocked",
                title=_TITLE,
                description="d",
                origin="freeform",
                gap_id=None,
                rank="a1",
                assignee=None,
                depends_on=(),
                captured_at="2026-10-22T00:00:00Z",
                resolution=None,
                reason=None,
                audit=None,
                superseded_by=None,
            ),
            blocked_reason="needs-human",
        ),
    )
    return repo


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    _ = project_root
    return None


def _valve_entry(
    *,
    repo: Path,
    runner: _Runner,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, object]:
    """The composed resolve-blocked entry, read out of the real JSON envelope."""
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    monkeypatch.setattr(_needs_attention_needs_human_question, "ShellCommandRunner", lambda: runner)
    exit_code = needs_attention.main(
        argv=["--json", "--project-root", str(repo), "--repo-name", "repo", "--skip-hygiene"]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    [entry] = [one for one in payload["attention"] if one["id"] == _VALVE_ID]
    return entry


def test_scenario125_the_valve_summary_carries_the_terminated_runs_account(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every fact the clause requires, in the summary a console actually renders.

    The run is inspected on the factory the ITEM was dispatched to rather than
    on whichever server happens to be declared first, so the argv is read off
    the seam: a default-host probe for a run living elsewhere returns cleanly
    and finds nothing, which is the wrong-population read this repository
    catalogues.
    """
    repo = _project(tmp_path=tmp_path)
    runner = _Runner(payload=_terminated_record(), exit_code=0)

    entry = _valve_entry(repo=repo, runner=runner, monkeypatch=monkeypatch, capsys=capsys)
    summary = str(entry["summary"])

    # The lane it enriches is preserved verbatim, never replaced.
    assert summary.startswith(_DEFAULT_SUMMARY)
    # The run's identity, and the factory it lived on by NAME and by SERVER.
    assert _RUN_ID in summary
    assert f"factory {_FACTORY} ({_SERVER})" in summary
    assert _OTHER_SERVER not in summary
    # Why it terminated, what it reported, and where the work survived.
    assert "terminated at the needs_human node" in summary
    assert f"Why: {_SIGNATURE}." in summary
    assert f"It reported: {_PROMPT}." in summary
    assert f"The run's tree is preserved at {_PRESERVED_REF}." in summary
    # The available actions are the EXISTING valves; a terminated run offers
    # neither an attach nor a resume route.
    assert f"resolve-blocked:{_ITEM}:ready" in summary
    assert f"resolve-blocked:{_ITEM}:backlog" in summary
    # Exactly one `inspect`, on the item's own factory server.
    [argv] = runner.calls
    assert argv[1] == "inspect"
    assert argv[2] == _RUN_ID
    assert argv[argv.index("--server") + 1] == _SERVER
    handoff = entry["handoff"]
    assert isinstance(handoff, dict)
    assert handoff["action_id"] == f"resolve-blocked:{_ITEM}:ready"


def test_scenario125_an_unreachable_factory_costs_the_enrichment_and_never_the_valve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The decision is already waiting in the ledger, so the lane must survive.

    The fixture is byte-identical to the reachable case except that the
    `inspect` the port issues is REFUSED, so the comparison isolates the one
    input under test. The enrichment's absence is asserted on its own
    fragments rather than on summary equality alone, since an enrichment that
    had merely dropped one sentence would still differ from the default.
    """
    repo = _project(tmp_path=tmp_path)
    runner = _Runner(payload="", exit_code=_REFUSED_EXIT)

    entry = _valve_entry(repo=repo, runner=runner, monkeypatch=monkeypatch, capsys=capsys)
    summary = str(entry["summary"])

    # The valve item is still surfaced, with the handoff an operator presses.
    assert entry["kind"] == "human-valve"
    handoff = entry["handoff"]
    assert isinstance(handoff, dict)
    assert handoff["action_id"] == f"resolve-blocked:{_ITEM}:ready"
    # The enrichment is omitted — not partially rendered, and not invented.
    assert summary.startswith(_DEFAULT_SUMMARY)
    for fragment in (_RUN_ID, _SERVER, _PROMPT, _SIGNATURE, _PRESERVED_REF):
        assert fragment not in summary
    # The read WAS attempted against the item's own factory: a lane that had
    # skipped the probe altogether would report the same degraded summary.
    [argv] = runner.calls
    assert argv[argv.index("--server") + 1] == _SERVER
