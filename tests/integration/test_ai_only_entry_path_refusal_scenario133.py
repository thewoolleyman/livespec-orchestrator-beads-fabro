"""A mixed item is refused `ai-only` from every dispatch entry path (Scenario 133).

Binds the "Declaration and routing" and "A parked policy admits the item" gherkin
scenarios of `SPECIFICATION/scenarios.md` Scenario 133 at the INTEGRATION tier, and
the derived-routing clause of `SPECIFICATION/contracts.md` they realize (ratified
v114): when any gradeable assertion is `human_attested`, an effective
`acceptance_policy` of `ai-only` MUST be refused by the host-side wall with a message
naming the human-attested assertions and the two remedies, and that ONE decision MUST
be consumed by every dispatch entry path "so the same item receives the same verdict
from each".

WHY THIS TIER EXISTS BESIDE THE UNIT ONE. The unit module
`tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_acceptance_eligibility.py`
asserts the refusal against the DECISION primitive and, where it reaches the CLI,
grades the admitting control on the refusal code's ABSENCE alone. That control cannot
separate "the wall let the item through" from "the dispatch died one gate later for an
unrelated reason", and nothing in it observes whether a run was created. Here the launch
seam RECORDS, so "before any claim or run exists" is read off the seam and off the
ledger row rather than inferred from an exit code — a dispatch can exit non-zero having
already created a run — and the parked control is graded on the seam actually being
ENTERED.

THE TWO ENTRY PATHS ARE COMPARED BYTE FOR BYTE, not needle by needle. The clause's
requirement is that the two agree, and two refusals that merely both mention the
assertion would satisfy a pair of independently-drifting messages just as well. Both
legs run over ONE seeded item in ONE test, which is what makes "the same item
receives the same verdict" an observation instead of two separate fixtures that
happen to read alike.

THE UNNARROWED AUTONOMOUS PASS IS ITS OWN CASE, because it consumes the same decision
through the other shape the clause ratifies. `acceptance_eligible_candidates` DROPS an
ineligible row from the enumeration instead of refusing the whole wave, so the
autonomous drain leaves the row physically `ready` and unclaimed rather than printing
this refusal. Asserting that here is what stops the module from reading as though an
unnarrowed drain would refuse, and it is the same no-claim guarantee measured on the
one path that reaches the item without naming it.

THE EXPECTED REFUSAL CODE IS THE PRODUCTION SYMBOL, imported from
`_dispatcher_command_common` rather than restated as a local literal. It is the very
constant both dispatch entry paths return, so no second value exists beside it that
could drift: were the production code to move, this module follows it instead of
asserting the retired number and failing for a reason that has nothing to do with the
clause under test.

THE REFERENCE RESOLVES AGAINST A REAL SPEC TREE in the fixture, so the routing
refusal is reached with the mechanical findings arm ARMED and quiet. That arm runs
FIRST and its refusal shadows this one; an unreadable tree makes it skip the
reference check altogether, which would leave the fixture passing for a reason it
had stopped measuring.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_UNGRADEABLE_CRITERIA,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-mixed133"

# The heading the item's reference line names, carried by the fixture's own spec
# tree so the reference RESOLVES and the mechanical findings arm stays quiet.
_SPEC_HEADING = "## Definition-of-Done and Proof-of-Done stages"

_HUMAN_ATTESTED_ASSERTION = (
    "A human confirms the external administrative console renders the parked row."
)
# Scenario 133's own shape: three `factory_captured` assertions and one assertion
# under a `Human-attested` sub-heading carrying a `Reason:` line.
_MIXED_SECTION = (
    "## Definition of Done\n"
    "\n"
    "- The hand-picked dispatch entry path refuses this item before any claim exists.\n"
    "- The autonomous drain command returns the identical refusal for the same item.\n"
    "- A parked acceptance policy admits this same item as the control.\n"
    "\n"
    "### Human-attested\n"
    "\n"
    "Reason: the proof needs a session on an external administrative console that no"
    " factory sandbox can reach.\n"
    "\n"
    f"- {_HUMAN_ATTESTED_ASSERTION}\n"
    "\n"
    f"References: {_SPEC_HEADING}\n"
)

# The wall's own framing line. Used to ISOLATE the refusal from anything else a
# dispatch wrote to stderr, so the two entry paths are compared on the refusal
# itself rather than on whatever preamble surrounded it.
_REFUSAL_MARKER = "ERROR: refusing to dispatch; no factory run was created:"

# The two journal stages a CLAIM leaves behind: the ledger admission that sets the
# assignee, and the dispatch id the pre-run claim mints. Either one present beside a
# refusal would mean the item was claimed before the wall ran.
_CLAIM_STAGES = ("ledger-admit", "dispatch-id")

_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
)
_RESERVED_DIR = ".fabro/workflows/implement-work-item"
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


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment plus a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("ai-only-entry-path-refusal")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:ai-only-entry-path-refusal")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
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


def _seed_item(*, acceptance_policy: str) -> None:
    """Seed ONE mixed item whose only variable is its declared acceptance policy.

    Everything else is held constant across the refused and admitted legs, so the
    parked control differs from the refusal in exactly the thing the clause names as
    the remedy and in nothing else.
    """
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=_ITEM_ID,
            type="task",
            status="ready",
            title="Exercise the mixed-item routing wall",
            description=_MIXED_SECTION,
            origin="freeform",
            gap_id=None,
            rank="a2",
            assignee=None,
            depends_on=(),
            captured_at="2026-10-04T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy=acceptance_policy,
        ),
    )


def _repo(*, tmp_path: Path) -> Path:
    """A governed target carrying the reserved workflow and a readable spec tree."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Chad Woolley",
                    "operator_email": "thewoolleyman@gmail.com",
                },
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {"wip_cap": 3, "acceptance_mode": "ai-only"},
                },
            }
        ),
        encoding="utf-8",
    )
    spec = repo / "SPECIFICATION"
    spec.mkdir()
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nThe clause this item is graded against.\n",
        encoding="utf-8",
    )
    workflow = repo / _RESERVED_DIR
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    return repo


