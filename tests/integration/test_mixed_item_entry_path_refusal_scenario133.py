"""Integration-tier binding of Scenario 133's two ENTRY-PATH gherkins.

Binds the entry-path half of `SPECIFICATION/scenarios.md` "Scenario 133 — A mixed
item is refused ai-only from every entry path, parks for its human-attested leg,
and the accept valve refuses until the record exists": the "Declaration and
routing" gherkin, whose last line reads "a direct dispatch --item and the
autonomous loop return the same refusal for the same item", and the "A parked
policy admits the item" gherkin.

WHY A SECOND TEST FOR ALREADY-TESTED BEHAVIOUR. Both gherkins were bound at UNIT
tier by S2 (`bd-ib-uczggw`) against the shared decision primitive
`acceptance_eligibility`, in
`tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_acceptance_eligibility.py`.
The heading taxonomy of `SPECIFICATION/constraints.md` requires a `scenarios.md`
heading to be bound integration-tier-or-above, never at unit tier, because a
scenario describes user-observable behaviour. So this file asserts the same rule
one level out: through the REAL `dispatcher.main(argv=[...])` CLI, down each
entry path's own wall composition — `_dispatcher_run_commands` for
`dispatch --item` and `_dispatcher_loop_command` for the drain — rather than
against the decision those two walls consume.

THE REFUSAL IS COMPARED FOR IDENTITY, NOT FOR CONTAINMENT. The gherkin's claim is
that the two paths return *the same* refusal, and two different refusals that both
exit `5` and both mention the assertion would satisfy every containment check
written here. The drain arm therefore asserts its refusal block EQUALS the
hand-picked dispatch's, character for character.

`run_dispatch` IS RECORDED RATHER THAN MERELY BLOCKED. Exit `5` alone is equally
consistent with a build that claimed the item, launched a factory run and only
then refused — which is the one outcome the clause's "before any factory run is
created" exists to prevent. Each refusing arm asserts the recorder saw NOTHING
launched, beside the ledger row still resting at `ready` with no assignee, which
is what "no claim left behind" means on this substrate.

THE GOVERNED SPEC TREE IS LOAD-BEARING, not scenery. The item's Definition of Done
carries `References: ## Effective acceptance criteria`, which is graded against the
target repository's own `SPECIFICATION/`. Without that tree the refusal every arm
observes would be a missing-reference SECTION finding rather than the `ai-only`
routing refusal under test — the same exit code, the same wall, the wrong rule.

THE AUTONOMOUS PASS EXCLUDES WHERE THE HAND-PICK REFUSES, and that asymmetry is
ratified rather than a gap in this binding. The pre-dispatch-wall clause of
`SPECIFICATION/contracts.md` keeps an "explicit hand-picked dispatch ... protected
by this refusal even when candidate enumerations filtered the item earlier", and
requires an ineligible physical `ready` row to be "excluded from every
dispatch-candidate enumeration" instead, so that one unrepaired row cannot stop the
queue behind it with a wave-level refusal. The autonomous arm here therefore
asserts the half of the gherkin that holds of it — nothing launched, no claim left
behind, and the queue not stopped — while the `loop --item` arm is where the drain
returns the refusal itself.
"""

from __future__ import annotations

import tempfile
import textwrap
from dataclasses import dataclass, field, replace
from itertools import takewhile
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_EXIT_UNGRADEABLE_CRITERIA = 5
_ITEM_ID = "bd-ib-mixedentry"
_RUN_ID = "01M3MIXEDENTRY"
_PR_NUMBER = 19
_REFUSAL_MARKER = "ERROR: refusing to dispatch; no factory run was created:"
_SPEC_HEADING = "## Effective acceptance criteria"
_HUMAN_ASSERTION = "The production console renders the capacity banner."

