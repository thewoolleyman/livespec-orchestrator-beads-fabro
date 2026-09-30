"""Tests for the shared acceptance-eligibility decision and its two walls (v114).

The effective-acceptance-criteria clause of `SPECIFICATION/contracts.md` ratifies
exactly ONE public decision combining the effective-criteria result with the
effective workflow variant, and requires the pre-dispatch wall, the drain, the
approve transition, `next` and the unrunnable-acceptance fact to CONSUME that one
decision rather than re-deriving any part of it. The section checks refuse with
the dedicated exit code `5`, distinct from the precondition exit `3`.

EVERY REFUSAL TEST HERE IS PAIRED WITH AN ADMITTING CONTROL. A wall that refused
everything would satisfy an exit-5 assertion perfectly, and the failure would
look exactly like a working wall from the refusing side alone. The control is the
same path, the same repository and the same item shape with only the Definition
of Done section differing.

THE `human-only` CASE IS THE ONE THAT SURPRISES. `human-only` is eligible with
respect to the gradeable-assertion COUNT, because the human owns that grading —
but it is NOT exempt from the section requirement: the clause says every
implement-kind item, "`human-only` included", is ineligible while its section is
absent, precisely because a human accepts AGAINST a stated definition.
"""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_eligibility import (
    acceptance_eligibility,
    pre_dispatch_criteria_refusal,
)
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_EXIT_UNGRADEABLE_CRITERIA = 5
_SPEC_HEADING = "## Effective acceptance criteria"
_SECTION = (
    "## Definition of Done\n"
    "\n"
    "- The wall refuses an item whose section is absent.\n"
    "- The refusal names the offending element of the section.\n"
    "\n"
    f"References: {_SPEC_HEADING}\n"
)
_HUMAN_ATTESTED_ASSERTION = "A human confirms the console renders the new row."
_MIXED_SECTION = (
    "## Definition of Done\n"
    "\n"
    "- The wall refuses an item whose section is absent.\n"
    "\n"
    "### Human-attested\n"
    "\n"
    "Reason: the proof needs a session on an external administrative console.\n"
    "\n"
    f"- {_HUMAN_ATTESTED_ASSERTION}\n"
    "\n"
    f"References: {_SPEC_HEADING}\n"
)


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-v114wall",
        type="task",
        status="ready",
        title="A gated task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-30T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _config(*, repo_root: Path | None = None) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _spec_tree(*, repo: Path) -> None:
    """The governed spec tree the reference line is validated against."""
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )


def _valve_repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib",'
        ' "fake": true}}}',
        encoding="utf-8",
    )
    _spec_tree(repo=repo)
    return repo


def _git(*, repo: Path, argv: list[str]) -> None:
    _ = subprocess.run(["git", *argv], cwd=repo, check=True, capture_output=True, text=True)


def _origin_backed_repo(*, tmp_path: Path) -> Path:
    """A pushed clone the dispatch preamble's source-checkout preflight accepts."""
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    _git(repo=tmp_path, argv=["init", "--bare", str(origin)])
    _git(repo=tmp_path, argv=["clone", str(origin), str(repo)])
    _git(repo=repo, argv=["config", "user.email", "test@example.com"])
    _git(repo=repo, argv=["config", "user.name", "Test User"])
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    _spec_tree(repo=repo)
    _git(repo=repo, argv=["add", "."])
    _git(repo=repo, argv=["commit", "-m", "initial"])
    _git(repo=repo, argv=["push", "origin", "HEAD:master"])
    _git(repo=repo, argv=["fetch", "origin"])
    return repo


# --- the one decision --------------------------------------------------------


def test_the_decision_refuses_an_implement_kind_item_with_no_section(tmp_path: Path) -> None:
    repo = _valve_repo(tmp_path=tmp_path)

    decision = acceptance_eligibility(item=_item(), cwd=repo)

    assert decision.eligible is False
    assert decision.refusal is not None
    assert "bd-ib-v114wall" in decision.refusal
    assert "Definition of Done" in decision.refusal