def _recording_run_dispatch(*, calls: list[str]) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in recording that a factory run WAS created."""

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        calls.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="dispatched",
        )

    return _run_dispatch


def _drive(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv_tail: list[str],
) -> tuple[int, list[str]]:
    """Drive one REAL dispatch entry point and report its exit code plus its launches."""
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording_run_dispatch(calls=calls))
    return main(argv=[*argv_tail, "--repo", str(repo), "--no-close-on-merge"]), calls


def _refusal_block(*, stderr: str) -> str:
    """The wall's refusal, isolated from any other line the invocation wrote.

    `str.index` rather than a tolerant search on purpose: a leg that printed no
    refusal at all must fail here rather than silently compare two empty strings.
    """
    return stderr[stderr.index(_REFUSAL_MARKER) :]


def _ledger_row() -> WorkItem:
    return next(item for item in read_work_items(path=_config()) if item.id == _ITEM_ID)


def _claim_records(*, repo: Path) -> list[dict[str, object]]:
    """Every journal record whose stage marks a claim, over the whole journal."""
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return [record for record in records if record.get("stage") in _CLAIM_STAGES]


def test_both_dispatch_entry_paths_refuse_the_mixed_ai_only_item_identically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The hand-picked dispatch and the drain command refuse the same item alike.

    Both legs run over ONE seeded row, which is also what makes the no-claim
    assertions mean something on the second leg: had the first claimed the item, the
    second would have met an `active` row and refused for a different reason.
    """
    _seed_item(acceptance_policy="ai-only")
    repo = _repo(tmp_path=tmp_path)

    hand_picked_code, hand_picked_calls = _drive(
        repo=repo, monkeypatch=monkeypatch, argv_tail=["dispatch", "--item", _ITEM_ID]
    )
    hand_picked_refusal = _refusal_block(stderr=capsys.readouterr().err)
    drain_code, drain_calls = _drive(
        repo=repo,
        monkeypatch=monkeypatch,
        argv_tail=["loop", "--item", _ITEM_ID, "--budget", "1"],
    )
    drain_refusal = _refusal_block(stderr=capsys.readouterr().err)

    # The verdict, the launch seam and the ledger row, for each entry path.
    assert (hand_picked_code, hand_picked_calls) == (EXIT_UNGRADEABLE_CRITERIA, [])
    assert (drain_code, drain_calls) == (EXIT_UNGRADEABLE_CRITERIA, [])
    # The SAME refusal, byte for byte, rather than two messages that each happen to
    # mention the assertion.
    assert drain_refusal == hand_picked_refusal
    # It names the human-attested assertion and BOTH ratified remedies.
    assert _HUMAN_ATTESTED_ASSERTION in hand_picked_refusal
    assert "ai-then-human" in hand_picked_refusal
    assert "human-only" in hand_picked_refusal
    assert "factory-capturable" in hand_picked_refusal
    # Before any claim: the row never moved and nothing claimed it.
    assert (_ledger_row().status, _ledger_row().assignee) == ("ready", None)
    assert _claim_records(repo=repo) == []


def test_the_autonomous_drain_leaves_the_mixed_item_unclaimed_and_unlaunched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The unnarrowed pass consumes the same decision by DROPPING the row.

    The shared decision reaches candidate ENUMERATION as a filter rather than as a
    wave-level refusal, so one ineligible row cannot stop the queue behind it. The
    guarantee this case carries is the same one the refusing legs carry — no claim,
    no run — reached on the one path that never names the item.
    """
    _seed_item(acceptance_policy="ai-only")
    repo = _repo(tmp_path=tmp_path)

    exit_code, calls = _drive(
        repo=repo, monkeypatch=monkeypatch, argv_tail=["loop", "--budget", "1"]
    )

    assert (exit_code, calls) == (0, [])
    assert _REFUSAL_MARKER not in capsys.readouterr().err
    assert (_ledger_row().status, _ledger_row().assignee) == ("ready", None)
    assert _claim_records(repo=repo) == []


def test_a_parked_acceptance_policy_admits_the_same_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CONTROL: the identical item under `ai-then-human` reaches the launch seam.

    Without it the three refusals above are equally consistent with a wall that
    refuses every human-attested item outright, which would make the ratified remedy
    unreachable. It is graded on the seam being ENTERED rather than on an exit code,
    because a dispatch can exit zero having launched nothing at all.
    """
    _seed_item(acceptance_policy="ai-then-human")
    repo = _repo(tmp_path=tmp_path)

    exit_code, calls = _drive(
        repo=repo, monkeypatch=monkeypatch, argv_tail=["dispatch", "--item", _ITEM_ID]
    )

    assert (exit_code, calls) == (0, [_ITEM_ID])