_FLEET_MANIFEST_TEXT = (
    "// .livespec-fleet-manifest.jsonc — canned test copy\n"
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [\n'
    '    { "repo": "livespec", "class": "core" },\n'
    '    { "repo": "repo", "class": "impl-plugin" }\n'
    "  ]\n"
    "}\n"
)
_COMMITTED_WORKFLOW_TOML = (
    '[workflow]\ngraph = "graph.toml"\n\n[run.environment]\nid = "fabro-sandbox"\n'
)
_MINIMAL_GRAPH = (
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


def _mixed_definition_of_done() -> str:
    """Three `factory_captured` assertions beside one `human_attested` one.

    The gherkin's Given, verbatim in shape: the sub-heading carries the `Reason`
    line the proof-mode declaration requires, so the section PARSES and the only
    rule left to fire is the routing refusal.
    """
    return textwrap.dedent(f"""\
        Implement the slice.

        ## Definition of Done

        - The dispatched slice lands its change.
        - The journal names the evidence leg it used.
        - The pointer cites the record the pass graded.

        ### Human-attested

        Reason: the sandbox has no session on the production console.

        - {_HUMAN_ASSERTION}

        References: {_SPEC_HEADING}
        """)


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    scratch = tmp_path_factory.mktemp("fabro-mixed-entry")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
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


def _item(*, acceptance_policy: str) -> WorkItem:
    """THE SAME item down every arm — only the policy under test differs."""
    base = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="A mixed-proof slice",
        description=_mixed_definition_of_done(),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, acceptance_policy=acceptance_policy)


def _repo_with_workflow(*, root: Path) -> tuple[Path, Path]:
    repo = root / "repo"
    repo.mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    spec = repo / "SPECIFICATION"
    spec.mkdir()
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    workflow = root / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (root / "graph.toml").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return repo, workflow


@dataclass(kw_only=True)
class _DispatchRecorder:
    """The `run_dispatch` seam, recording every work-item it was asked to launch."""

    launched: list[str] = field(default_factory=list)

    def run(self, **kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        self.launched.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=_PR_NUMBER,
            merge_sha="feed19",
            detail="merged",
            fabro_run_id=_RUN_ID,
        )


@dataclass(frozen=True, kw_only=True)
class _EntryPath:
    """One entry path driven over the item: what it returned, said, and left behind."""

    exit_code: int
    stderr: str
    launched: tuple[str, ...]
    item: WorkItem


def _drive(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    label: str,
    argv_tail: list[str],
    acceptance_policy: str,
) -> _EntryPath:
    """Drive ONE real dispatcher entry path over a pristine copy of the item."""
    reset_fake_singleton()
    repo, workflow = _repo_with_workflow(root=tmp_path / label)
    append_work_item(path=_config(), item=_item(acceptance_policy=acceptance_policy))
    recorder = _DispatchRecorder()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recorder.run)
    exit_code = main(
        argv=[
            *argv_tail,
            "--repo",
            str(repo),
            "--workflow",
            str(workflow),
            "--journal",
            str(tmp_path / f"{label}.jsonl"),
        ]
    )
    stderr = capsys.readouterr().err
    stored = materialize_work_items(records=read_work_items(path=_config()))
    return _EntryPath(
        exit_code=exit_code,
        stderr=stderr,
        launched=tuple(recorder.launched),
        item=stored[_ITEM_ID],
    )


def _refusal_block(*, stderr: str) -> str:
    """The wall's rendering: its header line plus the indented detail under it."""
    lines = stderr.splitlines()
    start = next(index for index, line in enumerate(lines) if line == _REFUSAL_MARKER)
    detail = takewhile(lambda line: line.startswith("  "), lines[start + 1 :])
    return "\n".join([lines[start], *detail])


def test_scenario133_each_entry_path_refuses_the_mixed_item_and_a_parked_policy_admits_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Scenario 133 — "Declaration and routing" and "A parked policy admits the item".

    ONE case rather than four, because each arm is the control that makes another
    assertable. The parked-policy arm is what distinguishes the refusal from a wall
    that refuses every human-attested item outright — which would make the ratified
    remedy unreachable, and which the three refusing arms alone cannot tell apart
    from correct behaviour. The autonomous arm is what shows the queue is not
    stopped by the row the hand-picked arms refuse.
    """
    hand_picked = _drive(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        label="hand-picked-dispatch",
        argv_tail=["dispatch", "--item", _ITEM_ID],
        acceptance_policy="ai-only",
    )

    assert hand_picked.exit_code == _EXIT_UNGRADEABLE_CRITERIA
    refusal = _refusal_block(stderr=hand_picked.stderr)
    assert _HUMAN_ASSERTION in refusal
    # Both ratified remedies, named: change the policy (to either parked mode), or
    # make the assertion factory-capturable.
    assert "ai-then-human" in refusal
    assert "human-only" in refusal
    assert "factory-capturable" in refusal
    assert hand_picked.launched == ()
    assert (hand_picked.item.status, hand_picked.item.assignee) == ("ready", None)

    drain = _drive(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        label="drain-hand-picked",
        argv_tail=["loop", "--item", _ITEM_ID, "--budget", "1"],
        acceptance_policy="ai-only",
    )

    assert drain.exit_code == _EXIT_UNGRADEABLE_CRITERIA
    assert _refusal_block(stderr=drain.stderr) == refusal
    assert drain.launched == ()
    assert (drain.item.status, drain.item.assignee) == ("ready", None)

    autonomous = _drive(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        label="drain-autonomous",
        argv_tail=["loop", "--budget", "1"],
        acceptance_policy="ai-only",
    )

    # The ratified migration posture, not a softer verdict: the same decision
    # excludes the row from the enumeration, so the pass neither launches it nor
    # stops the queue behind it, and the row is left exactly where it was for the
    # `hygiene:unrunnable-acceptance` fact to report.
    assert autonomous.exit_code == 0
    assert _REFUSAL_MARKER not in autonomous.stderr
    assert autonomous.launched == ()
    assert (autonomous.item.status, autonomous.item.assignee) == ("ready", None)

    parked = _drive(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        label="parked-policy-control",
        argv_tail=["dispatch", "--item", _ITEM_ID],
        acceptance_policy="ai-then-human",
    )

    assert parked.exit_code != _EXIT_UNGRADEABLE_CRITERIA
    assert _REFUSAL_MARKER not in parked.stderr
    assert parked.launched == (_ITEM_ID,)
    # Admitted AND recorded as parking for its human-attested leg after merge,
    # which is the second gherkin's Then in full.
    assert parked.item.status == "acceptance"
