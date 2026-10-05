"""Tests for the effective-acceptance-criteria primitive and the two walls (v072).

The effective-acceptance-criteria clause of `SPECIFICATION/contracts.md`
ratifies ONE public primitive plus four consumers, so the tests are grouped the
same way:
the primitive's own resolution arcs first, then each of the four gates.

The wiring test in the last group is the one that keeps the clause true over
time. Every behavioural test below would still pass if a gate quietly grew a
SECOND resolution of its own alongside the primitive — the clause's whole point
is that no such second path exists, and only reading the consumers' source can
establish that.
"""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_eligibility import (
    pre_dispatch_criteria_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    CHANGE_IMPLYING_CLASSIFICATION,
    CHANGE_OPTIONAL_CLASSIFICATION,
    CHANGE_OPTIONAL_LABEL,
    CRITERIA_FIELD_SOURCE,
    DESCRIPTION_EXIT_CRITERIA_SOURCE,
    change_classification,
    effective_criteria,
    ungradeable_criteria_refusal,
)
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.commands.groom import (
    CandidateSlice,
    GroomApproval,
    file_approved_slices,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_COMMANDS_DIR = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_PROSE_DIR = Path(__file__).resolve().parents[3] / ".claude-plugin" / "prose"
_PRIMITIVE_MODULE = "_dispatcher_effective_criteria"
_DECISION_MODULE = "_dispatcher_acceptance_eligibility"
_EXIT_UNGRADEABLE_CRITERIA = 5

_TWO_ASSERTIONS = (
    "The dispatcher refuses an ungradeable item before any run is created.\n"
    "The refusal names the work-item id and the resolved source.\n"
)

# The Definition of Done section every implement-kind item must carry since
# v114. It is deliberately BULLET-LESS: this file's subject is the resolution
# order and the wall's GRADEABILITY verdict, which the two legacy sources decide,
# so the section satisfies the section-presence and reference-line checks while
# contributing no gradeable assertion of its own. A section carrying a bullet
# would make every fixture here gradeable from step 1, and each leg below would
# pass without exercising the leg it names. The fixture repositories carry no
# spec tree, so the reference check is unobservable and it is the reference
# line's PRESENCE that is satisfied here.
_EMPTY_DEFINITION_OF_DONE = (
    "## Definition of Done\n" "\n" "References: ## Effective acceptance criteria\n"
)


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-v072",
        type="task",
        status="ready",
        title="A gated task",
        description=f"Do the thing.\n\n{_EMPTY_DEFINITION_OF_DONE}",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-27T00:00:00Z",
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


def _valve_repo(*, tmp_path: Path) -> Path:
    """A bare repo dir carrying the connection block the valve transport resolves."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib",'
        ' "fake": true}}}',
        encoding="utf-8",
    )
    return repo


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


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
    _git(repo=repo, argv=["add", ".livespec.jsonc"])
    _git(repo=repo, argv=["commit", "-m", "initial"])
    _git(repo=repo, argv=["push", "origin", "HEAD:master"])
    _git(repo=repo, argv=["fetch", "origin"])
    return repo


# --- the primitive: resolution order + resolved source ----------------------


def test_effective_criteria_resolves_the_merged_criteria_field() -> None:
    resolved = effective_criteria(item=_item(acceptance_criteria=_TWO_ASSERTIONS))

    assert resolved.source == CRITERIA_FIELD_SOURCE
    assert len(resolved.assertions) == 2
    assert resolved.gradeable
    assert resolved.text == _TWO_ASSERTIONS


def test_effective_criteria_falls_back_to_the_description_exit_criteria_section() -> None:
    description = (
        "Background prose that is not criteria.\n"
        "\n"
        "## Exit criteria\n"
        "\n"
        "The refusal names the work-item id and the resolved source.\n"
    )

    resolved = effective_criteria(item=_item(description=description))

    assert resolved.source == DESCRIPTION_EXIT_CRITERIA_SOURCE
    assert resolved.assertions == ("The refusal names the work-item id and the resolved source.",)
    assert resolved.text == "The refusal names the work-item id and the resolved source."


def test_effective_criteria_stops_the_exit_criteria_section_at_the_next_heading() -> None:
    description = (
        "## Exit criteria\n"
        "\n"
        "The refusal names the work-item id and the resolved source.\n"
        "\n"
        "## Notes\n"
        "\n"
        "Prose that must not be graded as an assertion.\n"
    )

    resolved = effective_criteria(item=_item(description=description))

    assert resolved.assertions == ("The refusal names the work-item id and the resolved source.",)


def test_effective_criteria_ignores_a_heading_that_is_not_exit_criteria() -> None:
    description = "## Design\n\nProse that must not be graded as an assertion.\n"

    resolved = effective_criteria(item=_item(description=description))

    assert resolved.source == DESCRIPTION_EXIT_CRITERIA_SOURCE
    assert resolved.text is None
    assert not resolved.gradeable


def test_effective_criteria_reports_the_fallback_source_when_nothing_resolves() -> None:
    # The two ratified source values are exhaustive, so an item with no criteria
    # anywhere reports the step that WAS resolved rather than a third value.
    resolved = effective_criteria(item=_item(acceptance_criteria=None))

    assert resolved.source == DESCRIPTION_EXIT_CRITERIA_SOURCE
    assert resolved.assertions == ()


def test_effective_criteria_falls_through_an_ungradeable_criteria_field() -> None:
    # A criteria field carrying only a dangling header parses to zero gradeable
    # assertions, so the merged value does NOT win — gradeability, not mere
    # presence, is what the resolution order turns on.
    description = "## Exit criteria\n\nThe refusal names the work-item id.\n"

    resolved = effective_criteria(
        item=_item(acceptance_criteria="Exit criteria:\n", description=description)
    )

    assert resolved.source == DESCRIPTION_EXIT_CRITERIA_SOURCE
    assert resolved.assertions == ("The refusal names the work-item id.",)


def test_effective_criteria_projects_the_parse_for_a_display_and_a_journal() -> None:
    resolved = effective_criteria(item=_item(acceptance_criteria=_TWO_ASSERTIONS))

    # This item resolves from a LEGACY source, so since v114 the display carries
    # the `definition-of-done: missing` marker alongside the count and source.
    assert resolved.parse_display() == (
        "effective acceptance criteria: 2 gradeable assertion(s) resolved from"
        " criteria-field; definition-of-done: missing"
    )
    # The RECORD is deliberately unchanged: it is the leak-free journal
    # projection, and the marker is a display affordance derived from `source`,
    # which the record already carries.
    assert resolved.as_record() == {
        "source": CRITERIA_FIELD_SOURCE,
        "gradeable_assertions": 2,
        "gradeable": True,
    }


# --- the change-implying default and the change-optional escape hatch -------


def test_gradeable_criteria_classify_as_change_implying_by_default() -> None:
    # The default: a gradeable criteria set with NO marker is presumed to
    # require file changes, which is what the empty-diff refusal consumes.
    resolved = effective_criteria(item=_item(acceptance_criteria=_TWO_ASSERTIONS))

    classification = change_classification()

    assert resolved.gradeable
    assert classification.classification == CHANGE_IMPLYING_CLASSIFICATION
    assert classification.change_implying
    assert classification.declared_marker is None


def test_a_declared_change_optional_marker_is_the_one_exemption() -> None:
    # The exemption, and the ONLY one: the item declares it explicitly.
    classification = change_classification(raw_labels=(f"{CHANGE_OPTIONAL_LABEL}true",))

    assert classification.classification == CHANGE_OPTIONAL_CLASSIFICATION
    assert not classification.change_implying
    assert classification.declared_marker == "true"


def test_an_unrelated_label_set_does_not_exempt_an_item() -> None:
    classification = change_classification(raw_labels=("rework:pending", "acceptance:ai-only"))

    assert classification.classification == CHANGE_IMPLYING_CLASSIFICATION
    assert classification.declared_marker is None


@pytest.mark.parametrize(
    ("labels", "expected_marker"),
    [
        pytest.param((f"{CHANGE_OPTIONAL_LABEL}maybe",), "maybe", id="malformed-value"),
        pytest.param((f"{CHANGE_OPTIONAL_LABEL}yes",), "yes", id="unknown-value"),
        pytest.param((f"{CHANGE_OPTIONAL_LABEL}false",), "false", id="negated-value"),
        pytest.param((CHANGE_OPTIONAL_LABEL,), "", id="empty-value"),
        pytest.param(("change-optional",), None, id="valueless-marker"),
        pytest.param((), None, id="absent-marker"),
    ],
)
def test_a_malformed_or_absent_marker_fails_closed_to_change_implying(
    labels: tuple[str, ...],
    expected_marker: str | None,
) -> None:
    # Fail-closed is the whole point: an unreadable marker resolves toward
    # REFUSING an empty diff, never toward accepting one, so a mistyped marker
    # can never silently exempt an item.
    classification = change_classification(raw_labels=labels)

    assert classification.classification == CHANGE_IMPLYING_CLASSIFICATION
    assert classification.classification != CHANGE_OPTIONAL_CLASSIFICATION
    assert classification.declared_marker == expected_marker


def test_the_classification_projects_the_record_the_acceptance_journal_carries() -> None:
    # The raw marker rides along so a mistyped declaration is distinguishable
    # from an absent one, which the classification value alone cannot show.
    assert change_classification(raw_labels=(f"{CHANGE_OPTIONAL_LABEL}nope",)).as_record() == {
        "classification": CHANGE_IMPLYING_CLASSIFICATION,
        "declared_marker": "nope",
    }
    assert change_classification().as_record() == {
        "classification": CHANGE_IMPLYING_CLASSIFICATION,
        "declared_marker": None,
    }


# --- the shared wall predicate ----------------------------------------------


def test_ungradeable_criteria_refusal_clears_a_gradeable_item(tmp_path: Path) -> None:
    item = _item(acceptance_criteria=_TWO_ASSERTIONS)

    assert ungradeable_criteria_refusal(item=item, cwd=tmp_path) is None


def test_ungradeable_criteria_refusal_clears_a_human_only_item(tmp_path: Path) -> None:
    # `human-only` is the ratified remedy for work machine grading cannot judge,
    # so the wall must not fire on it — otherwise the remedy is unreachable.
    item = _item(acceptance_policy="human-only")

    assert ungradeable_criteria_refusal(item=item, cwd=tmp_path) is None


def test_ungradeable_criteria_refusal_names_the_item_the_parse_and_the_remedy(
    tmp_path: Path,
) -> None:
    detail = ungradeable_criteria_refusal(item=_item(), cwd=tmp_path)

    assert detail is not None
    assert "bd-ib-v072" in detail
    assert "empty or ungradeable" in detail
    assert "0 gradeable assertion(s) resolved from description-exit-criteria" in detail
    assert "acceptance_policy to human-only" in detail


def test_ungradeable_criteria_refusal_arms_on_the_unconfigured_acceptance_default(
    tmp_path: Path,
) -> None:
    # An item carrying no per-item policy resolves through the global default,
    # `ai-then-human`, which is AI-dispositive: the wall stays armed rather than
    # opening on the commonest shape of all.
    detail = ungradeable_criteria_refusal(item=_item(acceptance_policy=None), cwd=tmp_path)

    assert detail is not None


def test_pre_dispatch_criteria_refusal_passes_a_conforming_wave(tmp_path: Path) -> None:
    conforming = _item(acceptance_criteria=_TWO_ASSERTIONS)

    assert pre_dispatch_criteria_refusal(items=[conforming], cwd=tmp_path) is None


def test_pre_dispatch_criteria_refusal_lists_every_offending_candidate(tmp_path: Path) -> None:
    wave = [_item(), _item(id="bd-ib-second"), _item(acceptance_criteria=_TWO_ASSERTIONS)]

    refusal = pre_dispatch_criteria_refusal(items=wave, cwd=tmp_path)

    assert refusal is not None
    assert "no factory run was created" in refusal
    assert "bd-ib-v072" in refusal
    assert "bd-ib-second" in refusal


# --- consumer 1: the entry-to-`ready` wall (the human `approve` valve) -------


def test_approve_refuses_an_ai_dispositive_item_with_no_gradeable_criteria(
    tmp_path: Path,
) -> None:
    repo = _valve_repo(tmp_path=tmp_path)
    append_work_item(
        path=_config(),
        item=_item(status="pending-approval", admission_policy="manual"),
    )

    result = run_human_valve_action(repo=repo, action_id="approve:bd-ib-v072")

    assert result["status"] == "failed"
    assert result["domain_error"] == "ungradeable-acceptance-criteria"
    assert "0 gradeable assertion(s)" in result["summary"]
    # It RESTS where it is: refusing entry to `ready` is not a move to
    # `backlog` or `blocked`.
    assert _fake().show_issue(issue_id="bd-ib-v072")["status"] == "pending-approval"


def test_approve_admits_a_pending_item_whose_criteria_are_gradeable(tmp_path: Path) -> None:
    repo = _valve_repo(tmp_path=tmp_path)
    append_work_item(
        path=_config(),
        item=_item(
            status="pending-approval",
            admission_policy="manual",
            acceptance_criteria=_TWO_ASSERTIONS,
        ),
    )

    result = run_human_valve_action(repo=repo, action_id="approve:bd-ib-v072")

    assert result["status"] == "green"
    assert _fake().show_issue(issue_id="bd-ib-v072")["status"] == "ready"


def test_approve_admits_a_human_only_item_carrying_no_criteria(tmp_path: Path) -> None:
    repo = _valve_repo(tmp_path=tmp_path)
    append_work_item(
        path=_config(),
        item=_item(
            status="pending-approval",
            admission_policy="manual",
            acceptance_policy="human-only",
        ),
    )

    result = run_human_valve_action(repo=repo, action_id="approve:bd-ib-v072")

    assert result["status"] == "green"
    assert _fake().show_issue(issue_id="bd-ib-v072")["status"] == "ready"


# --- consumer 2: the pre-dispatch wall (exit 5) -----------------------------


def test_dispatch_refuses_an_ungradeable_item_before_any_run_with_exit_5(
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
            "bd-ib-v072",
            "--journal",
            str(tmp_path / "journal.jsonl"),
        ]
    )

    assert rc == _EXIT_UNGRADEABLE_CRITERIA
    err = capsys.readouterr().err
    assert "no factory run was created" in err
    assert "bd-ib-v072" in err
    # Refused BEFORE admission, so the item never left `ready` and no run
    # exists to reap.
    assert next(iter(read_work_items(path=_config()))).status == "ready"


def test_loop_refuses_an_ungradeable_candidate_before_any_run_with_exit_5(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The drain path still meets the wall for a NAMED id: the clause keeps the
    # hand-picked dispatch protected by the refusal "even when candidate
    # enumerations filtered the item earlier", and `loop --item` is that
    # hand-pick on the drain command.
    repo = _origin_backed_repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())

    rc = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--item",
            "bd-ib-v072",
            "--budget",
            "1",
            "--journal",
            str(tmp_path / "journal.jsonl"),
        ]
    )

    assert rc == _EXIT_UNGRADEABLE_CRITERIA
    assert "bd-ib-v072" in capsys.readouterr().err
    assert next(iter(read_work_items(path=_config()))).status == "ready"


def test_the_autonomous_drain_leaves_an_ungradeable_candidate_unselected(
    tmp_path: Path,
) -> None:
    # The migration posture, and the discriminator against the refusal above:
    # the autonomous pass EXCLUDES the row rather than refusing the wave, so one
    # unrepaired legacy item cannot stop the queue behind it. The row itself
    # stays exactly where it is and the unrunnable-acceptance fact reports it.
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


def test_dispatch_admits_an_item_whose_criteria_are_gradeable(tmp_path: Path) -> None:
    # The discriminating control: the same path, the same repo, the same item
    # shape — only the criteria differ — must get PAST the wall. Without it an
    # exit-5 assertion is equally consistent with a wall that refuses
    # everything.
    repo = _origin_backed_repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(acceptance_criteria=_TWO_ASSERTIONS))

    rc = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            "bd-ib-v072",
            "--journal",
            str(tmp_path / "journal.jsonl"),
        ]
    )

    assert rc != _EXIT_UNGRADEABLE_CRITERIA


# --- consumer 3: groom displays the parse and never refuses on it -----------


def test_groom_reports_the_criteria_parse_for_every_filed_slice_without_refusing(
    tmp_path: Path,
) -> None:
    # A groomed slice folds its acceptance into the DESCRIPTION, so its parse is
    # legitimately empty at filing time. Groom must report that, not refuse it:
    # criteria may arrive later, and filing stays consent-gated.
    config = _config(repo_root=_valve_repo(tmp_path=tmp_path))
    append_work_item(path=config, item=_item(id="bd-ib-epic", status="backlog"))

    result = file_approved_slices(
        path=config,
        regroom_item_id="bd-ib-epic",
        slices=[
            CandidateSlice(
                title="Slice one",
                description="Do the first half.",
                acceptance="It works.",
                autonomy_tier="factory",
                repo_target="here",
            )
        ],
        local_repo="here",
        approval=GroomApproval(approver="thewoolleyman", route="resolve-blocked ledger comment"),
    )

    assert len(result.filed_slice_ids) == 1
    assert len(result.criteria_parses) == 1
    parse = result.criteria_parses[0]
    assert parse.slice_id == result.filed_slice_ids[0]
    assert parse.criteria.source == DESCRIPTION_EXIT_CRITERIA_SOURCE
    assert not parse.criteria.gradeable
    # The groom display is one of the three the v114 clause names: a slice
    # resolved from a legacy source must be reported as
    # `definition-of-done: missing` so the gap is repaired at the next touch.
    # Asserted on the GROOM RESULT rather than on the primitive, because the
    # obligation is the front-end's and only the result proves it reaches it.
    assert "definition-of-done: missing" in parse.criteria.parse_display()


# --- consumer 4 + the clause itself: ONE primitive, no second path ----------


def test_every_criteria_gate_resolves_through_the_one_primitive() -> None:
    """Each ratified gate reaches the primitive rather than re-deriving criteria.

    Two shapes satisfy the clause, and v114 introduced the second. A gate that
    holds only the ITEM imports the primitive directly. A gate that also needs
    the REPOSITORY — the workflow variant and the governed spec tree — imports
    the ONE shared acceptance-eligibility decision, which composes the primitive
    with those reads. What the clause forbids is a THIRD shape: a gate deriving
    criteria for itself, which is what the assertion below still catches, because
    a module doing that would name neither module.
    """
    item_only_gates = (
        "_dispatcher_acceptance_ai.py",
        "groom.py",
    )
    repository_aware_gates = (
        "_drive_valves.py",
        # BOTH dispatch paths, as ONE entry. The criteria wall used to be
        # duplicated per command module; it now lives in the shared
        # pre-dispatch wall `_dispatcher_run_commands` and
        # `_dispatcher_loop_command` each call. Naming the two command modules
        # here would assert the duplicate is still there.
        "_dispatcher_pre_dispatch_wall.py",
    )

    for name in item_only_gates:
        assert _PRIMITIVE_MODULE in (_COMMANDS_DIR / name).read_text(encoding="utf-8"), name
    for name in repository_aware_gates:
        assert _DECISION_MODULE in (_COMMANDS_DIR / name).read_text(encoding="utf-8"), name
    # The decision is not a second resolution: it composes the one primitive.
    decision_source = (_COMMANDS_DIR / f"{_DECISION_MODULE}.py").read_text(encoding="utf-8")
    assert _PRIMITIVE_MODULE in decision_source


def test_the_acceptance_pass_no_longer_carries_its_own_criteria_resolution() -> None:
    # The private resolution the acceptance pass used to own is the second path
    # the clause forbids; its absence is what makes "exactly one" checkable.
    source = (_COMMANDS_DIR / "_dispatcher_acceptance_ai.py").read_text(encoding="utf-8")

    assert "_description_exit_criteria" not in source
    assert "_effective_criteria_text" not in source


def test_the_capture_front_end_prose_displays_the_parse() -> None:
    # Capture is a prose-driven front-end: its call site IS the prose, so that
    # is where the display obligation has to be checkable. Since v115 the prose
    # names the FILING DISPLAY, which carries the parse as its first line along
    # with the modes, the capabilities and the findings — so the obligation is
    # checked one level in: the prose names the display, and the display composes
    # this primitive. Asserting `effective_criteria` in the prose directly would
    # now demand a SECOND resolution beside the display's, which is exactly the
    # duplicate path the clause forbids.
    prose = (_PROSE_DIR / "capture-work-item.md").read_text(encoding="utf-8")
    display = (_COMMANDS_DIR / "_dispatcher_filing_display.py").read_text(encoding="utf-8")

    assert "_dispatcher_filing_display" in prose
    assert "filing_display(" in prose
    assert "effective_criteria" in display
    assert "parse_display" in display
    assert _PRIMITIVE_MODULE in display


def test_the_groom_front_end_prose_displays_the_parse() -> None:
    prose = (_PROSE_DIR / "groom.md").read_text(encoding="utf-8")

    assert "criteria_parses" in prose
    assert "filing_display(" in prose