def test_the_decision_clears_an_item_carrying_a_valid_section(tmp_path: Path) -> None:
    repo = _valve_repo(tmp_path=tmp_path)

    decision = acceptance_eligibility(item=_item(description=_SECTION), cwd=repo)

    assert decision.eligible is True
    assert decision.refusal is None
    assert decision.findings == ()
    assert decision.criteria.source == "description-definition-of-done"


def test_the_decision_names_an_unresolved_reference_rather_than_the_count(
    tmp_path: Path,
) -> None:
    repo = _valve_repo(tmp_path=tmp_path)
    description = (
        "## Definition of Done\n"
        "\n"
        "- The reference does not resolve.\n"
        "\n"
        "References: ## Scenario 999 — No such heading\n"
    )

    decision = acceptance_eligibility(item=_item(description=description), cwd=repo)

    assert decision.eligible is False
    assert decision.refusal is not None
    assert "## Scenario 999 — No such heading" in decision.refusal
    # The criteria themselves ARE gradeable, so an item refused only for its
    # reference must not be reported as carrying empty criteria.
    assert decision.criteria.gradeable is True


def test_the_decision_names_a_malformed_proof_mode(tmp_path: Path) -> None:
    repo = _valve_repo(tmp_path=tmp_path)
    description = (
        "## Definition of Done\n"
        "\n"
        "### Human-attested\n"
        "\n"
        "- A human attests this one.\n"
        "\n"
        f"References: {_SPEC_HEADING}\n"
    )

    decision = acceptance_eligibility(item=_item(description=description), cwd=repo)

    assert decision.eligible is False
    assert decision.refusal is not None
    assert "Reason:" in decision.refusal


def test_a_human_only_item_is_still_refused_for_an_absent_section(tmp_path: Path) -> None:
    # The surprising half of the clause: `human-only` escapes the
    # gradeable-assertion COUNT, never the section requirement.
    repo = _valve_repo(tmp_path=tmp_path)

    decision = acceptance_eligibility(item=_item(acceptance_policy="human-only"), cwd=repo)

    assert decision.eligible is False
    assert decision.refusal is not None
    assert "Definition of Done" in decision.refusal


def test_a_human_only_item_carrying_a_section_is_eligible(tmp_path: Path) -> None:
    repo = _valve_repo(tmp_path=tmp_path)
    item = _item(acceptance_policy="human-only", description=_SECTION)

    assert acceptance_eligibility(item=item, cwd=repo).eligible is True


def test_the_decision_still_refuses_an_ai_dispositive_item_with_no_gradeable_criteria(
    tmp_path: Path,
) -> None:
    # The pre-v114 refusal is unchanged: a section that parses to nothing
    # gradeable is still an empty-criteria refusal, not only a section finding.
    repo = _valve_repo(tmp_path=tmp_path)
    description = f"## Definition of Done\n\nReferences: {_SPEC_HEADING}\n"

    decision = acceptance_eligibility(item=_item(description=description), cwd=repo)

    assert decision.eligible is False
    assert decision.refusal is not None
    assert "empty or ungradeable" in decision.refusal


def test_the_wall_lists_every_offending_candidate_of_a_wave(tmp_path: Path) -> None:
    repo = _valve_repo(tmp_path=tmp_path)
    wave = [_item(), _item(id="bd-ib-second"), _item(id="bd-ib-third", description=_SECTION)]

    refusal = pre_dispatch_criteria_refusal(items=wave, cwd=repo)

    assert refusal is not None
    assert "no factory run was created" in refusal
    assert "bd-ib-v114wall" in refusal
    assert "bd-ib-second" in refusal


def test_the_wall_passes_a_conforming_wave(tmp_path: Path) -> None:
    repo = _valve_repo(tmp_path=tmp_path)

    assert pre_dispatch_criteria_refusal(items=[_item(description=_SECTION)], cwd=repo) is None


