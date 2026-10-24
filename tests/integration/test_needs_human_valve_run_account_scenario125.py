"""Scenario 125 — the valve item carries the terminated run's account, fail-soft.

Integration-tier binding for the `SPECIFICATION/scenarios.md` heading
`## Scenario 125 — The needs-attention valve item carries the terminated run's
account and fails soft`. Its two gherkin scenarios are the two cases below,
each driven through the COMPOSED `build_attention` envelope rendered to JSON
rather than through the enrichment function alone.

WHY THE COMPOSED ENVELOPE. The scenario's subject is the valve ITEM a console
reads, and the two claims are properties of that item: that its summary carries
the account, and that the item is still THERE when the factory is not. An
enrichment read in isolation can show the first and structurally cannot show
the second — an absent lane and an unenriched lane are the same return value
once the row that would have carried it is gone.

THE FAIL-SOFT DIRECTION IS THE EXPENSIVE ONE. A lane that vanished because a
network read failed reads downstream as a decision that had already been made,
so the human who was being asked is never asked again. The second case
therefore asserts the valve entry is present AND that EVERY field of the
account is absent, not merely the run id — a partially-enriched summary, a run
handle with no question or a factory name with no address, is the shape that
reads as an answer while carrying none.

AN UNREACHABLE FACTORY IS MODELLED AS A REFUSED CONNECTION, raised by the
process seam, rather than as a non-zero exit. That is the arm a real unreachable
host takes, and it reaches the enrichment through a different absorbed-exception
path than a `fabro inspect` that ran and failed; the case also asserts the call
WAS attempted, which is the only place "it could not be reached" is
distinguishable from "it was never addressed".
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import (
    _needs_attention_needs_human_question as enrichment,
)
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands.needs_attention import (
    build_attention,
    render_json,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.needs_attention import SpecNextOutput

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_TENANT = "livespec-orchestrator-beads-fabro"
_PREFIX = "bd-ib"
_ITEM = "bd-ib-parked"
_TITLE = "Parked on a question"
_VALVE_ID = f"valve:resolve-blocked:{_ITEM}"
_FACTORY = "gmktec"
_SERVER = "https://gmktec.example:32276"
_RUN = "01M5NEEDSHUMAN"
_PRESERVED_REF = f"refs/heads/needs-human/{_RUN}"
_PROMPT = "loop cannot auto-resolve this work-item; a provider must be chosen"
_SIGNATURE = "review|deterministic|acp turn failed"
# The graph node a run that needs a decision terminates at, and the unenriched
# summary the lane renders when no account is readable. The disposition sentence
# the sibling answer-disposition enrichment appends is NOT part of either: this
# file reads the run-account half, and Scenario 122's binding reads that one.
_NEEDS_HUMAN_NODE = "needs_human"
_UNENRICHED = f"Resolve human-needed block for work-item {_ITEM}: {_TITLE}"
# The clause that joins the account to the lane it enriches. Present in ANY
# enrichment, however little of the account was readable, so its absence is what
# separates "omitted" from "partially written".
_ACCOUNT_JOINER = "; fabro run"
_REFUSED_CONNECTION = ConnectionRefusedError(111, "Connection refused")


@dataclass(kw_only=True)
class _Runner:
    """One fake `fabro` CLI, recording each argv and answering one payload.

    `raises` is how an UNREACHABLE factory is expressed: the process seam raises
    rather than returning, which is what a refused connection to a factory host
    actually does. A non-zero exit would exercise a different absorbed path and
    would not model the scenario's `Given`.
    """

    payload: str = "[]"
    raises: OSError | None = None
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
        if self.raises is not None:
            raise self.raises
        return CommandResult(exit_code=0, stdout=self.payload, stderr="")


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A fresh in-memory tenant per case, with the fake backend selected."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", "fabro")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def test_scenario125_the_valve_summary_carries_the_terminated_runs_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a blocked needs-human item whose run terminated on a needs_human outcome,
    When needs-attention renders the item's resolve-blocked valve item,
    Then the summary carries the run id, the factory name and its server, that a
    needs_human termination routed the decision to this valve, why it terminated,
    what the run reported, the preserved reference, and the available actions."""
    repo = _repo(tmp_path=tmp_path)
    _seed(repo=repo)
    runner = _Runner(payload=_terminated_record())

    summary = str(_valve_entry(repo=repo, monkeypatch=monkeypatch, runner=runner)["summary"])

    # The lane it enriches is preserved, never replaced.
    assert summary.startswith(_UNENRICHED)
    # The run handle: which run, on which factory, at which address.
    assert _RUN in summary
    assert f"factory {_FACTORY} ({_SERVER})" in summary
    # That a needs_human termination is what routed the decision here.
    assert f"terminated at the {_NEEDS_HUMAN_NODE} node and routed the decision" in summary
    # Why it terminated, and what it reported — two different fields.
    assert f"Why: {_SIGNATURE}" in summary
    assert f"It reported: {_PROMPT}" in summary
    # Where a rework can start FROM, which is the fact the decision turns on.
    assert f"preserved at {_PRESERVED_REF}" in summary
    # The available actions are the EXISTING valve; a terminated run has neither
    # an attach nor a resume route, so neither may be advertised.
    assert f"resolve-blocked:{_ITEM}:ready" in summary
    assert f"resolve-blocked:{_ITEM}:backlog" in summary
    assert "leave the item blocked" in summary
    for forbidden in ("fabro attach", "resume"):
        assert forbidden not in summary
    # The run was inspected on the factory the item was dispatched to, not on
    # whichever engine the reading host happens to run.
    assert [call[1] for call in runner.calls] == ["inspect"]
    assert runner.calls[0][runner.calls[0].index("--server") + 1] == _SERVER


