"""Outcome-first contract tests for the seven operation prose files."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROSE = ROOT / ".claude-plugin" / "prose"


def _read(name: str) -> str:
    return (PROSE / name).read_text(encoding="utf-8")


def _squash(text: str) -> str:
    return " ".join(text.split()).lower()


def test_plan_opens_with_the_archive_goal_and_stop_contract() -> None:
    text = _read("plan.md")
    goal = text.index("## Goal")
    flow = text.index("## Flow")
    prerequisites = text.index("## Pre-requisites")

    assert text.startswith("# plan\n\n## Goal\n")
    assert goal < flow < prerequisites
    opening = text[goal:flow].lower()
    required = (
        "successful archive",
        "child disposition",
        "current independent completeness-review evidence",
        "verified` plan proof of done",
        "released artifact where a release applies",
        "required human attestations",
        "### continue",
        "re-read current state",
        "recorded eligible next action",
        "continuation is authorized",
        "store-write consent",
        "### suspend",
        "recorded human gate",
        "bounded wait",
        "run",
        "deadline",
        "supervising mechanism",
        "### fail",
        "unresolved input, refusal, or outage",
        "incomplete work",
        "human decision",
    )
    assert all(phrase in opening for phrase in required)


def test_plan_picker_defaults_to_the_typed_action_under_standing_direction() -> None:
    text = _read("plan.md")
    resume = text[text.index("#### Unattended resume") : text.index("### Step 4")]

    assert "presents the epic's `next_action` as the default choice" in resume
    assert "standing maintainer directive to continue satisfies that picker" in resume
    assert "take the default without re-prompting" in resume
    assert "Store-write consent remains governed by the consent contract" in resume


def test_plan_handoff_is_not_progress_and_exit_is_audited() -> None:
    text = _read("plan.md")
    handoff = text[text.index("### Step 4") : text.index("### Step 5")]

    assert "Recording a handoff does not complete an executable next action" in handoff
    assert "Before ending" in handoff
    assert "successful archive" in handoff
    assert "specific unresolved input or refusal" in handoff
    assert "run and verified continuation mechanism" in handoff
    assert "report the work as incomplete" in handoff


def test_plan_flow_precedes_a_compact_reference_and_mutation_check() -> None:
    text = _read("plan.md")
    lines = text.splitlines()
    flow = text.index("## Flow")
    reference = text.index("## Reference")
    prerequisites = text.index("### Pre-requisites")
    store = text.index("### The Plan Store")
    commands = text.index("### Package Commands")
    first_mutation = text.index("On confirmation, create exactly these records")
    prerequisite_check = text.index("Before the first mutation, verify")

    assert flow < reference < prerequisites < store < commands
    assert prerequisite_check < first_mutation
    assert len(lines) <= 450


def test_other_operations_name_their_done_state_before_prerequisites() -> None:
    expected = {
        "implement.md": (
            "definition of done proved",
            "administrative resolution",
            "acceptance on a pending host leg",
            "reported as what it is",
        ),
        "groom.md": (
            "actual routed state",
            "disposed original",
            "all-spec cut",
            "original at `backlog`",
        ),
        "capture-work-item.md": (
            "filed consented item",
            "every finding displayed",
            "finding may remain",
        ),
        "capture-impl-gaps.md": (
            "filed consented gap items",
            "every finding displayed",
            "no candidate",
        ),
        "capture-spec-drift.md": (
            "coverage attempt",
            "withheld reason",
            "zero findings",
        ),
        "discuss-work-item.md": (
            "stands by",
            "explicit-instruction gate",
        ),
    }
    architecture = (
        'per `specification/constraints.md` §"skill orchestration constraints", '
        "this is the harness-neutral operation prose; each runtime binding only maps its tools to it."
    )

    for name, phrases in expected.items():
        text = _read(name)
        done = text.index("## What done looks like")
        prerequisites = text.index("## Pre-requisites")
        opening = _squash(text[:prerequisites])
        assert architecture in opening, name
        assert done < prerequisites, name
        assert text[:done].count("\n") < 100, name
        assert all(phrase in opening for phrase in phrases), name


def test_implement_routes_product_work_and_uses_beads_lifecycle_terms() -> None:
    text = _read("implement.md")
    prose = _squash(text)

    assert "route product-code work through `drive` with `impl:<id>`" in prose
    assert "retain supervision through the detached gate runner" in prose
    assert "submission alone does not complete the work item" in prose
    assert "beads work-items store" in prose
    assert (
        "`backlog`, `ready`, `blocked`, `active`, `acceptance`, `pending-approval`, and `closed`"
        in prose
    )
    assert "jsonl" not in prose
    assert "work-items.jsonl" not in prose
    assert 'status != "open"' not in prose


def test_capture_and_plan_use_invocation_values_before_consent() -> None:
    for name in ("capture-work-item.md", "plan.md"):
        prose = _squash(_read(name))
        supplied_text = "use values supplied by the invocation"
        missing_text = "ask only for required values still missing"
        consent_text = "obtain write consent"

        assert supplied_text in prose, name
        assert missing_text in prose, name
        assert consent_text in prose, name

        supplied = prose.index(supplied_text)
        missing = prose.index(missing_text)
        consent = prose.index(consent_text)

        assert supplied < missing < consent, name


def test_rewrite_preserves_the_protected_normative_force() -> None:
    plan = _squash(_read("plan.md"))
    plan_requirements = (
        "called from the reviewer's own session",
        "while that set differs from the epic's child set",
        "record predates the latest status change",
        "does not attest complete requirement-carrier coverage",
        "each `human_attested` plan assertion is covered separately",
        "a later negative verdict defeats an older verified one",
        "actual independence of the plan's implementation",
        "still routed socially",
        "publish every plan record through the one posting primitive",
        "the primitive computes the rest",
        "a different session must replay them",
        "normal installation path",
        "refuses the move while any file outside `plan/` references",
        "same pull request as the move",
        "no stub, marker, forwarding note, or empty directory",
        "a plan assertion is not transferable",
        "disposing a plan child is **session-performable**",
        "both refuse a **spec-change-tier** child",
        "this guard only warns: it never refuses a write",
        "the warning must be surfaced",
        "an unattended resume must not author the assertions",
        "unless `next_action` was already `kind: impl`",
        "does not manufacture consent for a new write",
    )
    missing = tuple(requirement for requirement in plan_requirements if requirement not in plan)
    assert not missing, missing

    discuss = _squash(_read("discuss-work-item.md"))
    assert "it is not named `plan`" in discuss
    assert "executes only on an explicit maintainer instruction" in discuss
    assert "an implicit or ambiguous request must not trigger a drive" in discuss
    assert "read the event back" in discuss

    capture = _squash(_read("capture-work-item.md"))
    assert "capture must not refuse on a finding or on an empty parse" in capture

    groom = _squash(_read("groom.md"))
    assert "only after explicit approval" in groom
    assert "an all-spec-change cut" in groom
    assert "the original stays `backlog`" in groom

    for name in ("capture-impl-gaps.md", "capture-spec-drift.md"):
        operation = _squash(_read(name))
        assert "every invocation" in operation, name
        assert "on every exit path" in operation, name
        assert "report `withheld_reason` verbatim" in operation, name


def test_plan_and_drive_bindings_share_outcomes_across_runtimes() -> None:
    plan_bindings = (
        ROOT / ".claude-plugin" / "skills" / "plan" / "SKILL.md",
        ROOT / ".claude-plugin" / ".codex-plugin" / "skills" / "plan" / "SKILL.md",
        ROOT
        / ".claude-plugin"
        / ".pi-plugin"
        / "skills"
        / "livespec-orchestrator-beads-fabro-plan"
        / "SKILL.md",
    )
    plan_outcome = (
        "child disposition, independent completeness review, a verified plan proof of done "
        "with required attestations, and archive"
    )
    for binding in plan_bindings:
        prose = _squash(binding.read_text(encoding="utf-8"))
        assert plan_outcome in prose, binding
        assert "released-build proof where applicable" in prose, binding
        assert "prose/plan.md" in prose, binding

    drive_bindings = (
        ROOT / ".claude-plugin" / "skills" / "drive" / "SKILL.md",
        ROOT / ".claude-plugin" / ".codex-plugin" / "skills" / "drive" / "SKILL.md",
        ROOT
        / ".claude-plugin"
        / ".pi-plugin"
        / "skills"
        / "livespec-orchestrator-beads-fabro-drive"
        / "SKILL.md",
    )
    for binding in drive_bindings:
        prose = _squash(binding.read_text(encoding="utf-8"))
        assert "a valve action is complete when it returns" in prose, binding
        assert (
            "an `impl:` dispatch spans the run, the merge, the post-merge janitor, and acceptance"
            in prose
        ), binding
        assert "reported as observed when its gate reports" in prose, binding

    codex = plan_bindings[1].read_text(encoding="utf-8")
    assert 'cat "$PLUGIN_ROOT/prose/plan.md"' not in codex
    assert "sed -n '1,160p'" in codex
    assert "sed -n '161,320p'" in codex
    assert "sed -n '321,480p'" in codex
    assert "A truncation notice is an incomplete read" in codex