# --- consumer: the entry-to-`ready` approve valve ----------------------------


def test_approve_refuses_an_item_whose_section_is_absent(tmp_path: Path) -> None:
    repo = _valve_repo(tmp_path=tmp_path)
    append_work_item(
        path=_config(),
        item=_item(status="pending-approval", admission_policy="manual"),
    )

    result = run_human_valve_action(repo=repo, action_id="approve:bd-ib-v114wall")

    assert result["status"] == "failed"
    assert "Definition of Done" in result["summary"]
    # It RESTS where it is: refusing entry to `ready` is not a move.
    assert _fake().show_issue(issue_id="bd-ib-v114wall")["status"] == "pending-approval"


def test_approve_admits_an_item_whose_section_is_valid(tmp_path: Path) -> None:
    repo = _valve_repo(tmp_path=tmp_path)
    append_work_item(
        path=_config(),
        item=_item(
            status="pending-approval",
            admission_policy="manual",
            description=_SECTION,
        ),
    )

    result = run_human_valve_action(repo=repo, action_id="approve:bd-ib-v114wall")

    assert result["status"] == "green"
    assert _fake().show_issue(issue_id="bd-ib-v114wall")["status"] == "ready"


# --- consumer: the pre-dispatch wall on both dispatch entry paths ------------


def test_dispatch_refuses_an_absent_section_before_any_run_with_exit_5(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _origin_backed_repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())

    rc = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            "bd-ib-v114wall",
            "--journal",
            str(tmp_path / "journal.jsonl"),
        ]
    )

    assert rc == _EXIT_UNGRADEABLE_CRITERIA
    err = capsys.readouterr().err
    assert "no factory run was created" in err
    assert "Definition of Done" in err
    assert next(iter(read_work_items(path=_config()))).status == "ready"


def test_the_drain_refuses_an_absent_section_before_any_run_with_exit_5(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `loop --item` is the drain command's HAND-PICK, which the clause keeps
    # protected by this refusal "even when candidate enumerations filtered the
    # item earlier"; the autonomous pass is the sibling case below.
    repo = _origin_backed_repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())

    rc = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--item",
            "bd-ib-v114wall",
            "--budget",
            "1",
            "--journal",
            str(tmp_path / "journal.jsonl"),
        ]
    )

    assert rc == _EXIT_UNGRADEABLE_CRITERIA
    assert "Definition of Done" in capsys.readouterr().err
    assert next(iter(read_work_items(path=_config()))).status == "ready"


def test_the_autonomous_drain_excludes_an_absent_section_instead_of_refusing(
    tmp_path: Path,
) -> None:
    # The migration posture for the population predating the wall: the row is
    # excluded from the enumeration, stays physically `ready`, and is reported by
    # the unrunnable-acceptance fact — so one unrepaired legacy item does not
    # stop the whole drain with a wave-level exit 5.
    repo = _origin_backed_repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())

    rc = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--journal",
            str(tmp_path / "journal.jsonl"),
        ]
    )

    assert rc == 0
    assert next(iter(read_work_items(path=_config()))).status == "ready"


def test_dispatch_gets_past_the_wall_for_an_item_carrying_a_valid_section(
    tmp_path: Path,
) -> None:
    # The discriminating control for both exit-5 tests above.
    repo = _origin_backed_repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(description=_SECTION))

    rc = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            "bd-ib-v114wall",
            "--journal",
            str(tmp_path / "journal.jsonl"),
        ]
    )

    assert rc != _EXIT_UNGRADEABLE_CRITERIA


# --- derived routing: never stored, computed from the assertion modes ---------


def test_an_all_factory_captured_item_routes_as_factory_captured_only(
    tmp_path: Path,
) -> None:
    repo = _valve_repo(tmp_path=tmp_path)

    decision = acceptance_eligibility(item=_item(description=_SECTION), cwd=repo)

    assert decision.proof_routing == "factory-captured-only"