def test_scenario125_an_unreachable_factory_costs_the_enrichment_and_never_the_valve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a blocked needs-human item whose factory is unreachable,
    When needs-attention renders the item's resolve-blocked valve item,
    Then the run account enrichment is omitted,
    And the valve item is still surfaced.

    EVERY field of the account is asserted absent, not merely the run id,
    because a half-written account — a handle with no question, an address with
    no reason — is the shape that reads as an answer while carrying none. The
    joining clause is asserted absent too, since that is the one token present
    in any enrichment however little of it was readable.
    """
    repo = _repo(tmp_path=tmp_path)
    _seed(repo=repo)
    runner = _Runner(raises=_REFUSED_CONNECTION)

    entry = _valve_entry(repo=repo, monkeypatch=monkeypatch, runner=runner)
    summary = str(entry["summary"])

    # The valve is STILL THERE, and still hands the operator the same action.
    assert entry["id"] == _VALVE_ID
    assert entry["kind"] == "human-valve"
    assert entry["handoff"]["action_id"] == f"resolve-blocked:{_ITEM}:ready"
    # And the enrichment is wholly absent rather than partially written.
    assert summary.startswith(_UNENRICHED)
    assert _ACCOUNT_JOINER not in summary
    for field_of_the_account in (
        _RUN,
        _FACTORY,
        _SERVER,
        _NEEDS_HUMAN_NODE,
        _SIGNATURE,
        _PROMPT,
        _PRESERVED_REF,
    ):
        assert field_of_the_account not in summary
    # The factory WAS addressed: that is the only place an unreachable host is
    # distinguishable from one the read never attempted to contact.
    assert [call[1] for call in runner.calls] == ["inspect"]


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    """Stand the cross-plane spec lane down: it answers nothing this heading asks."""
    _ = project_root
    return None


def _valve_entry(
    *, repo: Path, monkeypatch: pytest.MonkeyPatch, runner: _Runner
) -> dict[str, object]:
    """This item's resolve-blocked entry of the composed JSON snapshot.

    Two things are stood down and nothing else. The enrichment's process seam is
    replaced by `runner`, which is the point of the fixture; and the cross-plane
    spec lane is stood down because it reaches outside this repository's tenant
    and answers nothing this heading asks. The sibling answer-disposition
    enrichment is deliberately LEFT STANDING — it appends a sentence of its own,
    which is why the cases below read the account's own fields rather than
    comparing the whole summary string to one this file would have to spell.
    """
    monkeypatch.setattr(enrichment, "ShellCommandRunner", lambda: runner)
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    attention = build_attention(project_root=repo, repo_name="repo", include_hygiene=False)
    payload = json.loads(render_json(attention=attention))
    entries = [entry for entry in payload["attention"] if entry["id"] == _VALVE_ID]
    assert len(entries) == 1
    return dict(entries[0])


def _terminated_record() -> str:
    """A `fabro inspect --json` payload for a run that terminated at needs_human.

    The engine's loop failure signature is what the summary reports as WHY, and
    the node's own stderr carries the preserved ref and the message it reported
    — three fields from two places, so a build that read only one of them
    renders a visibly incomplete account.
    """
    return json.dumps(
        [
            {
                "run_id": _RUN,
                "status": {"kind": "failed"},
                "checkpoints": [
                    {
                        "checkpoint": {
                            "next_node_id": _NEEDS_HUMAN_NODE,
                            "loop_failure_signatures": {_SIGNATURE: 1},
                        }
                    }
                ],
                "nodes": [
                    {
                        "id": _NEEDS_HUMAN_NODE,
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


def _seed(*, repo: Path) -> None:
    """The parked item, and the journal record naming the run it came from."""
    append_work_item(path=_config(), item=_parked())
    journal = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    _ = journal.write_text(
        json.dumps({"work_item_id": _ITEM, "run_id": _RUN}) + "\n", encoding="utf-8"
    )


def _parked() -> WorkItem:
    """A work-item resting at `blocked` with `blocked_reason: needs-human`."""
    return WorkItem(
        id=_ITEM,
        type="task",
        status="blocked",
        title=_TITLE,
        description="It could not be finished without a decision.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason="needs-human",
    )


def _repo(*, tmp_path: Path) -> Path:
    """A governed clone declaring the factory the parked item's run went to."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                _PLUGIN_BLOCK: {
                    "connection": {"prefix": _PREFIX},
                    "dispatcher": {
                        "default_factory": _FACTORY,
                        "factories": {_FACTORY: {"server": _SERVER}},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _config() -> StoreConfig:
    return StoreConfig(
        tenant=_TENANT,
        prefix=_PREFIX,
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
    )