def test_one_human_attested_assertion_routes_the_whole_item_to_parking(
    tmp_path: Path,
) -> None:
    # The routing is a property of the ITEM derived from its assertions: one
    # human-attested assertion among three factory-captured ones parks the item,
    # because the human leg has to land before it can close.
    repo = _valve_repo(tmp_path=tmp_path)
    item = _item(description=_MIXED_SECTION, acceptance_policy="ai-then-human")

    decision = acceptance_eligibility(item=item, cwd=repo)

    assert decision.proof_routing == "parks-for-human-attestation"


def test_ai_only_is_refused_for_a_human_attested_assertion_naming_both_remedies(
    tmp_path: Path,
) -> None:
    repo = _valve_repo(tmp_path=tmp_path)
    item = _item(description=_MIXED_SECTION, acceptance_policy="ai-only")

    decision = acceptance_eligibility(item=item, cwd=repo)

    assert decision.eligible is False
    assert decision.refusal is not None
    assert _HUMAN_ATTESTED_ASSERTION in decision.refusal
    # Both ratified remedies, named: change the policy, or make the assertion
    # factory-capturable.
    assert "ai-then-human" in decision.refusal
    assert "human-only" in decision.refusal
    assert "factory-capturable" in decision.refusal


def test_a_parked_policy_admits_the_same_mixed_item(tmp_path: Path) -> None:
    # The PARKED-POLICY CONTROL. Without it, the refusal above is equally
    # consistent with a wall that refuses every human-attested item outright,
    # which would make the ratified remedy unreachable.
    repo = _valve_repo(tmp_path=tmp_path)

    for policy in ("ai-then-human", "human-only"):
        item = _item(description=_MIXED_SECTION, acceptance_policy=policy)

        decision = acceptance_eligibility(item=item, cwd=repo)

        assert decision.eligible is True, policy
        assert decision.proof_routing == "parks-for-human-attestation", policy


def test_an_ordinary_ai_only_item_is_not_refused_by_the_routing_check(
    tmp_path: Path,
) -> None:
    # The ORDINARY-ITEM CONTROL: `ai-only` stays legal for an item whose every
    # assertion is factory-captured, which is the whole default case.
    repo = _valve_repo(tmp_path=tmp_path)
    item = _item(description=_SECTION, acceptance_policy="ai-only")

    assert acceptance_eligibility(item=item, cwd=repo).eligible is True


@pytest.mark.parametrize(
    "argv_tail",
    [
        pytest.param(["dispatch", "--item", "bd-ib-v114wall"], id="hand-picked-dispatch"),
        pytest.param(["loop", "--item", "bd-ib-v114wall", "--budget", "1"], id="hand-picked-drain"),
    ],
)
def test_every_dispatch_entry_path_returns_the_same_ai_only_refusal(
    argv_tail: list[str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # ONE decision consumed by every entry path that REACHES the item: the same
    # item must receive the same verdict whether it is named to `dispatch` or
    # named to the drain. The autonomous drain never reaches it — it excludes the
    # row at enumeration, which the sibling test above asserts.
    repo = _origin_backed_repo(tmp_path=tmp_path)
    append_work_item(
        path=_config(),
        item=_item(description=_MIXED_SECTION, acceptance_policy="ai-only"),
    )
    command, *flags = argv_tail

    rc = main(
        argv=[
            command,
            "--repo",
            str(repo),
            *flags,
            "--journal",
            str(tmp_path / "journal.jsonl"),
        ]
    )

    assert rc == _EXIT_UNGRADEABLE_CRITERIA
    err = capsys.readouterr().err
    assert _HUMAN_ATTESTED_ASSERTION in err
    assert "ai-then-human" in err
    assert next(iter(read_work_items(path=_config()))).status == "ready"
